import os
import sys
import time
import types
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app import main, storage
from app.document_ingest import chunks_from_text, extract_chunks, validate_signature


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage,'DB_PATH',tmp_path/'test_large.db')
    monkeypatch.setenv('ADMIN_TOKEN','test-secure')
    monkeypatch.setenv('AI_PROVIDER','off')
    monkeypatch.delenv('LAW_OC', raising=False)
    with TestClient(main.app) as c:
        yield c


def await_index(client,job_id):
    h={'X-Admin-Token':'test-secure'}
    for _ in range(200):
        r=client.get('/api/admin/jobs/'+job_id,headers=h)
        assert r.status_code==200
        data=r.json()
        if data['status'] in ('completed','failed'):
            return data
        time.sleep(0.02)
    raise AssertionError('Indexing did not finish')


def test_large_text_chunk_search_page(client):
    body=('다양한 분양전문 사례집 문구.\n'*1000 +
          '유치업종 추가는 시행령 제5조의2를 참조한다.\n' +
          '일반적인 개발계획 변경과 경미한 변경을 비교한다.\n')*4
    h={'X-Admin-Token':'test-secure'}
    uploaded=client.post('/api/admin/upload',headers=h,
          data={'title':'유치업종 질의회신 사례집'},
          files={'file':('casebook.txt',body.encode('utf-8'),'text/plain')})
    assert uploaded.status_code==202, uploaded.text
    data=await_index(client,uploaded.json()['job_id'])
    assert data['status']=='completed',data
    assert data['chunks']>15
    found=client.post('/api/ask',json={'question':'유치업종 추가 시행령','categories':['local']}).json()
    assert found['sources'],found
    assert '제5조의2' in ' '.join(s['body'] for s in found['sources'])
    assert '구간' in found['sources'][0]['title']
    assert client.delete(f'/api/admin/documents/{data["id"]}',headers=h).status_code==200
    assert not storage.search_local('유치업종')


def test_hwp_hwpx_supported_with_parser_mock(client, monkeypatch):
    module=types.SimpleNamespace(extract_markdown=lambda path:'국토계획법 개발행위허가 관련 질의회신의 주요 내용입니다.\n'*70)
    monkeypatch.setitem(sys.modules, 'syhwp', module)
    h={'X-Admin-Token':'test-secure'}
    for ext, signature in [('hwp', bytes.fromhex('D0CF11E0A1B11AE1')),('hwpx',b'PK\x03\x04')]:
        response=client.post('/api/admin/upload',headers=h, data={'title':'HWP 질의회신'},
           files={'file':('samples.'+ext,signature+b'0'*200,'application/octet-stream')})
        assert response.status_code==202,response.text
        job=await_index(client,response.json()['job_id'])
        assert job['status']=='completed',job
    assert len(storage.search_local('개발행위허가'))==2


def test_pdf_reports_page_and_body(client, tmp_path):
    from reportlab.pdfgen import canvas
    p=tmp_path/'test.pdf'
    c=canvas.Canvas(str(p))
    # Latin fallback for reportlab built-in font; use test Latin query and page detection.
    c.drawString(90, 730, 'first page zoning permit')
    c.showPage(); c.drawString(90, 730, 'second page development plan permit')
    c.save()
    h={'X-Admin-Token':'test-secure'}
    with p.open('rb') as f:
        resp=client.post('/api/admin/upload',headers=h,data={'title':'development plan casebook'},
                files={'file':('case.pdf',f,'application/pdf')})
    assert resp.status_code==202,resp.text
    job=await_index(client, resp.json()['job_id'])
    assert job['status']=='completed',job
    assert job['pages']==2
    matches=storage.search_local('development plan')
    assert matches and '2쪽' in matches[0]['title']


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_MB','1')
    h={'X-Admin-Token':'test-secure'}
    r=client.post('/api/admin/upload',headers=h,data={'title':'Huge file'},
          files={'file':('test.txt',b'x'*(1024*1024+2),'text/plain')})
    assert r.status_code==413
    assert '1MB' in r.json()['detail']


def test_wrong_extension_signature(client):
    h={'X-Admin-Token':'test-secure'}
    r=client.post('/api/admin/upload',headers=h,data={'title':'bad PDF'},
          files={'file':('not.pdf',b'not a PDF','application/pdf')})
    job=await_index(client,r.json()['job_id'])
    assert job['status']=='failed' and 'PDF' in job['message']


def test_legacy_migration(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB_PATH',tmp_path/'legacy.db')
    storage.initialize()
    with storage.connect() as c:
        c.execute('INSERT INTO documents(title,kind,organization,body) VALUES(?,?,?,?)',
                  ('legacy','질의회신','기관','과거 질의회신 내용이 포함된 기존 자료'))
    storage.initialize()
    assert storage.search_local('과거 질의회신')
