"""Regression tests for institution -> legal action -> approval authority retrieval.

All official law response documents in this test are synthetic fixtures. Tests
verify retrieval behavior, not whether an actual delegation exists in a region.
"""
import asyncio
from types import SimpleNamespace
from defusedxml import ElementTree as ET

from app import law_api, main
from app.authority_retrieval import (
    authority_issue, associated_statutes, expanded_question, retry_question,
    has_direct_provision, AUTHORITY_ANSWER_GUIDANCE,
)
from app.statutory_retrieval import family_queries, extract_relevant_articles

ACT = '경제자유구역의 지정 및 운영에 관한 특별법'
QUESTION = '경자청은 실시계획 검토할수있나?'


def test_institution_alias_leads_to_parent_act_and_three_tiers():
    expanded = expanded_question(QUESTION)
    assert authority_issue(QUESTION)
    assert associated_statutes(QUESTION) == [ACT]
    assert ACT in expanded
    assert '승인' in expanded and '시도지사' in expanded
    assert expanded_question(expanded) == expanded
    assert family_queries(expanded, law_api.PREFERRED_LAWS)[:3] == [ACT, ACT+' 시행령', ACT+' 시행규칙']


def test_ordinary_questions_are_not_overexpanded():
    q = '개발행위를 도시관리계획과 맞지 않게 할 수 있나?'
    assert not authority_issue(q)
    assert expanded_question(q) == q
    q2 = '공유수면법 제46조의 내용은?'
    assert expanded_question(q2) == q2


def test_actor_review_is_not_automatically_a_delegation():
    assert '사무위임' in AUTHORITY_ANSWER_GUIDANCE
    assert '금전 감액' in AUTHORITY_ANSWER_GUIDANCE
    assert '동일한 단어' in AUTHORITY_ANSWER_GUIDANCE


def test_generic_approval_review_query_does_not_force_economic_zone_law():
    q = '산업입지법에 따른 개발계획 승인권자가 심사할 수 있나?'
    expanded = expanded_question(q)
    assert '심사' in expanded and '승인' in expanded
    assert ACT not in expanded
    assert '산업입지 및 개발에 관한 법률' in family_queries(expanded, law_api.PREFERRED_LAWS)


def test_economic_zone_review_discovers_controlling_statutory_article():
    xml = '''<법령>
      <조문단위><조문번호>0011</조문번호>
        <조문내용>제11조(인허가 등의 의제) 개발사업시행자가 실시계획의 승인을 받은 경우 관련 허가가 의제된다.</조문내용>
      </조문단위>
      <조문단위><조문번호>0009</조문번호>
        <조문내용>제9조(경제자유구역개발사업 실시계획의 승인)</조문내용>
        <항내용>① 개발사업시행자는 실시계획을 작성하여 관할 시ㆍ도지사의 승인을 받아야 한다.</항내용>
      </조문단위>
      <조문단위><조문번호>0028</조문번호><조문내용>제28조(그 밖의 사항) 과태료를 부과한다.</조문내용></조문단위>
    </법령>'''
    parts = extract_relevant_articles(ET.fromstring(xml), expanded_question(QUESTION), ACT, max_articles=2)
    assert parts[0]['article_number'] == '9', parts
    assert '도지사의 승인' in parts[0]['body']


def test_direct_evidence_requires_actual_law_article_and_subject():
    assert not has_direct_provision(QUESTION, [{'kind':'질의회신', 'body':'경자청이 실시계획을 승인한다'}])
    assert not has_direct_provision(QUESTION, [{'kind':'법령', 'body':'승인 절차', 'article_number':'7'}])
    article={'kind':'법령','law_title':ACT,'article_number':'9',
             'body':'제9조 실시계획에 관하여 관할 시ㆍ도지사의 승인을 받아야 한다.'}
    assert has_direct_provision(QUESTION, [article])


def test_one_bounded_retry_when_direct_article_missing(monkeypatch):
    calls=[]
    async def fake_search(question,oc,deep=True,categories=None):
        calls.append((question,deep,tuple(categories or ())))
        if len(calls) == 1:
            return [{'id':'opinion','kind':'질의회신','title':'실시계획 참고',
                     'body':'검토 관련', 'organization':'국토부','issued_date':'','url':''}],None
        return [{'id':'article','kind':'법령','title':ACT+' 제9조','law_title':ACT,
                 'article_number':'9','law_level':'법률',
                 'body':'제9조 경제자유구역개발사업 실시계획은 관할 시도지사의 승인을 받아야 한다.',
                 'organization':'법제처','issued_date':'','url':''}],None
    async def fake_answer(question,sources):
        assert question == QUESTION  # the original wording reaches the AI
        assert any(s.get('article_number')=='9' for s in sources)
        return '근거확보','ai'
    monkeypatch.setattr(main,'search_official',fake_search)
    monkeypatch.setattr(main,'search_local',lambda *a,**k: [])
    monkeypatch.setattr(main,'generate_answer',fake_answer)
    monkeypatch.setattr(main,'rate_limit',lambda req: None)
    monkeypatch.setenv('LAW_OC','mock-oc')
    response=asyncio.run(main.ask(main.AskRequest(question=QUESTION, categories=['law']),SimpleNamespace()))
    assert response['answer']=='근거확보'
    assert len(calls)==2, calls
    assert calls[1][1] is False and calls[1][2] == ('law',)
    assert '승인권자' in retry_question(QUESTION)


def test_no_retry_when_direct_article_is_present(monkeypatch):
    calls=[]
    async def fake_search(question,oc,deep=True,categories=None):
        calls.append(question)
        return [{'id':'article','kind':'법령','title':ACT+' 제9조','law_title':ACT,
                 'article_number':'9','law_level':'법률',
                 'body':'제9조 실시계획에 관하여 관할 시도지사의 승인을 받아야 한다.',
                 'organization':'법제처','issued_date':'','url':''}],None
    async def fake_answer(*args):return '답변','ai'
    monkeypatch.setattr(main,'search_official',fake_search)
    monkeypatch.setattr(main,'search_local',lambda *a,**k: [])
    monkeypatch.setattr(main,'generate_answer',fake_answer)
    monkeypatch.setattr(main,'rate_limit',lambda req: None)
    monkeypatch.setenv('LAW_OC','mock-oc')
    resp=asyncio.run(main.ask(main.AskRequest(question=QUESTION,categories=['law']),SimpleNamespace()))
    assert resp['answer']=='답변'
    assert len(calls)==1


def test_live_api_shape_for_economic_zone_approval_is_retrieved(monkeypatch):
    """Use mock XML to verify the full official API + article extraction pipeline."""
    act=ACT
    names=[act,act+' 시행령',act+' 시행규칙']
    serial={name:str(i+811) for i,name in enumerate(names)}
    assert names == family_queries(expanded_question(QUESTION),law_api.PREFERRED_LAWS)[:3]
    calls=[]

    class FakeClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False

    async def fake_request(client,endpoint,params):
        calls.append((endpoint,dict(params)))
        if endpoint=='lawSearch.do':
            name=params.get('query')
            if name not in serial: return b'<lawSearch><totalCnt>0</totalCnt></lawSearch>'
            return (f'<lawSearch><법령><법령일련번호>{serial[name]}</법령일련번호>'
                    f'<법령ID>{serial[name]}</법령ID><법령명한글>{name}</법령명한글>'
                    f'</법령></lawSearch>').encode('utf-8')
        name=next(k for k,v in serial.items() if v==params['ID'])
        if name==act:
            num,txt='0009', ('제9조(경제자유구역개발사업 실시계획의 승인) '
                '개발사업시행자는 실시계획을 작성하여 관할 시도지사의 승인을 받아야 한다.')
        elif name.endswith('시행령'):
            num,txt='0009','제9조(실시계획의 승인절차) 시행자는 시도지사에게 실시계획 승인신청을 한다.'
        else:
            num,txt='0001','제1조(목적) 시행규칙의 적용범위를 정한다.'
        return (f'<법령><조문단위><조문번호>{num}</조문번호>'
                f'<조문내용>{txt}</조문내용></조문단위></법령>').encode('utf-8')

    async def fake_interp(*args,**kwargs):return [],[]
    monkeypatch.setattr(law_api.httpx,'AsyncClient',FakeClient)
    monkeypatch.setattr(law_api,'_request_xml',fake_request)
    monkeypatch.setattr(law_api,'_search_interpretations',fake_interp)
    sources,_=asyncio.run(law_api.search_official(QUESTION,'mock-oc',categories=['law']))
    assert any(x['law_title']==act and x['article_number']=='9' for x in sources),sources
    assert any(x['law_title']==act+' 시행령' and x['article_number']=='9' for x in sources),sources
    assert has_direct_provision(QUESTION,sources)
    assert len([e for e,p in calls if e=='lawSearch.do']) >= 3
