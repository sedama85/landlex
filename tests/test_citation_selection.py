"""Regression tests for ranked evidence / click-through numbering / re-analysis."""
import time
import pytest
from fastapi.testclient import TestClient
from app import main, storage
from app.evidence import prepare_sources, selected_sources


def sample(n, kind='법제처 해석례', body='유치업종 변경과 관련된 사항'):
    return {'id':f'id-{n}','kind':kind,'title':f'경제자유구역 제{n}호 유치업종',
            'body':body,'organization':'테스트기관','issued_date':'20261124','url':'https://example.org'}


def test_lexical_rank_and_statute_pin():
    docs=[sample(i) for i in range(22)]
    docs += [sample(22,'법령','산업유치계획 및 경미한 변경 요건')]
    docs += [sample(23,'법령','시행령 제5조의2 유치산업 추가')]
    docs += [sample(24,'법령','관계법령 기타')]
    ordered, chosen=prepare_sources('경제자유구역 내 유치업종 변경', docs)
    assert len(ordered)==24
    assert len(chosen)==12
    assert [x['citation_number'] for x in ordered]==list(range(1,25))
    pinned=[x['ref_id'] for x in ordered if x['kind']=='법령' and x['match_score']>0][:3]
    assert all(ref in chosen for ref in pinned)
    assert all(x['citation_group']=='law' for x in ordered if x['kind']=='법령')


def test_case_number_outranks_generic_hits():
    a=sample(1)
    b=sample(2)
    b['case_number']='20-0098'
    ranked,_=prepare_sources('법제처 법령해석 20-0098 찾아줘',[a,b])
    assert ranked[0]['case_number']=='20-0098'


def test_selected_context_preserves_source_display_number():
    records,chosen=prepare_sources('유치업종 변경',[sample(i) for i in range(20)])
    noncontig=selected_sources(records,['s2','s17'])
    ctx=main._source_context(noncontig)
    assert '[2] 분류:' in ctx
    assert '[17] 분류:' in ctx
    assert '[1] 분류:' not in ctx


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'DB_PATH', tmp_path/'citations.db')
    monkeypatch.delenv('LAW_OC', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setenv('AI_PROVIDER','off')
    main.SEARCH_SNAPSHOTS.clear()
    with TestClient(main.app) as c:
        yield c


def test_reanalyze_citation_ids_and_reject_invalid(client, monkeypatch):
    from app import main as mod
    monkeypatch.setattr(mod, 'search_local', lambda *args,**kwargs: [sample(i) for i in range(18)])
    r=client.post('/api/ask',json={'question':'경제자유구역 유치업종 추가','categories':['local']})
    assert r.status_code==200,r.text
    data=r.json()
    assert len(data['sources'])==18
    assert data['search_id']
    assert len(data['selected_ids'])==12
    selection=['s2','s17']
    r=client.post('/api/reanalyze',json={'search_id':data['search_id'],'selected_ids':selection})
    assert r.status_code==200,r.text
    result=r.json()
    assert result['selected_ids']==selection
    assert len(result['sources'])==18
    assert result['mode']=='search_only'
    bad=client.post('/api/reanalyze',json={'search_id':data['search_id'],'selected_ids':['s99']})
    assert bad.status_code==400
    duplicate=client.post('/api/reanalyze',json={'search_id':data['search_id'],'selected_ids':['s2','s2']})
    assert duplicate.status_code==400
    forged=client.post('/api/reanalyze',json={'search_id':'f'*32,'selected_ids':['s2']})
    assert forged.status_code==404
    too_many=client.post('/api/reanalyze',json={'search_id':data['search_id'],'selected_ids':[f's{i}' for i in range(1,14)]})
    assert too_many.status_code==422


def test_no_search_id_when_no_sources(client):
    r=client.post('/api/ask',json={'question':'출처 없는 임의 질문','categories':['local']})
    assert r.status_code==200
    assert r.json()['search_id'] is None


def test_snapshot_expiry(client,monkeypatch):
    monkeypatch.setattr(main,'search_local',lambda *args,**kwargs:[sample(1)])
    r=client.post('/api/ask',json={'question':'유치업종 변경','categories':['local']}).json()
    main.SEARCH_SNAPSHOTS[r['search_id']]['created_at']-=1900
    res=client.post('/api/reanalyze',json={'search_id':r['search_id'],'selected_ids':['s1']})
    assert res.status_code==404
