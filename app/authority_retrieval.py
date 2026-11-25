"""Authority/approval issue expansion for Korean administrative-law retrieval.

This module helps find controlling provisions.  It does NOT decide who has a
statutory delegation or whether a specific cost item may lawfully be reduced.
No external API calls and no guessed statutory text are used here.
"""
from __future__ import annotations

import re

# Agency and statute are SEARCH ASSOCIATIONS, not claims of delegated authority.
_AGENCY_LAW = (
    (('경자청', '경제자유구역청', '경자청장', '경제자유구역청장'),
     '경제자유구역의 지정 및 운영에 관한 특별법'),
    (('매립면허관청', '공유수면매립면허관청'),
     '공유수면 관리 및 매립에 관한 법률'),
)

# A plan + an administrative power often appear under different words in the law.
# Expand *retrieval terms*, not legal conclusions.  Do not conflate the powers.
_PLAN_SYNONYMS = (
    ('실시계획', ('실시계획', '승인', '변경승인', '승인신청', '승인절차', '심사', '적합', '부합')),
    ('개발계획', ('개발계획', '수립', '변경', '승인', '협의')),
    ('관리기본계획', ('관리기본계획', '수립', '변경', '고시', '승인')),
    ('매립실시계획', ('매립실시계획', '승인', '적정성', '매립면허관청')),
)

_POWER_VERBS = ('검토', '심사', '승인', '허가', '인가', '면허', '변경승인',
                '지정', '협의', '시정', '명령', '취소', '반려', '거부', '결정')
_AGENCY_WORDS = ('청장', '경자청', '관청', '행정기관', '행정청', '허가권자', '승인권자',
                 '시도지사', '시·도지사', '시장', '군수', '구청장', '장관')


def _normalize(text: str) -> str:
    return re.sub(r'[^0-9가-힣a-z]', '', (text or '').lower())


def _match_any(question: str, words: tuple[str, ...]) -> bool:
    q = _normalize(question)
    return any(_normalize(w) in q for w in words)


def authority_issue(question: str) -> bool:
    """Return whether this is an actor/power review question, not a legal answer."""
    q = question or ''
    authority_actor = _match_any(q, _AGENCY_WORDS) or _match_any(
        q, ('누가', '누구', '어느기관', '권한', '소관', '담당', '위임'))
    action = _match_any(q, _POWER_VERBS)
    return bool(authority_actor and action)


def associated_statutes(question: str) -> list[str]:
    """Identify potentially related statute families from agencies alone."""
    laws = []
    for actor_aliases, law_name in _AGENCY_LAW:
        if _match_any(question, actor_aliases):
            laws.append(law_name)
    return laws


def expansion_terms(question: str) -> list[str]:
    if not authority_issue(question):
        return []
    terms: list[str] = []
    for law_name in associated_statutes(question):
        terms.extend([law_name, law_name.split('의 지정')[0]])
    if associated_statutes(question):
        terms.extend(('시도지사', '경제자유구역청') if any('경제자유구역' in n for n in associated_statutes(question))
                     else ('매립면허관청',))
    # Most specific subject first; never expand general '실시계획' instead of
    # a more specific '매립실시계획' when both are mentioned.
    for name, aliases in sorted(_PLAN_SYNONYMS, key=lambda x: -len(x[0])):
        if name in question:
            terms.extend(aliases)
            break
    if _match_any(question, ('검토', '심사', '검증', '적정성')):
        terms.extend(('심사', '검토', '적정성', '승인기준', '권한'))
    if _match_any(question, ('승인', '허가', '인가')):
        terms.extend(('승인', '허가', '신청', '절차', '요건'))
    output=[]; used=set()
    for term in terms:
        key=_normalize(term)
        if key and key not in used:
            used.add(key)
            output.append(term)
    return output[:16]


def expanded_question(question: str) -> str:
    """Build an additional retrieval query, preserving the user's original ask."""
    additions = expansion_terms(question)
    if not additions:
        return question
    existing = _normalize(question)
    new = [term for term in additions if _normalize(term) not in existing]
    return (question + ' ' + ' '.join(new[:16])).strip()


def retry_question(question: str) -> str:
    """One bounded second-pass query for missing controlling legal provisions."""
    laws=associated_statutes(question)
    subject=next((s for s,_ in sorted(_PLAN_SYNONYMS,key=lambda x:-len(x[0])) if s in question), '')
    return ' '.join([question] + laws + ([subject] if subject else []) +
                    ['승인권자', '승인절차', '심사기준', '법령상 권한']).strip()


def has_direct_provision(question: str, sources: list[dict]) -> bool:
    """Approximate evidence presence; no claim about the law's application.

    Only an actual statute article can satisfy this, not a case title or guide.
    """
    subject=next((s for s,_ in sorted(_PLAN_SYNONYMS,key=lambda x:-len(x[0])) if s in question), None)
    for item in sources:
        if item.get('kind') != '법령' or not item.get('article_number'):
            continue
        text = _normalize(item.get('body', ''))
        if subject and _normalize(subject) not in text:
            continue
        if any(a in text for a in ('승인', '허가', '인가', '권한', '지정', '협의', '심사')):
            return True
    return False


AUTHORITY_ANSWER_GUIDANCE = (
    '질문 속 행정기관 명칭·약칭과 법령상의 정식 승인권자를 반드시 구분하세요. '
    '승인권한이 있는 경우에는 제출자료를 법정 승인요건에 비추어 검토하는 일반적인 심사와 '
    '별도 명시적 근거가 필요한 개별 금전 감액·명령·처분 권한을 혼동하지 마세요. '
    '승인권자와 실제 업무 수행 기관이 다를 수 있으므로 사무위임 또는 위탁의 근거가 '
    '검색자료에 없다면 위임 여부는 확인 필요하다고 밝히세요. '
    '법령에 질문과 동일한 단어(예: 검토)가 없다는 이유만으로 관련 승인·심사 권한의 '
    '근거가 없다고 단정하지 마세요. 다만 일반론과 특정 지역의 실제 권한을 구분하세요. '
    '인용한 법령 조문의 문장이 결론을 뒷받침하는지 확인하고, 근거가 없다면 정확히 어떤 부분이 '
    '확인되지 않는지 설명하세요.'
)
