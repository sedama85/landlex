"""SQLite corpus: documents + page-aware chunks for large source collections."""
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

DB_PATH = Path(os.getenv('DATABASE_PATH', 'data/landlaw.db'))
LOCK = Lock()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def initialize():
    with LOCK, connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS documents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          title TEXT NOT NULL, kind TEXT NOT NULL, organization TEXT NOT NULL,
          issued_date TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
          body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )''')
        columns = {r['name'] for r in c.execute('PRAGMA table_info(documents)')}
        for column, type_sql in [('file_type','TEXT NOT NULL DEFAULT ""'),
                                 ('size_bytes','INTEGER NOT NULL DEFAULT 0'),
                                 ('page_count','INTEGER NOT NULL DEFAULT 0')]:
            if column not in columns:
                c.execute(f'ALTER TABLE documents ADD COLUMN {column} {type_sql}')
        c.execute('''CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL, page INTEGER NOT NULL DEFAULT 0,
            body TEXT NOT NULL, UNIQUE(document_id, chunk_index)
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id)')
        try:
            c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(body, tokenize='trigram')")
        except sqlite3.OperationalError:
            pass  # some Windows SQLite builds lack trigram; basic LIKE fallback works
        # Migrate existing small documents so the old data remains searchable.
        old_docs = list(c.execute('''SELECT d.id, d.body FROM documents d
            WHERE length(d.body) > 0
            AND NOT EXISTS (SELECT 1 FROM document_chunks x WHERE x.document_id=d.id)'''))
        from app.document_ingest import chunks_from_text
        for row in old_docs:
            for i, (page, part) in enumerate(chunks_from_text(row['body'])):
                _insert_chunk(c, row['id'], i, page, part)


def _insert_chunk(conn, document_id, idx, page, part):
    cur = conn.execute('''INSERT INTO document_chunks(document_id,chunk_index,page,body)
                          VALUES(?,?,?,?)''', (document_id, idx, page, part))
    try:
        conn.execute('INSERT INTO document_chunks_fts(rowid,body) VALUES(?,?)', (cur.lastrowid, part))
    except sqlite3.OperationalError:
        pass


def insert_document_chunks(title, kind, organization, issued_date, source_url, chunks, size_bytes=0, file_type=''):
    """Single transaction; failure rolls back document and partial chunks."""
    count = 0
    pages = set()
    char_count = 0
    # Keep writes locked because the desktop MVP uses only one indexing worker.
    with LOCK, connect() as c:
        cur = c.execute('''INSERT INTO documents(title,kind,organization,issued_date,source_url,body,file_type,size_bytes)
             VALUES(?,?,?,?,?,?,?,?)''',
             (title,kind,organization,issued_date,source_url,'',file_type,size_bytes))
        doc_id = cur.lastrowid
        for page, part in chunks:
            if not part.strip():
                continue
            _insert_chunk(c, doc_id, count, page, part)
            pages.add(page)
            char_count += len(part)
            count += 1
        if not count:
            raise ValueError('텍스트를 찾지 못했습니다. 스캔 PDF라면 OCR 처리가 필요합니다.')
        c.execute('UPDATE documents SET page_count=? WHERE id=?',
                  (len(pages) if pages != {0} else 0, doc_id))
    return {'id':doc_id, 'chunks':count, 'characters':char_count,
            'pages':len(pages) if pages != {0} else 0, 'title':title}


def insert_document(title, kind, organization, issued_date, source_url, body):
    """Retain previous API for legacy tests / callers."""
    from app.document_ingest import chunks_from_text
    result = insert_document_chunks(title,kind,organization,issued_date,source_url,
                                    chunks_from_text(body))
    with LOCK, connect() as c:
        c.execute('UPDATE documents SET body=? WHERE id=?', (body, result['id']))
    return result['id']


def list_documents(limit=100):
    with connect() as c:
        return [dict(r) for r in c.execute('''
            SELECT d.id,d.title,d.kind,d.organization,d.issued_date,d.source_url,
              coalesce(sum(length(ch.body)), 0) AS characters,
              count(ch.id) AS chunks, d.file_type, d.size_bytes, d.page_count
            FROM documents d LEFT JOIN document_chunks ch ON ch.document_id=d.id
            GROUP BY d.id ORDER BY d.id DESC LIMIT ?''', (limit,))]


def delete_document(doc_id):
    with LOCK, connect() as c:
        ids = [r[0] for r in c.execute('SELECT id FROM document_chunks WHERE document_id=?',(doc_id,))]
        if ids:
            try:
                c.executemany('DELETE FROM document_chunks_fts WHERE rowid=?', ((id_,) for id_ in ids))
            except sqlite3.OperationalError:
                pass
        c.execute('DELETE FROM document_chunks WHERE document_id=?',(doc_id,))
        cur=c.execute('DELETE FROM documents WHERE id=?',(doc_id,))
        return cur.rowcount


def _keywords(question):
    stop={'하려면','가능한가','하는가','어떻게','해야','하는','있는','없는','경우',
          '관련','대해서','알려줘','무엇인가','여부','어떤','해줘','입니까','됩니까','변경하려면'}
    return [t for t in re.findall(r'[가-힣A-Za-z0-9]{2,}',question.lower())
            if t not in stop][:15]


def search_local(question, limit=8):
    from app.law_api import keywords as legal_keywords
    # Broaden uploaded casebook lookup too: 경자구역 -> 경제자유구역,
    # 유치업종 -> 유치산업, etc. Keep an upper bound for large documents.
    tokens=list(dict.fromkeys(_keywords(question) + legal_keywords(question)))[:22]
    if not tokens:
        return []
    # FTS5 trigram indexes LIKE patterns containing >=3 contiguous characters.
    # Avoid retrieving the full corpus (the previous version loaded all full texts).
    with connect() as c:
        indexed = bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_chunks_fts'").fetchone())
        long_tokens = [t for t in tokens if len(t) >= 3]
        if indexed and long_tokens:
            clauses = ' OR '.join('f.body LIKE ?' for _ in long_tokens)
            params = [f'%{t}%' for t in long_tokens]
            query = f'''SELECT ch.id,ch.document_id,ch.chunk_index,ch.page,
                ch.body,d.title,d.kind,d.organization,d.issued_date,d.source_url
                FROM document_chunks_fts f
                JOIN document_chunks ch ON f.rowid=ch.id
                JOIN documents d ON d.id=ch.document_id
                WHERE {clauses} LIMIT 1200'''
            candidates = list(c.execute(query, params))
        else:
            clauses = ' OR '.join('ch.body LIKE ?' for _ in tokens)
            params = [f'%{t}%' for t in tokens]
            candidates = list(c.execute(f'''SELECT ch.id,ch.document_id,ch.chunk_index,ch.page,
                ch.body,d.title,d.kind,d.organization,d.issued_date,d.source_url
                FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
                WHERE {clauses} LIMIT 1200''', params))
    ranked=[]
    for r in candidates:
        body=r['body'].lower(); title=r['title'].lower()
        hits=sum(min(body.count(t),4) for t in tokens)
        score = hits + sum(5 for t in tokens if t in title)
        # A paragraph-level chunk is already short; provide full chunk for citation.
        if score:
            page = r['page']
            suffix = f' · {page}쪽' if page else f' · 구간 {r["chunk_index"]+1}'
            ranked.append((score, {
                'id': f'local-{r["id"]}', 'kind':r['kind'],
                'title':r['title']+suffix,'organization':r['organization'],
                'issued_date':r['issued_date'],'url':r['source_url'],
                'body':r['body'],'source_note':'관리자 등록 공개자료'+suffix
            }))
    ranked.sort(key=lambda x:x[0],reverse=True)
    # Prefer results from different parts of the source and independent docs.
    return [r for _, r in ranked[:limit]]
