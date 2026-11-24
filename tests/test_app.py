import pytest
import time
from fastapi.testclient import TestClient
from app import main, storage

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setenv('ADMIN_TOKEN','testing-super-secure-token')
    monkeypatch.delenv('LAW_OC', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with TestClient(main.app) as c:
        yield c


def test_home_and_status(client):
    assert client.get('/').status_code == 200
    status=client.get('/api/status').json()
    assert status['law_api_connected'] is False
    assert status['ai_connected'] is False


def test_empty_search_does_not_hallucinate(client):
    r=client.post('/api/ask', json={'question':'개발계획 변경 절차는?','categories':['local']})
    assert r.status_code == 200
    assert r.json()['mode']=='no_sources'
    assert r.json()['sources']==[]


def test_admin_secret_required(client):
    r=client.post('/api/admin/upload', data={'title':'테스트 자료'}, files={'file':('a.txt',b'abc'*30)})
    assert r.status_code == 403
    assert client.get('/api/admin/documents').status_code == 403


def test_upload_search_and_delete(client):
    token={'X-Admin-Token':'testing-super-secure-token'}
    txt='산업단지 관리기본계획 변경 질의회신 자료입니다. 원문 내용은 관리자 업로드 파일을 기반으로 합니다.'
    uploaded=client.post('/api/admin/upload', headers=token,
         data={'title':'산업단지 관리기본계획 질의회신','kind':'질의회신','organization':'테스트기관','issued_date':'2026-01-01','source_url':'https://example.org/public'},
         files={'file':('memo.txt',txt.encode('utf-8'),'text/plain')})
    assert uploaded.status_code==202, uploaded.text
    job_id = uploaded.json()['job_id']
    for _ in range(60):
        job = client.get('/api/admin/jobs/' + job_id, headers=token).json()
        if job['status'] in ('completed','failed'):
            break
        time.sleep(.025)
    assert job['status'] == 'completed', job
    record_id=job['id']
    found=client.post('/api/ask',json={'question':'산업단지 관리기본계획 변경','categories':['local']})
    assert found.status_code==200
    result=found.json()
    assert result['mode']=='search_only'
    assert result['sources'][0]['title'].startswith('산업단지 관리기본계획 질의회신')
    assert 'AI API 키' in result['answer']
    assert client.delete(f'/api/admin/documents/{record_id}',headers=token).status_code==200
    assert client.get('/api/admin/documents',headers=token).json()['documents']==[]


def test_reject_unsupported_file(client):
    token={'X-Admin-Token':'testing-super-secure-token'}
    r=client.post('/api/admin/upload', headers=token,
          data={'title':'임의 파일'}, files={'file':('evil.exe',b'hello'*20)})
    assert r.status_code==400


def test_reject_invalid_link(client):
    token={'X-Admin-Token':'testing-super-secure-token'}
    r=client.post('/api/admin/upload', headers=token,
          data={'title':'임의 자료','source_url':'javascript:alert(1)'},
          files={'file':('a.txt',b'abc'*20)})
    assert r.status_code==400
