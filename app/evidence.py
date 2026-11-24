"""Grounded retrieval ordering and AI citation selection.

This is a transparent lexical ranker, NOT a semantic relevance or legal-accuracy score.
"""
import re
from app.law_api import keywords

MAX_DISPLAY = 24
MAX_EVIDENCE = 12
LAW = {'법령'}
INTERPRETATIONS = {'법제처 해석례', '법제처 법령해석', '국토부 질의회신', '질의회신'}


def citation_group(kind: str) -> str:
    if kind == '법령':
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


def prepare_sources(question: str, candidates: list[dict]) -> tuple[list[dict], list[str]]:
    """Merge duplicate IDs, sort by lexical evidence match and pin relevant statutes."""
    terms = ranking_terms(question)
    seen = set()
    ranked = []
    for idx, original in enumerate(candidates):
        item = dict(original)
        key = item.get('id') or (item.get('kind'), item.get('title'), item.get('body', '')[:60])
        if key in seen:
            continue
        seen.add(key)
        score = lexical_score(question, item, terms)
        item['match_score'] = score
        item['citation_group'] = citation_group(item.get('kind', ''))
        ranked.append((score, idx, item))
    ranked.sort(key=lambda t: (-t[0], t[1]))
    prepared = [item for _, _, item in ranked[:MAX_DISPLAY]]
    for i, item in enumerate(prepared, 1):
        # Opaque within a result set; selected IDs are checked against server cache.
        item['ref_id'] = f's{i}'
        item['citation_number'] = i
    # Preserve up to three best relevant statutes, then use all remaining slots
    # across source categories by relevance. User may change any selection.
    statute = [i for i, s in enumerate(prepared) if s['kind'] == '법령' and s['match_score'] > 0][:3]
    selected_indices = set(statute)
    for i in range(len(prepared)):
        if len(selected_indices) >= MAX_EVIDENCE:
            break
        selected_indices.add(i)
    selected_ids = [s['ref_id'] for i, s in enumerate(prepared) if i in selected_indices]
    return prepared, selected_ids


def selected_sources(sources: list[dict], selected_ids: list[str]) -> list[dict]:
    """Preserve display / citation order, regardless of checkbox click order."""
    wanted = set(selected_ids)
    return [s for s in sources if s['ref_id'] in wanted]
