"""Chunked indexing of administrator-supplied PDF, HWP/HWPX, TXT and MD files.

The uploaded original stays in temporary storage only during indexing; chunks and
source metadata are stored in SQLite. No OCR and no automatic case boundary detection.
"""
from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterator

import pdfplumber

CHUNK_SIZE = 2600
CHUNK_OVERLAP = 220
MAX_FILE_BYTES = 512 * 1024 * 1024
SUPPORTED_EXTENSIONS = {'.pdf', '.hwp', '.hwpx', '.txt', '.md'}


def chunks_from_text(text: str, page: int = 0, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterator[tuple[int, str]]:
    """Produce overlapping text slices; shift cuts to nearby paragraph boundaries."""
    if not 0 <= overlap < size:
        raise ValueError('올바르지 않은 본문 분할 설정')
    text = text.strip()
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            break_at = text.rfind('\n', start + size // 2, end)
            if break_at > start + size // 2:
                end = break_at + 1
        part = text[start:end].strip()
        if part:
            yield page, part
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)


def extract_chunks(path: Path, suffix: str) -> Iterator[tuple[int, str]]:
    """Yield (page, text). 0 page means HWP/TXT physical page unavailable."""
    if suffix == '.pdf':
        # Work page by page, rather than loading the whole file into RAM.
        with pdfplumber.open(str(path)) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ''
                yield from chunks_from_text(page_text, page=page_no)
                page.close()  # discard per-page cached layout data
    elif suffix in {'.hwp', '.hwpx'}:
        try:
            import syhwp
        except ImportError as exc:
            raise ValueError('HWP 읽기 모듈(syhwp)이 설치되지 않았습니다. pip install syhwp') from exc
        # Use Markdown form to preserve tables as text searchable by RAG.
        try:
            text = syhwp.extract_markdown(str(path))
        except Exception as exc:
            raise ValueError('HWP/HWPX 내용을 읽지 못했습니다. 암호·문서손상·HWP 버전을 확인하세요.') from exc
        yield from chunks_from_text(text)
    elif suffix in {'.txt', '.md'}:
        # Streaming decoder avoids reading 100+MB of UTF-8 text at once.
        import codecs
        decoder = codecs.getincrementaldecoder('utf-8-sig')('strict')
        buf = ''
        with path.open('rb') as f:
            while True:
                raw = f.read(1024 * 1024)
                buf += decoder.decode(raw, final=not raw)
                if not raw:
                    break
                while len(buf) > CHUNK_SIZE * 3:
                    cut = CHUNK_SIZE * 2
                    yield from chunks_from_text(buf[:cut])
                    buf = buf[cut - CHUNK_OVERLAP:]
        yield from chunks_from_text(buf)
    else:
        raise ValueError('지원하지 않는 파일 형식입니다.')


def validate_signature(path: Path, suffix: str) -> None:
    """Do not trust an extension alone, to catch accidental file mismatch."""
    with path.open('rb') as f:
        head = f.read(16)
    if suffix == '.pdf' and not head.startswith(b'%PDF-'):
        raise ValueError('PDF 파일 형식이 올바르지 않습니다.')
    if suffix == '.hwp' and not head.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        raise ValueError('HWP 5.x 파일이 아닙니다. HWPX라면 확장자를 확인하세요.')
    if suffix == '.hwpx' and not head.startswith(b'PK'):
        raise ValueError('HWPX 파일 형식이 올바르지 않습니다.')


def index_file(path: Path, suffix: str, metadata: dict) -> dict:
    from app.storage import insert_document_chunks
    validate_signature(path, suffix)
    return insert_document_chunks(
        metadata['title'], metadata['kind'], metadata['organization'],
        metadata['issued_date'], metadata['source_url'],
        extract_chunks(path, suffix), path.stat().st_size, suffix
    )
