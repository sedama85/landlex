"""Offline regression tests for official multi-scope interpretation search."""
import asyncio
from app import law_api as mod
from app.main import _source_context

CASE = '20-0098'
TITLE = '공유수면 매립으로 의제되는 경우 감정평가업자 지정 주체'


def fake_record(target='expc', item='330319', number=CASE):
    key = mod.SERIAL_KEYS[target][0]
    return (f'<LawSearch><totalCnt>1</totalCnt><{target}>'
            f'<{key}>{item}</{key}><안건명>{TITLE}</안건명>'
            f'<안건번호>{number}</안건번호><회신일자>20200625</회신일자>'
            f'</{target}></LawSearch>').encode()

DETAIL = '''<해석례><질의요지>매립지 가격 산정에 필요한 감정평가업자 지정 주체는?</질의요지>
<회답>매립면허관청이 지정해야 합니다.</회답>
<이유>개별 법령의 권한과 의제 효과를 구분합니다.</이유></해석례>'''.encode()


def test_case_number_normalization():
    assert mod._case_number('법제처 20-0098 안건을 찾아줘') == '200098'
    assert mod._case_number('20–0098') == '200098'
    assert mod._case_number('2020년 0098건') == ''
    assert mod._case_number('안건번호 200098 알려줘') == '200098'


def test_case_number_uses_itmno_and_returns_fulltext(monkeypatch):
    seen=[]
    async def fake_request(client, endpoint, params):
        seen.append((endpoint, dict(params)))
        if endpoint == 'lawService.do':
            return DETAIL
        if params.get('target') == 'expc' and params.get('itmno') == '200098':
            return fake_record()
        return b'<LawSearch><totalCnt>0</totalCnt></LawSearch>'
    monkeypatch.setattr(mod, '_request_xml', fake_request)
    found, warning = asyncio.run(mod.search_official('법제처 20-0098 유권해석 찾아줘', 'test', deep=False, categories=['expc']))
    assert warning is None
    assert found and found[0]['case_number'] == CASE
    assert '매립면허관청' in found[0]['body']
    assert any(p.get('itmno') == '200098' and 'query' not in p for _,p in seen)
    assert all(p.get('target') in ('expc','molegCgmExpc') for _,p in seen)


def test_body_scope_finds_title_miss_and_deduplicates(monkeypatch):
    seen=[]
    async def fake_request(client, endpoint, params):
        seen.append(dict(params))
        if endpoint == 'lawService.do':
            return DETAIL
        if params['target']=='expc' and params.get('search')=='2' and params.get('query') == '감정평가업자':
            return fake_record()
        return b'<LawSearch><totalCnt>0</totalCnt></LawSearch>'
    monkeypatch.setattr(mod, '_request_xml', fake_request)
    found,warning=asyncio.run(mod.search_official('감정평가업자 지정 주체는 누구인가?', 'test',deep=True,categories=['expc']))
    assert not warning
    assert len([r for r in found if r['id']=='expc-330319'])==1
    assert any(p.get('search')=='2' for p in seen)
    assert any(p.get('search')=='1' for p in seen)
    assert '회답:' in found[0]['body']


def test_pagination_bounded_on_many_results(monkeypatch):
    seen=[]
    async def fake_request(client, endpoint, params):
        seen.append(dict(params))
        if endpoint=='lawService.do': return DETAIL
        if params.get('search')=='2':
            return b'<LawSearch><totalCnt>100</totalCnt></LawSearch>'
        return b'<LawSearch><totalCnt>0</totalCnt></LawSearch>'
    monkeypatch.setattr(mod, '_request_xml', fake_request)
    found,_=asyncio.run(mod.search_official('감정평가업자 공유수면 의제', 'test', deep=True, categories=['expc']))
    assert found == []
    assert any(p.get('page')=='2' for p in seen)
    assert len([p for p in seen if p.get('page')=='2'])<=4


def test_source_context_has_12_slots_with_bounded_size():
    sources=[{'kind':'법제처 해석례','title':'테스트'+str(i),'organization':'법제처',
              'issued_date':'20200625','url':'https://www.law.go.kr/',
              'case_number':CASE,'body':'가'*15000} for i in range(20)]
    ctx=_source_context(sources)
    assert '[12] 분류:' in ctx and '[13] 분류:' not in ctx
    assert len(ctx)<=31000
    assert '20-0098' in ctx
