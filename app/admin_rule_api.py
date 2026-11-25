"""MOLEG administrative rules (훈령/예규/고시/지침) search adapter.

Official APIs:
  GET https://www.law.go.kr/DRF/lawSearch.do?target=admrul
  GET https://www.law.go.kr/DRF/lawService.do?target=admrul

Requests are bounded, read-only, and fixed to the official API origin.
Administrative rules are NOT treated as equivalent to Acts or Decrees.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote

import httpx
from defusedxml import ElementTree as ET
from app.statutory_retrieval import extract_relevant_articles, question_terms, normalize

LOG = logging.getLogger('landlex.admrul')
SEARCH = 'https://www.law.go.kr/DRF/lawSearch.do'
DETAIL = 'https://www.law.go.kr/DRF/lawService.do'
MAX_SEARCHES = 3
MAX_DETAILS = 5

# Broad subject vocabulary, NOT hard-coded answers. These are optional
# discovery cues when a question does not explicitly name an administrative rule.
SUBJECTS = ('산업입지', '산업단지', '산업집적', '공유수면', '경제자유구역',
            '개발행위', '도시계획', '도시관리', '환경영향평가', '토지보상',
            '건설기술', '항만', '하천', '도로', '지반', '매립')
STOP = {'어떻게','가능','있는','없는','하는','하려면','한다고','개발계획','실시계획',
        '변경','관련','법령','확인','기준','절차','해당','검토','되나','인가','누가'}


def search_terms(question: str, limit: int = MAX_SEARCHES) -> list[tuple[str, str]]:
    """(keyword, search scope) tuples. Scope 1 title; scope 2 body.

    Avoid unrestricted '*' searches and reject candidate sentences or dates.
    """
    terms: list[tuple[str,str]] = []
    def add(term: str, scope: str):
        term=term.strip()
        if 2 <= len(term) <= 25 and (term,scope) not in terms:
            terms.append((term,scope))
    for subject in SUBJECTS:
        if subject in question:
            add(subject, '1')
    for word in re.findall(r'[가-힣]{2,18}',question):
        if any(p in word for p in ('지침','고시','규정','훈령','예규')) and word not in STOP:
            for suffix in ('에서는','에서','에는','으로','에','의','을','를','이','가'):
                if word.endswith(suffix) and len(word)>len(suffix)+2:
                    word=word[:-len(suffix)]
                    break
            add(word, '1')
    if not terms:
        for token in question_terms(question):
            if token not in STOP and len(token)>=3:
                add(token, '1')
                if len(terms)>=2:break
    # A narrow body search can find an administrative rule whose title omits
    # the question term (e.g. 관리기본계획 in 산업단지 관리지침).
    if terms and ('지침' in question or '규정' in question or '관리기본계획' in question):
        if '관리기본계획' in question: add('관리기본계획','2')
        elif '실시계획' in question: add('실시계획','2')
    return terms[:limit]


def _tag(element) -> str:
    return element.tag.split('}')[-1]


def _child_text(element, tagname: str) -> str:
    for child in element.iter():
        if _tag(child)==tagname and child.text:
            return child.text.strip()
    return ''


def parse_list(xml: bytes) -> list[dict]:
    """List output has multiple nested XML variants; use only direct fields."""
    root=ET.fromstring(xml)
    records=[]; seen=set()
    for el in root.iter():
        direct={_tag(ch):(ch.text or '').strip() for ch in el if len(ch)==0}
        serial=direct.get('행정규칙일련번호') or direct.get('admrul id')
        title=direct.get('행정규칙명')
        if not serial or not str(serial).isdigit() or not title or serial in seen:
            continue
        seen.add(serial)
        records.append({'serial':str(serial),'title':title,
            'type':direct.get('행정규칙종류',''),
            'organization':direct.get('소관부처명',''),
            'issued_date':direct.get('발령일자',''),
            'effective_date':direct.get('시행일자',''),
            'current':direct.get('현행연혁구분',''),
            'link':direct.get('행정규칙상세링크','')})
    return records


def _date(value: str) -> str:
    v=re.sub(r'[^0-9]','',value or '')
    return f'{v[:4]}-{v[4:6]}-{v[6:8]}' if len(v)>=8 else ''


def _rank(question: str, rec: dict, *, body: str = '') -> float:
    q=normalize(question)
    title=normalize(rec['title'])
    tokens=[normalize(t) for t in question_terms(question) if len(t)>=2]
    score=sum(8 if t in title else 0 for t in tokens)
    score+=sum(2 if t in normalize(body[:8000]) else 0 for t in tokens)
    for subject in SUBJECTS:
        ns=normalize(subject)
        if ns in q and ns in title: score+=12
    if title in q:score+=40
    return score


def _fallback_body(root, question: str) -> str:
    """Unstructured provisions: keep relevant paragraph(s), not unrelated metadata."""
    content_tags={'조문내용','항내용','호내용','목내용','부칙내용'}
    paragraphs=[]; seen=set()
    for el in root.iter():
        s=(el.text or '').strip()
        if _tag(el) in content_tags and s and s not in seen:
            seen.add(s);paragraphs.append(s)
    if not paragraphs:
        # Some administrative rules use a plain text field, not 조문단위.
        for el in root.iter():
            if _tag(el) in ('내용','본문','행정규칙내용','조문내용'):
                s=(el.text or '').strip()
                if s and s not in seen:seen.add(s);paragraphs.append(s)
    terms=[normalize(t) for t in question_terms(question) if len(t)>2]
    ranked=sorted(enumerate(paragraphs),key=lambda it:(-sum(t in normalize(it[1]) for t in terms),it[0]))
    if not ranked:return ''
    picked=[];remaining=2000
    for pos,text in ranked:
        if len(text)>1600: text=text[:1600]
        if len(text)+1<=remaining:
            picked.append((pos,text));remaining-=len(text)+1
        if len(picked)>=5:break
    return '\n'.join(t for _,t in sorted(picked))


def parse_detail(xml: bytes, question: str, rec: dict) -> list[dict]:
    root=ET.fromstring(xml)
    title=_child_text(root,'행정규칙명') or rec['title']
    issued=_date(_child_text(root,'발령일자') or rec['issued_date'])
    effective=_date(_child_text(root,'시행일자') or rec['effective_date'])
    organization=_child_text(root,'소관부처명') or rec['organization'] or '발령기관 미확인'
    kind=_child_text(root,'행정규칙종류') or rec['type']
    serial=rec['serial']
    link=f'https://www.law.go.kr/admRulInfoP.do?admRulSeq={int(serial)}'
    article_items=extract_relevant_articles(root, question,title,max_articles=2)
    results=[]
    for article in article_items:
        body=article.get('body','').strip()
        if not body:continue
        label=article.get('article_label','')
        results.append({'id':f'admrul-{serial}-{article.get("article_number", "body")}',
            'kind':'행정규칙','title':title+(f' {label}' if label else ''),
            'law_level':'행정규칙','law_title':title,
            'article_number':article.get('article_number',''),
            'case_number':'','organization':organization,'issued_date':issued,
            'effective_date':effective,'url':link,'body':body[:2400],
            'source_note':f'법제처 현행 행정규칙 ({kind}; 발령 {issued or "일자 미확인"}; 시행 {effective or "일자 미확인"}). 행정규칙의 법적 효력은 별도 검토'})
    if not results:
        body=_fallback_body(root,question)
        if body:
            results.append({'id':f'admrul-{serial}', 'kind':'행정규칙',
                'title':title, 'law_level':'행정규칙','law_title':title,
                'article_number':'','case_number':'','organization':organization,
                'issued_date':issued,'effective_date':effective,'url':link,
                'body':body[:2400],
                'source_note':f'법제처 현행 행정규칙 ({kind}; 발령 {issued or "일자 미확인"}; 시행 {effective or "일자 미확인"}). 행정규칙의 법적 효력은 별도 검토'})
    return results


async def search_administrative_rules(client: httpx.AsyncClient, oc: str,
                                      question: str, *, deep: bool=True) -> tuple[list[dict], bool]:
    """Bounded official API retrieval. Returns (records, any_api_failures).

    Failures are isolated so that Act/Decree queries still succeed. Never log
    URLs (which contain the OC credential), raw XML, or user questions.
    """
    terms=search_terms(question, 3 if deep else 2)
    if not oc or not terms:return [],False
    sem=asyncio.Semaphore(3)
    async def search_one(term,scope):
        try:
            async with sem:
                r=await client.get(SEARCH,params={'OC':oc,'target':'admrul',
                    'type':'XML','nw':'1','search':scope,'query':term,
                    'display':'40','page':'1','sort':'ddes'},timeout=10)
            r.raise_for_status()
            if not r.content.lstrip().startswith(b'<') or b'<html' in r.content[:300].lower():
                raise ValueError('Non-XML response')
            return parse_list(r.content),False
        except (httpx.HTTPError,ValueError,ET.ParseError) as exc:
            LOG.warning('Administrative rule list unavailable (%s)',type(exc).__name__)
            return [],True
    listed=await asyncio.gather(*(search_one(term,scope) for term,scope in terms))
    failures=any(f for _,f in listed)
    unique={}
    for records,_ in listed:
        for rec in records:
            serial=rec['serial'];rank=_rank(question,rec)
            if serial not in unique or rank>unique[serial][0]:unique[serial]=(rank,rec)
    # Only request the most plausible five official full texts.
    choices=[x[1] for x in sorted(unique.values(),key=lambda x:-x[0])[:MAX_DETAILS]]
    async def detail_one(rec):
        try:
            async with sem:
                r=await client.get(DETAIL,params={'OC':oc,'target':'admrul',
                    'type':'XML','ID':rec['serial']},timeout=10)
            r.raise_for_status()
            if not r.content.lstrip().startswith(b'<') or b'<html' in r.content[:300].lower():
                raise ValueError('Non-XML response')
            return parse_detail(r.content,question,rec),False
        except (httpx.HTTPError,ValueError,ET.ParseError) as exc:
            LOG.warning('Administrative rule detail unavailable (%s)',type(exc).__name__)
            return [],True
    detailed=await asyncio.gather(*(detail_one(rec) for rec in choices))
    failures=failures or any(err for _,err in detailed)
    records=[item for result,_ in detailed for item in result]
    records.sort(key=lambda item:-_rank(question,{'title':item['title']},body=item['body']))
    return records[:6],failures
