"""Regression tests: legal question must include the controlling Act AND Decree."""
import asyncio
from defusedxml import ElementTree as ET
import app.law_api as mod

QUESTION = '경제자유구역 내 유치업종을 추가하려면 개발계획을 변경해야 하나요?'


def test_priority_law_title_matches_act_and_decree():
    records = [
        {'법령명한글':'경제자유구역의 지정 및 운영에 관한 특별법 시행규칙'},
        {'법령명한글':'경제자유구역의 지정 및 운영에 관한 특별법 시행령'},
        {'법령명한글':'경제자유구역의 지정 및 운영에 관한 특별법'},
    ]
    result=mod._best_law_records(records,'경제자유구역의 지정 및 운영에 관한 특별법',2)
    assert result[0]['법령명한글']=='경제자유구역의 지정 및 운영에 관한 특별법'
    assert result[1]['법령명한글'].endswith('시행령')


def test_picks_relevant_sections_for_industry_addition():
    tree = ET.fromstring('''<법령>
      <조문단위><조문번호>0001</조문번호><조문내용>제1조(목적) 경제자유구역</조문내용></조문단위>
      <조문단위><조문번호>0005</조문번호><조문가지번호>0002</조문가지번호>
      <조문내용>제5조의2(경제자유구역개발계획의 변경)</조문내용>
      <항내용>④ 경미한 사항</항내용><호내용>6. 산업유치계획 중 유치산업 배치계획 변경 또는 유치산업의 추가</호내용>
      <목내용>가. 핵심전략산업</목내용><목내용>나. 산업단지관리기본계획에 반영하려는 입주업종</목내용>
      </조문단위>
      <조문단위><조문번호>0030</조문번호><조문내용>제30조 경제자유구역의 관리</조문내용></조문단위>
    </법령>''')
    body=mod._flatten_content(tree,'law',QUESTION,'경제자유구역의 지정 및 운영에 관한 특별법 시행령')
    assert '제5조의2' in body
    assert '산업유치계획' in body
    assert '입주업종' in body


def test_law_search_uses_id_not_master_number(monkeypatch):
    seen=[]
    async def fake_request(client, endpoint, params):
        seen.append((endpoint, params))
        if endpoint == 'lawSearch.do':
            return '''<LawSearch><law><법령일련번호>987654</법령일련번호>
            <법령ID>009411</법령ID><법령명한글>경제자유구역의 지정 및 운영에 관한 특별법</법령명한글>
            </law></LawSearch>'''.encode()
        return '''<법령><조문단위><조문번호>0007</조문번호>
            <조문내용>제7조(경제자유구역개발계획의 변경) 개발계획을 변경할 수 있다</조문내용>
            </조문단위></법령>'''.encode()
    monkeypatch.setattr(mod,'_request_xml',fake_request)
    result=asyncio.run(mod._search_target(None,'test','law',
                   '경제자유구역의 지정 및 운영에 관한 특별법',QUESTION))
    assert len(result)==1
    assert seen[1][1].get('ID')=='009411'
    assert 'MST' not in seen[1][1]


def test_law_search_falls_back_to_mst_without_id(monkeypatch):
    seen=[]
    async def fake_request(client, endpoint, params):
        seen.append((endpoint,params))
        if endpoint == 'lawSearch.do':
            return '''<LawSearch><law><법령일련번호>987654</법령일련번호>
            <법령명한글>경제자유구역의 지정 및 운영에 관한 특별법</법령명한글>
            </law></LawSearch>'''.encode()
        return '''<법령><조문단위><조문번호>0006</조문번호>
            <조문내용>제6조 산업유치계획</조문내용></조문단위></법령>'''.encode()
    monkeypatch.setattr(mod,'_request_xml',fake_request)
    result=asyncio.run(mod._search_target(None,'test','law',
                    '경제자유구역의 지정 및 운영에 관한 특별법',QUESTION))
    assert len(result)==1
    assert seen[1][1].get('MST')=='987654'


def test_all_relevant_statute_searches(monkeypatch):
    calls=[]
    class FakeClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
    async def fake_target(client,oc,target,word,question,max_results=3):
        calls.append((target,word)); return []
    monkeypatch.setattr(mod.httpx, 'AsyncClient', FakeClient)
    monkeypatch.setattr(mod,'_search_target', fake_target)
    asyncio.run(mod.search_official(QUESTION,'test'))
    assert ('law','경제자유구역의 지정 및 운영에 관한 특별법') in calls
    assert ('law','경제자유구역의 지정 및 운영에 관한 특별법 시행령') in calls
