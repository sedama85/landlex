"""Generic statutory hierarchy discovery and article-level retrieval for MOLEG XML.

No text of statutes is shipped in source code.  Results are extracted only from
live official response XML, with article, law level and effective-date provenance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Small aliases recognize common names; they are NOT hard-coded legal answers.
LAW_ALIASES = (
    ('경제자유구역법', '경제자유구역의 지정 및 운영에 관한 특별법'),
    ('경자법', '경제자유구역의 지정 및 운영에 관한 특별법'),
    ('경자구역', '경제자유구역의 지정 및 운영에 관한 특별법'),
    ('경제자유구역', '경제자유구역의 지정 및 운영에 관한 특별법'),
    ('공유수면법', '공유수면 관리 및 매립에 관한 법률'),
    ('공유수면', '공유수면 관리 및 매립에 관한 법률'),
    ('국계법', '국토의 계획 및 이용에 관한 법률'),
    ('도시관리계획', '국토의 계획 및 이용에 관한 법률'),
    ('도시·군관리계획', '국토의 계획 및 이용에 관한 법률'),
    ('도시군관리계획', '국토의 계획 및 이용에 관한 법률'),
    ('지구단위계획', '국토의 계획 및 이용에 관한 법률'),
    ('개발행위', '국토의 계획 및 이용에 관한 법률'),
    ('산집법', '산업집적활성화 및 공장설립에 관한 법률'),
    ('산업집적', '산업집적활성화 및 공장설립에 관한 법률'),
    ('산업입지법', '산업입지 및 개발에 관한 법률'),
    ('관리기본계획', '산업집적활성화 및 공장설립에 관한 법률'),
    ('산업단지', '산업입지 및 개발에 관한 법률'),
    ('도시개발', '도시개발법'),
    ('건축법', '건축법'),
    ('행정기본법', '행정기본법'),
    ('도로법', '도로법'),
    ('하천법', '하천법'),
)

_STOP = {'법률', '법령', '시행령', '시행규칙', '누가', '누구', '어떻게', '무엇', '관련', '여부', '있는', '없는', '것은', '것이',
         '정하는', '정해진', '하는', '있나', '하나', '인가', '해줘', '근거', '누구인지', '될까', '해야', '하며', '될수'}
_SUFFIXES = ('에서', '으로써', '으로서', '으로는', '에게는', '에게', '부터', '까지', '이라고', '이라면',
             '이라서', '으로', '하는가', '하나요', '할까요', '하나', '하는', '하냐', '한다', '해도', '인가', '됩니까',
             '입니까', '일까', '가요', '나요', '이다', '이며', '이지', '있나', '했나', '을', '를', '은', '는', '의', '에', '가', '이')
# Verbs are not conclusions: they only improve retrieval relevance.
_ACTIONS = ('감정평가', '지정', '정산', '매립', '시정', '허가', '인가', '승인', '의제',
            '변경', '준공검사', '사용승인', '소유권', '귀속', '기부채납', '수립', '결정',
            '신청', '부과', '취소', '요청', '명령', '지급', '보상', '분양', '시설', '공작물')


def normalize(s: str) -> str:
    return re.sub(r'[^0-9가-힣a-z]', '', (s or '').lower())


def family_names(question: str, old_preferred=(), *, max_families=3) -> list[str]:
    """Find explicitly referenced Act(s), then the parent Act for known legal concepts.

    Avoid treating a single arbitrary noun as a valid statute title.
    """
    found = []
    q = normalize(question)
    for alias, long_name in LAW_ALIASES:
        if normalize(alias) in q and long_name not in found:
            found.append(long_name)
    for trigger, name in old_preferred:
        if normalize(trigger) in q and name not in found:
            found.append(name)
    # Quoted full Act names and unambiguous short titles such as 정보공개법.
    for quoted in re.findall(r'[「〈<]([^」〉>]{2,75})[」〉>]', question):
        candidate = re.sub(r'\s+(?:시행령|시행규칙)$', '', quoted.strip())
        if (candidate.endswith(('법', '법률', '특별법'))) and candidate not in found:
            found.insert(0, candidate)
    for match in re.finditer(r'(?<![가-힣])([가-힣]{2,19}(?:특별법|기본법|법률|법))(?:에서|에|상|의|은|는|으로|에선|부터)?', question):
        candidate = match.group(1)
        if (candidate not in found and candidate not in {'법률','특별법','기본법'}
                and not any(normalize(alias)==normalize(candidate)
                            and long_name in found for alias,long_name in LAW_ALIASES)):
            found.append(candidate)
    return found[:max_families]


def family_queries(question: str, old_preferred=(), fallback: str = '', *, max_families=3) -> list[str]:
    families = family_names(question, old_preferred, max_families=max_families)
    if not families:
        # Generic questions still attempt official title search.
        return [fallback] if fallback else []
    return list(dict.fromkeys(
        f'{name}{suffix}' for name in families for suffix in ('', ' 시행령', ' 시행규칙')
    ))


def law_level(title: str) -> str:
    if title.endswith('시행규칙'):
        return '시행규칙'
    if title.endswith('시행령'):
        return '시행령'
    return '법률'


def article_number(el) -> str:
    def text(name):
        for x in el.iter():
            if x.tag.split('}')[-1] == name and x.text:
                return x.text.strip()
        return ''
    num = text('조문번호').lstrip('0')
    if not num:
        return ''
    suffix = text('조문가지번호').lstrip('0')
    return num + ('의' + suffix if suffix else '')


def question_terms(question: str) -> list[str]:
    terms = []
    def add(t):
        x=normalize(t)
        if len(x) >= 2 and x not in _STOP and x not in terms:
            terms.append(x)
    for v in _ACTIONS:
        if v in question:
            add(v)
    for raw in re.findall(r'[가-힣]{2,26}|[0-9]{2,}', question):
        word = raw
        for suffix in _SUFFIXES:
            if word.endswith(suffix) and len(word) > len(suffix) + 1:
                word=word[:-len(suffix)];break
        if len(word)>=3:
            add(word)
    # A user saying '감정평가사' can be answered from '감정평가법인등'.
    if '감정평가' in question:
        add('감정평가')
    return terms[:22]


def _article_text(el) -> str:
    parts=[]
    for item in el.iter():
        tag = item.tag.split('}')[-1]
        value = (item.text or '').strip()
        if tag in {'조문내용', '항내용', '호내용', '목내용'} and value and value not in parts:
            parts.append(value)
    return '\n'.join(parts) if parts else '\n'.join(t.strip() for t in el.itertext() if t and t.strip())


def article_score(question: str, title: str, number: str, article: str, topic_weights=None) -> float:
    """Predict useful *evidence*, not the legal correctness of a conclusion."""
    norm = normalize(article)
    terms = question_terms(question)
    hits = 0
    score = 0.0
    for t in terms:
        if t and t in norm:
            hits += 1
            score += (7.0 if t in _ACTIONS else 3.0) + (min(norm.count(t), 3)-1)*0.6
    # Exclude generic matches of only one common word unless the cited article
    # is explicitly requested by number or known to contain a direct topic.
    match = re.search(r'제\s*(\d+)\s*조(?:의\s*(\d+))?', question)
    if match and (match.group(1).lstrip('0')+('의'+match.group(2).lstrip('0') if match.group(2) else '')) == number:
        score += 200
    if topic_weights:
        score += topic_weights.get(number, 0)
    if hits >= 2:
        score += 12.0 + min(hits,5)*1.3
    # A question specifically asking WHO needs a sentence with actor + action.
    if any(w in question for w in ('누가', '누구', '어느 기관', '누구인지', '주체')):
        for action in ('지정','허가','승인','부과','시정','명령','결정','수립'):
            if action in question and any(re.search(rf'[^.\n]{{2,55}}{action}', line) for line in article.split('\n')):
                score += 3
                break
    return score


def select_article_text(el, question: str, limit: int = 1700) -> str:
    raw = _article_text(el)
    if len(raw) <= limit:
        return raw
    chunks = [p for p in raw.splitlines() if p.strip()]
    if not chunks:
        return raw[:limit]
    terms = question_terms(question)
    scored=[]
    for idx, line in enumerate(chunks):
        line_n = normalize(line)
        score = sum(4 if t in _ACTIONS else 2 for t in terms if t in line_n)
        scored.append((score, idx, line))
    scored.sort(key=lambda x:(-x[0],x[1]))
    chosen = {0}
    remaining = limit - len(chunks[0])-2
    for score,idx,line in scored:
        if idx in chosen or remaining <= 0:
            continue
        if score < 1 and len(chosen)>2:
            break
        if len(line)+2 <= remaining:
            chosen.add(idx)
            remaining-=len(line)+2
    return '\n'.join(chunks[idx] for idx in sorted(chosen))[:limit]


def extract_relevant_articles(root, question: str, title: str, *, max_articles=2, topic_weights=None) -> list[dict]:
    ranked=[]
    for el in root.iter():
        if el.tag.split('}')[-1] != '조문단위':
            continue
        number=article_number(el)
        if not number:
            continue
        article = _article_text(el)
        score = article_score(question,title,number,article,topic_weights)
        if score > 0:
            ranked.append((score,number,el))
    ranked.sort(key=lambda t:(-t[0],int(t[1].split('의')[0])))
    out=[]
    for score,number,el in ranked[:max_articles]:
        name = '제' + number.replace('의','조의',1) + ('' if '의' in number else '조')
        text = select_article_text(el, question)
        out.append({'article_number': number, 'article_label': name,
                    'body': f'{name}\n{text}', 'retrieval_score': round(score,1)})
    return out
