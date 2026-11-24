"""Offline tests for cross-statute retrieval, exact articles, context selection."""
import asyncio
from app import law_api
from app.evidence import prepare_sources, selected_sources
from app.main import _source_context
from app.statutory_retrieval import family_names, family_queries, extract_relevant_articles, law_level
from defusedxml import ElementTree as ET

QUESTION = '공유수면법에서 감정평가사는 누가 지정하나?'
ACT='공유수면 관리 및 매립에 관한 법률'


def test_query_covers_three_tiers_not_only_act_and_decree():
    queries=family_queries(QUESTION, law_api.PREFERRED_LAWS)
    assert queries == [ACT, ACT+' 시행령', ACT+' 시행규칙']


def test_generic_law_title_detection():
    assert family_names('건축법에서 공작물 설치 허가는 누가하나?')[0] == '건축법'
    assert family_names('행정기본법 제24조 인허가 의제는?')[0] == '행정기본법'
    assert family_names('산업입지법 개발계획 변경')[0] == '산업입지 및 개발에 관한 법률'
    assert family_names('산업단지 관리기본계획의 변경은?')[0] == '산업집적활성화 및 공장설립에 관한 법률'


def test_article_level_ranks_direct_provision_over_unrelated():
    xml='''<법령>
      <조문단위><조문번호>0050</조문번호><조문내용>제50조(기타사업) 매립 면허</조문내용></조문단위>
      <조문단위><조문번호>0051</조문번호>
        <조문내용>제51조(매립지의 가격 산정)</조문내용>
        <항내용>② 매립면허취득자가 총사업비에 상당하는 매립지의 소유권을 취득할 때</항내용>
        <호내용>해양수산부령으로 정하는 바에 따라 매립면허관청이 지정한 2인 이상의 감정평가법인등이 평가한 평가액의 산술평균치를 기준으로 한다.</호내용>
      </조문단위>
    </법령>'''
    root=ET.fromstring(xml)
    records=extract_relevant_articles(root,QUESTION, ACT+' 시행령',max_articles=1)
    assert records[0]['article_number']=='51'
    assert '매립면허관청이 지정한' in records[0]['body']
    assert '제51조' in records[0]['body']


def test_article_level_prioritizes_rule33():
    xml='''<법령>
    <조문단위><조문번호>0033</조문번호>
      <조문내용>제33조(감정평가법인등의 지정)</조문내용>
      <항내용>① 매립면허관청은 영 제51조제2항에 따라 감정평가법인등을 지정하려는 경우 10일 이상 공고한 후 신청자 중에서 추첨하여 지정해야 한다.</항내용>
    </조문단위></법령>'''
    result=extract_relevant_articles(ET.fromstring(xml), QUESTION,ACT+' 시행규칙')
    assert result[0]['article_label']=='제33조'
    assert '추첨하여 지정' in result[0]['body']


def test_full_official_pipeline_and_AI_context(monkeypatch):
    calls=[]
    names=[ACT, ACT+' 시행령',ACT+' 시행규칙']
    corpus={
      ACT: ('46','제46조(매립지의 소유권 취득) 매립면허취득자는 총사업비 상당의 매립지 소유권을 취득할 수 있다.'),
      ACT+' 시행령': ('51','제51조(매립지의 가격 산정) ② 매립면허관청이 지정한 2인 이상의 감정평가법인등이 평가한 평균치를 기준으로 한다.'),
      ACT+' 시행규칙': ('33','제33조(감정평가법인등의 지정) ① 매립면허관청은 10일 이상 공고 후 신청자 중 추첨하여 지정한다.'),
    }
    serials={ACT:'101',ACT+' 시행령':'102',ACT+' 시행규칙':'103'}
    class FakeClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
    async def fake_request(client,endpoint,params):
        calls.append((endpoint,dict(params)))
        if endpoint=='lawSearch.do':
            if params.get('target')!='law' or params.get('query') not in corpus:
                return b'<LawSearch><totalCnt>0</totalCnt></LawSearch>'
            name=params['query'];ser=serials[name]
            return (f'<LawSearch><law><법령일련번호>{ser}</법령일련번호>'
                    f'<법령ID>{ser}</법령ID><법령명한글>{name}</법령명한글>'
                    f'<시행일자>20261124</시행일자></law></LawSearch>').encode()
        id_=params['ID']
        name=next(k for k,v in serials.items() if v==id_)
        art,body=corpus[name]
        return (f'<법령><조문단위><조문번호>{int(art):04d}</조문번호>'
                f'<조문내용>{body}</조문내용></조문단위></법령>').encode()
    async def fake_int(*args,**kwargs):return [],[]
    monkeypatch.setattr(law_api.httpx,'AsyncClient', FakeClient)
    monkeypatch.setattr(law_api,'_request_xml', fake_request)
    monkeypatch.setattr(law_api,'_search_interpretations',fake_int)
    result,warning=asyncio.run(law_api.search_official(QUESTION,'test', categories=['law']))
    levels={x['law_level'] for x in result}
    # The Act can be absent when it lacks a clause directly bearing on the
    # narrow question; never invent a statutory reference just to fill a tier.
    assert levels=={'시행령','시행규칙'},result
    assert {x['article_number'] for x in result}=={'51','33'},result
    assert any('추첨' in x['body'] for x in result)
    assert any(p.get('query')==ACT+' 시행규칙' for endpoint,p in calls if endpoint=='lawSearch.do')
    # Stress with many superficially relevant opinions to ensure all three
    # actual statute tiers reach the LLM context (rather than rank 18, 19).
    opinions=[{'id':f'fake-{i}', 'kind':'법제처 해석례','title':f'공유수면 감정평가 지정 회신 {i}',
       'organization':'기관','issued_date':'20200101','url':'', 'body':'감정평가 지정을 검토하라는 내용'} for i in range(35)]
    prepared,ids=prepare_sources(QUESTION,opinions+result)
    picked=selected_sources(prepared,ids)
    assert {'시행령','시행규칙'} <= {s['law_level'] for s in picked if s['kind']=='법령'},picked
    context=_source_context(picked)
    assert '제51조' in context and '제33조' in context,context
    assert '매립면허관청' in context
    assert '추첨' in context
    assert len(prepared)==24 and len(picked)==12


def test_does_not_claim_law_when_only_unrelated_text():
    tree=ET.fromstring('<법령><조문단위><조문번호>0001</조문번호><조문내용>제1조 목적 교통안전 강화</조문내용></조문단위></법령>')
    assert not extract_relevant_articles(tree, QUESTION, ACT)
