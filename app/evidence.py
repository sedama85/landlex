"""Grounded retrieval ordering and AI citation selection.

This is a transparent lexical ranker, NOT a semantic relevance or legal-accuracy score.
"""
import re
from app.law_api import keywords
from app.statutory_retrieval import law_level

MAX_DISPLAY = 24
MAX_EVIDENCE = 12
LAW = {'법령', '행정규칙'}
INTERPRETATIONS = {'법제처 해석례', '법제처 법령해석', '국토부 질의회신', '질의회신'}


def citation_group(kind: str) -> str:
    if kind in {'법령', '행정규칙'}:
        return 'law'
    if kind in INTERPRETATIONS:
        return 'qa'
    if kind == '판례':
        return 'case'
    return 'other'


def normalize(s: str) -> str:
    return re.sub(r'[^0-9a-z가-힣]', '', str(s or '').lower())


def ranking_terms(question: str) -> list[str]:
    terms = list(dict.fromkeys(keywords(question)))
    expansions = {
        '유치업종': ['유치산업', '입주업종', '산업유치계획'],
        '경자구역': ['경제자유구역'],
        '경자법': ['경제자유구역'],
        '매립실시계획': ['매립', '실시계획'],
        '감정평가업자': ['감정평가'],
    }
    for needle, aliases in expansions.items():
        if needle in question:
            terms.extend(aliases)
    return list(dict.fromkeys(normalize(t) for t in terms if len(normalize(t)) >= 2))[:16]


def lexical_score(question: str, item: dict, terms: list[str] | None = None) -> int:
    terms = ranking_terms(question) if terms is None else terms
    title = normalize(item.get('title', ''))
    body = normalize(item.get('body', '')[:15000])
    score = 0
    for token in terms:
        if token in title:
            score += 9 + min(6, len(token))
        if token in body:
            score += 3 + min(5, len(token))
    number = re.search(r'(?<!\d)(\d{2})\s*[-–—]\s*(\d{4})(?!\d)', question)
    if number and normalize(item.get('case_number', '')) == ''.join(number.groups()):
        score += 1000
    # Tiny tie-breaker, never enough to outrank a meaningful keyword match.
    if score and item.get('kind') in LAW | INTERPRETATIONS:
        score += 1
    return score


# AUTHORITY_RETRIEVAL_V8: caller supplies issue-expanded retrieval terms.
def prepare_sources(question: str, candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Rank candidates while reserving actual Act/Decree/Rule evidence.

    This is lexical relevance, not a legal-accuracy score.  Directly applicable
    statutes from distinct tiers cannot be displaced by 20 similar case titles.
    """
    terms=ranking_terms(question)
    seen=set(); ranked=[]
    for idx, original in enumerate(candidates):
        item=dict(original)
        key=item.get('id') or (item.get('kind'), item.get('title'), item.get('body','')[:60])
        if key in seen: continue
        seen.add(key)
        score=lexical_score(question,item,terms)
        # Official provision + direct keyword evidence earns a moderate boost.
        # It does NOT substitute for checking the actual section's content.
        if item.get('kind')=='법령' and item.get('article_number'):
            normalized = normalize(item.get('body',''))
            matched = sum(1 for term in terms if term in normalized)
            if matched >= 2:
                score += 12 + min(3, matched)*3
        item['match_score']=score
        item['citation_group']=citation_group(item.get('kind',''))
        if item.get('kind')=='법령':
            item['law_level']=item.get('law_level') or law_level(item.get('law_title') or item.get('title',''))
        ranked.append((score,idx,item))
    ranked.sort(key=lambda t:(-t[0],t[1]))
    # One reference from each available statute tier, even if many case titles
    # repeat the query. Avoid including unrelated zero-match statutes.
    reserved=[]
    for level in ('법률','시행령','시행규칙'):
        hit=next((t for t in ranked if t[2].get('kind')=='법령'
                  and t[2].get('law_level')==level and t[0]>0), None)
        if hit and hit not in reserved: reserved.append(hit)
    # Keep one matching administrative rule visible without elevating it
    # to the same legal authority as Acts or subordinate legislation.
    admin_hit=next((t for t in ranked if t[2].get('kind')=='행정규칙' and t[0]>0),None)
    if admin_hit: reserved.append(admin_hit)
    kept=list(reserved)
    kept_keys={t[1] for t in kept}
    for t in ranked:
        if len(kept)>=MAX_DISPLAY: break
        if t[1] not in kept_keys:
            kept.append(t);kept_keys.add(t[1])
    kept.sort(key=lambda t:(-t[0],t[1]))
    prepared=[item for _,_,item in kept]
    for i,item in enumerate(prepared,1):
        item['ref_id']=f's{i}'
        item['citation_number']=i
    selected = {i for i,s in enumerate(prepared)
        if any(s is tier[2] for tier in reserved)}
    # Preserve old guarantee for tests and cases where no tier metadata exists:
    # include up to three relevant legal documents, not just interpretations.
    for i,src in enumerate(prepared):
        if src['kind']=='법령' and src['match_score']>0 and len(selected)<3:
            selected.add(i)
    for i in range(len(prepared)):
        if len(selected)>=MAX_EVIDENCE: break
        selected.add(i)
    return prepared,[prepared[i]['ref_id'] for i in range(len(prepared)) if i in selected]

def selected_sources(sources: list[dict], selected_ids: list[str]) -> list[dict]:
    """Preserve display / citation order, regardless of checkbox click order."""
    wanted = set(selected_ids)
    return [s for s in sources if s['ref_id'] in wanted]
