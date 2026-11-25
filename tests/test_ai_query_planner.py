"""Generic AI question rewriting and grounded retrieval tests (no live API)."""
import asyncio
from types import SimpleNamespace
import json

from app import main, query_planner


def test_bounded_rewrites_keep_user_question_unchanged():
    q='경자청은 실시계획을 검토할 수 있나?'
    plan=query_planner.parse_plan({
        'issue':'승인권한과 검토',
        'search_questions':[
            q,
            '경제자유구역의 지정 및 운영에 관한 특별법 실시계획 승인권자',
            '실시계획 승인 심사 범위 및 권한 위임 여부',
            '세 번째 검색은 무시',
        ]},q)
    assert plan.used_ai and len(plan.search_questions)==2
    assert plan.search_questions[0].startswith('경제자유구역')
    assert plan.public_info()['issue']=='승인권한과 검토'


def test_bad_json_cannot_inject_more_queries():
    assert not query_planner.parse_plan([], '질문이 무엇인가?').used_ai
    assert not query_planner.parse_plan({'search_questions':'문자열'},'질문이 무엇인가?').used_ai
    p=query_planner.parse_plan({'search_questions':['a']*100+['법령 조회 질문']},'법령질문')
    assert not p.search_questions


def test_ai_planner_off_skips_network(monkeypatch):
    monkeypatch.setenv('LANDLEX_QUERY_PLANNER','off')
    monkeypatch.setenv('GEMINI_API_KEY','test-not-real')
    assert asyncio.run(query_planner.plan_question('아무 질문'))==query_planner.SearchPlan()


def test_planner_parses_structured_gemini_response(monkeypatch):
    q='경자청은 실시계획을 검토할수 있나?'
    payload={'issue':'승인과 심사의 관계','search_questions':[
        '경제자유구역법 실시계획 승인권한은 어디에 있는가?',
        '경제자유구역청장이 실시계획 승인요건을 검토할 권한이 있는가?']}
    seen=[]
    class Client:
        def __init__(self,**kwargs): pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def post(self,url,headers,json):
            seen.append(json)
            return SimpleNamespace(status_code=200,json=lambda:{'candidates':[
                {'content':{'parts':[{'text':__import__('json').dumps(payload,ensure_ascii=False)}]}}]})
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','dummy')
    monkeypatch.setenv('LANDLEX_QUERY_PLANNER','on')
    monkeypatch.setattr(query_planner.httpx,'AsyncClient',Client)
    plan=asyncio.run(query_planner.plan_question(q))
    assert plan.used_ai and len(plan.search_questions)==2
    assert seen[0]['generationConfig']['responseMimeType']=='application/json'
    assert '원래 질문' in seen[0]['contents'][0]['parts'][0]['text']


def test_original_question_is_preserved_and_official_retry_is_bounded(monkeypatch):
    original='경자청은 실시계획 검토할수있나?'
    planned='경제자유구역의 지정 및 운영에 관한 특별법 실시계획 승인권자'
    fake=query_planner.SearchPlan('승인권한', (planned, '위임기관 승인 심사 여부'),True)
    async def planning(q):
        assert q==original
        return fake
    calls=[]
    async def search(q,oc,deep=True,categories=None):
        calls.append((q,deep,tuple(categories or [])))
        if q==original:
            return [{'id':'op','kind':'질의회신','title':'일반 의견','body':'실시계획 관련',
                     'organization':'국토부','issued_date':'','url':''}],None
        return [{'id':'act9','kind':'법령','title':'경제자유구역법 제9조',
                 'law_title':'경제자유구역의 지정 및 운영에 관한 특별법',
                 'article_number':'9','law_level':'법률',
                 'body':'제9조 실시계획 승인 신청 시 관할 시도지사의 승인을 받아야 한다.',
                 'organization':'법제처','issued_date':'','url':''}],None
    async def answer(q,sources):
        assert q==original
        assert any(s.get('article_number')=='9' for s in sources)
        return '회답 [1]','ai'
    local_calls=[]
    def local_search(q,limit):
        local_calls.append(q)
        return []
    monkeypatch.setattr(main,'plan_question',planning)
    monkeypatch.setattr(main,'search_official',search)
    monkeypatch.setattr(main,'generate_answer',answer)
    monkeypatch.setattr(main,'search_local',local_search)
    monkeypatch.setattr(main,'rate_limit',lambda req:None)
    monkeypatch.setenv('LAW_OC','mock')
    resp=asyncio.run(main.ask(main.AskRequest(question=original),SimpleNamespace()))
    assert resp['answer']=='회답 [1]'
    assert len(calls)==2 and calls[0][0]==original
    assert calls[1]==(planned,False,('law',))
    assert local_calls==[original,planned,'위임기관 승인 심사 여부']
    assert resp['search_plan']['used_ai']


def test_if_planner_fails_still_answers_original(monkeypatch):
    async def fallback(_):return query_planner.SearchPlan()
    async def official(*args,**kwargs):return [],None
    async def answer(q,sources):return ('근거 부족','no_sources')
    monkeypatch.setattr(main,'plan_question',fallback)
    monkeypatch.setattr(main,'search_official',official)
    monkeypatch.setattr(main,'search_local',lambda *a,**k:[])
    monkeypatch.setattr(main,'generate_answer',answer)
    monkeypatch.setattr(main,'rate_limit',lambda req:None)
    r=asyncio.run(main.ask(main.AskRequest(question='변경 계획을 허가받을 수 있나?',categories=['law']),SimpleNamespace()))
    assert r['question']=='변경 계획을 허가받을 수 있나?'
    assert not r['search_plan']['used_ai']
