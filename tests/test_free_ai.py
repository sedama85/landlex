import asyncio
from app import main

SAMPLE = [{'kind':'법령','title':'테스트 법령','organization':'법제처',
           'issued_date':'2026-01-01','url':'https://example.org','body':'경미한 변경은 규정에 따른다.'}]


def test_gemini_answer(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'secret-test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
    class FakeResponse:
        status_code = 200
        def json(self):
            return {'candidates':[{'content':{'parts':[{'text':'검토 답변 [자료 1]'}]}}]}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): pass
        async def post(self, url, *, headers, json):
            assert url.endswith('gemini-3.5-flash-lite:generateContent')
            assert headers['x-goog-api-key'] == 'secret-test-key'
            assert '테스트 법령' in json['contents'][0]['parts'][0]['text']
            return FakeResponse()
    monkeypatch.setattr(main.httpx,'AsyncClient',Client)
    answer, mode = asyncio.run(main.generate_answer('개발계획 변경?', SAMPLE))
    assert (answer,mode)==('검토 답변 [자료 1]','ai')


def test_gemini_quota_error(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','secret')
    class FakeResponse: status_code=429
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*exc): pass
        async def post(self,*args,**kwargs): return FakeResponse()
    monkeypatch.setattr(main.httpx,'AsyncClient',Client)
    answer, mode=asyncio.run(main.generate_answer('개발계획 변경?', SAMPLE))
    assert mode=='ai_error' and '한도' in answer
    assert 'secret' not in answer


def test_ollama_local_only(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','ollama')
    monkeypatch.setenv('OLLAMA_MODEL','qwen3.5:4b')
    class FakeResponse:
        status_code=200
        def json(self): return {'response':'로컬 검토 [자료 1]'}
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*exc): pass
        async def post(self,url,*,json):
            assert url == 'http://127.0.0.1:11434/api/generate'
            assert json['model']=='qwen3.5:4b'
            return FakeResponse()
    monkeypatch.setattr(main.httpx,'AsyncClient',Client)
    assert asyncio.run(main.generate_answer('개발계획 변경?', SAMPLE))==('로컬 검토 [자료 1]','ai')


def test_auto_picks_gemini_before_paid_openai(monkeypatch):
    monkeypatch.delenv('AI_PROVIDER',raising=False)
    monkeypatch.setenv('OPENAI_API_KEY','unused_openai_key')
    monkeypatch.setenv('GEMINI_API_KEY','google-key')
    assert main._ai_provider()=='gemini'
