"""Prevent urban management plan and district unit plan from diverging in retrieval."""
import asyncio
from defusedxml import ElementTree as ET
from app import law_api
from app.evidence import lexical_score

QUESTIONS = (
    '개발행위를 지구단위계획과 맞지않게 할수있나?',
    '개발행위를 도시관리계획과 맞지않게 할수있나?',
    '개발행위허가가 도시·군관리계획에 어긋나도 될까요?',
)


def test_both_questions_expand_to_parent_and_child():
    for q in QUESTIONS:
        terms=law_api.keywords(q)
        assert '지구단위계획' in terms
        assert '도시·군관리계획' in terms
        assert '개발행위허가' in terms


def test_both_questions_rank_same_controlling_act():
    for q in QUESTIONS:
        focus=law_api._law_topics(q,'국토의 계획 및 이용에 관한 법률')
        assert focus['58'] > 0
        assert focus['50'] > 0


def test_both_question_search_act_and_decree(monkeypatch):
    calls=[]
    class FakeClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return False
    async def fake_law(client,oc,target,word,question,max_results=2):
        calls.append((question,word))
        return []
    async def fake_interpretations(client,oc,question,**kwargs): return [],[]
    monkeypatch.setattr(law_api.httpx,'AsyncClient',FakeClient)
    monkeypatch.setattr(law_api,'_search_target',fake_law)
    monkeypatch.setattr(law_api,'_search_interpretations',fake_interpretations)
    for q in QUESTIONS:
        asyncio.run(law_api.search_official(q,'test'))
        names=[name for question,name in calls if question==q]
        assert '국토의 계획 및 이용에 관한 법률' in names
        assert '국토의 계획 및 이용에 관한 법률 시행령' in names


def test_priority_statute_includes_both_articles_within_ai_budget():
    tree=ET.fromstring('''<법령>
      <조문단위><조문번호>0058</조문번호>
        <조문내용>제58조(개발행위허가의 기준)</조문내용>
        <항내용>① 개발행위허가 신청내용이 다음 기준에 적합해야 한다.</항내용>
        <호내용>2. 도시·군관리계획 및 성장관리계획의 내용에 어긋나지 아니할 것</호내용>
      </조문단위>
      <조문단위><조문번호>0050</조문번호>
        <조문내용>제50조(지구단위계획구역 및 지구단위계획의 결정)</조문내용>
        <항내용>지구단위계획구역 및 지구단위계획은 도시·군관리계획으로 결정한다.</항내용>
      </조문단위>
    </법령>''')
    for q in QUESTIONS:
        text=law_api._flatten_content(tree,'law',q,'국토의 계획 및 이용에 관한 법률')
        assert '제58조' in text and '제50조' in text
        assert '어긋나지 아니할 것' in text
        assert '도시·군관리계획으로 결정한다' in text
        assert len(text)<=2200


def test_uploaded_casebook_relevance_across_parent_child():
    item={'title':'도시관리계획 개발행위허가','body':'지구단위계획에서 정한 기준에 따라 개발행위허가 검토'}
    assert all(lexical_score(q,item)>0 for q in QUESTIONS)
