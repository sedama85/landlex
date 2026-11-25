"""v10: AI query rewrite observability and second-query fallback tests."""
import asyncio
from types import SimpleNamespace
from app import query_planner, main


def test_query_plan_success_has_observable_status():
    q='경자청은 실시계획을 검토할 수 있나?'
    plan=query_planner.parse_plan({
        'issue':'실시계획 승인과 심사 권한',
        'search_questions':['경제자유구역법 실시계획 승인권자','실시계획 승인권자의 심사 범위']},q)
    assert plan.used_ai
    assert plan.public_info()['status']=='ok'
    assert len(plan.search_questions)==2


def test_planner_api_429_is_exposed_without_secret(monkeypatch):
    class Client:
        def __init__(self,**kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): return False
        async def post(self,*a,**kw): return SimpleNamespace(status_code=429)
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','secret-in-runtime-only')
    monkeypatch.setenv('LANDLEX_QUERY_PLANNER','on')
    monkeypatch.setattr(query_planner.httpx,'AsyncClient',Client)
    plan=asyncio.run(query_planner.plan_question('경자청 실시계획의 승인권한?'))
    assert plan.public_info()['status']=='http_429'
    assert not plan.used_ai
    assert 'secret' not in str(plan.public_info())


def test_two_rewrites_used_if_first_has_no_statute(monkeypatch):
    question='경자청은 실시계획을 검토할 수 있나?'
    first='실시계획 서류 검토 기관이 누구인가?'
    second='경제자유구역의 지정 및 운영에 관한 특별법 실시계획 승인권자'
    plan=query_planner.SearchPlan('승인권한과 심사범위',(first,second),True,'ok')
    calls=[]
    async def planner(q):
        assert q==question
        return plan
    async def official(q, oc, deep=True, categories=None):
        calls.append(q)
        if q==second:
            return [{
                'id':'law-9','kind':'법령','title':'경제자유구역법 제9조','law_level':'법률',
                'law_title':'경제자유구역의 지정 및 운영에 관한 특별법',
                'article_number':'9','body':'제9조 실시계획은 관할 시도지사의 승인을 받아야 한다.',
                'organization':'법제처','issued_date':'','url':'https://www.law.go.kr/'}],None
        return [],None
    async def answer(q, sources):
        assert q==question
        assert any(s.get('article_number')=='9' for s in sources)
        return '승인 요건 검토 가능 [1]','ai'
    monkeypatch.setattr(main,'plan_question',planner)
    monkeypatch.setattr(main,'search_official',official)
    monkeypatch.setattr(main,'search_local',lambda *args,**kw:[])
    monkeypatch.setattr(main,'generate_answer',answer)
    monkeypatch.setattr(main,'rate_limit',lambda _:None)
    monkeypatch.setenv('LAW_OC','dummy')
    resp=asyncio.run(main.ask(main.AskRequest(question=question,categories=['law']),SimpleNamespace()))
    assert calls==[question,first,second]
    assert resp['search_plan']['official_queries']==[first,second]
    assert resp['search_plan']['statute_articles_selected']>=1
    assert resp['search_plan']['status']=='ok'


def test_skip_unnecessary_second_lookup(monkeypatch):
    question='지구단위계획은 도시관리계획인가?'
    first='국토의 계획 및 이용에 관한 법률 지구단위계획 지정'
    second='도시관리계획 제50조 지구단위계획'
    plan=query_planner.SearchPlan('계획의 포함관계',(first,second),True,'ok')
    calls=[]
    async def official(q,*args,**kwargs):
        calls.append(q)
        if q==first:
            return [{
                'id':'law-50','kind':'법령','title':'국토계획법 제50조','law_level':'법률',
                'article_number':'50','body':'지구단위계획은 도시·군관리계획으로 결정한다.',
                'organization':'법제처','issued_date':'','url':'https://www.law.go.kr/'}],None
        return [],None
    async def answer(q,s): return '지구단위계획은 도시군관리계획으로 결정합니다.','ai'
    monkeypatch.setattr(main,'plan_question',lambda q: asyncio.sleep(0,result=plan))
    monkeypatch.setattr(main,'search_official',official)
    monkeypatch.setattr(main,'search_local',lambda *args,**kwargs:[])
    monkeypatch.setattr(main,'generate_answer',answer)
    monkeypatch.setattr(main,'rate_limit',lambda _:None)
    monkeypatch.setenv('LAW_OC','dummy')
    resp=asyncio.run(main.ask(main.AskRequest(question=question,categories=['law']),SimpleNamespace()))
    assert calls==[question,first]
    assert resp['search_plan']['official_queries']==[first]
