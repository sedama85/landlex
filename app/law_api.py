"""Official Korean law.go.kr Open API adapter.

Supported targets from official guides:
  law         - law list and full text
  expc        - MOLEG statutory interpretations
  molitCgmExpc - MOLIT ministry interpretations
All remote requests go to the fixed law.go.kr origin (no SSRF).
"""
import asyncio
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
import httpx
from defusedxml import ElementTree as SafeET
from app.statutory_retrieval import family_queries, law_level, extract_relevant_articles

API_ROOT = 'https://www.law.go.kr/DRF/'
TAGS = {
    'law': ['법령', 'law'],
    'expc': ['법령해석례', 'expc'],
    'molitCgmExpc': ['법령해석', 'molitCgmExpc'],
    'molegCgmExpc': ['법령해석', 'molegCgmExpc'],
}
SERIAL_KEYS = {
    'law': ('법령일련번호', '법령ID'),
    'expc': ('법령해석례일련번호',),
    'molitCgmExpc': ('법령해석일련번호',),
    'molegCgmExpc': ('법령해석일련번호',),
}
STOPWORDS = {'어떻게','법령','대한','가능','있는','없는','하는','하려면','변경하려면','인가','되는','알려줘','확인','해야','사항','여부','관련','관한','있나','것이','해줘','해당','인지','공사','사업'}
ALIAS = {
    '경자구역': '경제자유구역', '경자법': '경제자유구역', '국계법': '국토의 계획',
    '유치업종': '유치산업', '유치산업': '산업유치계획',
    '산집법': '산업집적활성화', '공유수면법': '공유수면',
}


def _plan_concepts(question: str) -> bool:
    """Recognize statutory parent/child concepts and common pre-2020 spelling.

    A district unit plan is adopted as an urban/county management plan under
    National Land Planning Act art. 50. Relevance does not establish that a
    particular parcel is subject to an adopted district unit plan.
    """
    plain = re.sub(r'[^0-9a-z가-힣]', '', question.lower())
    return any(x in plain for x in ('도시관리계획', '도시군관리계획', '지구단위계획'))


def keywords(question: str):
    result = []
    # Expand the legal hierarchy before generic words consume the keyword budget.
    if _plan_concepts(question):
        result.extend(['도시·군관리계획', '지구단위계획', '도시관리계획'])
    if '개발행위' in question:
        result.append('개발행위허가')
    for short,long in ALIAS.items():
        if short in question and long not in result:
            result.append(long)
    # Prioritize meaningful compound words, not arbitrary full sentences.
    for phrase in ['경제자유구역','산업단지','국토의 계획','개발계획','실시계획','유치업종','법령해석','개발행위','공유수면','지구단위계획','도시관리계획','도시·군관리계획','관리기본계획', '유치산업', '산업유치계획']:
        if phrase in question and phrase not in result:
            result.append(phrase)
    for token in re.findall(r'[가-힣A-Za-z0-9]{2,}', question):
        token = re.sub(r'(에서는|이라면|으로는|에서|에게|부터|까지|으로|하는|하려면|해도|하게|인가|은|는|이|가|을|를|에|의|도)$', '', token)
        if len(token) >= 2 and token not in STOPWORDS and token not in result:
            result.append(token)
    return result[:8]


def _text(elem, name):
    for child in elem.iter():
        if child.tag.split('}')[-1] == name and child.text:
            return child.text.strip()
    return ''


def _records_from_xml(raw: bytes, target: str):
    root = SafeET.fromstring(raw)
    # Records have a serial id and a recognizable title. Be defensive about
    # root/tag differences between the three official datasets.
    serial_key = SERIAL_KEYS[target][0]
    candidates = []
    for elem in root.iter():
        direct = {ch.tag.split('}')[-1]: (ch.text or '').strip() for ch in elem if len(ch)==0}
        if serial_key in direct:
            candidates.append(direct)
    # Avoid accidental nested duplicate records.
    seen = set()
    result = []
    for rec in candidates:
        ident = rec.get(serial_key)
        if ident in seen:
            continue
        seen.add(ident)
        result.append(rec)
    return result


# Keep primary law + regulation provisions ahead of broad, often irrelevant interpretation hits.
PREFERRED_LAWS = (
    ('경제자유구역', '경제자유구역의 지정 및 운영에 관한 특별법'),
    ('국토의 계획', '국토의 계획 및 이용에 관한 법률'),
    ('도시관리계획', '국토의 계획 및 이용에 관한 법률'),
    ('도시·군관리계획', '국토의 계획 및 이용에 관한 법률'),
    ('도시군관리계획', '국토의 계획 및 이용에 관한 법률'),
    ('지구단위계획', '국토의 계획 및 이용에 관한 법률'),
    ('개발행위', '국토의 계획 및 이용에 관한 법률'),
    ('도시개발', '도시개발법'),
    ('산업집적', '산업집적활성화 및 공장설립에 관한 법률'),
    ('공유수면', '공유수면 관리 및 매립에 관한 법률'),
)


def _article_num(el):
    number = _text(el, '조문번호').lstrip('0') or '0'
    suffix = _text(el, '조문가지번호').lstrip('0')
    return f'{number}의{suffix}' if suffix else number


def _law_topics(question, title):
    if '경제자유구역' in title and any(w in question for w in ('유치업종','유치산업','산업유치','업종추가','업종 변경')):
        if '시행령' in title:
            return {'5의2': 100, '5': 15}
        return {'6': 85, '7': 95}
    if '국토의 계획 및 이용에 관한 법률' in title and _plan_concepts(question) and '개발행위' in question:
        # Legal hierarchy: art.50 (district-unit plan -> management plan),
        # art.58(1)2 (permit must conform to management plan).
        if '시행령' in title:
            return {'56': 120, '55': 30}
        return {'58': 200, '50': 190, '2': 100, '56': 70, '52': 60}
    return {}


def _compact_article(el, question, title, max_chars=2450):
    """Preserve article heading and targeted paras/items, instead of losing item 6
    to a blind [:4500] truncation of a long regulation article.
    """
    sections=[]
    allowed={'조문내용','항내용','호내용','목내용'}
    for item in el.iter():
        tag=item.tag.split('}')[-1]
        txt=(item.text or '').strip()
        if tag in allowed and txt:
            sections.append(txt)
    # Some law XML variants keep article content without child sections.
    if not sections:
        sections=[t.strip() for t in el.itertext() if t and t.strip()]
    if not sections: return ''
    if len('\n'.join(sections)) <= max_chars:
        return '\n'.join(sections)
    scoring_terms = [w for w in keywords(question) if len(w)>2]
    if '유치업종' in question or '유치산업' in question:
        scoring_terms += ['산업유치계획','유치산업','입주업종','관리기본계획','핵심전략산업','경미한 사항']
    # Always retain article header and context; rank the body lines by direct
    # relevance while preserving their relative order in the statute.
    rated=[]
    for idx, text in enumerate(sections[1:],1):
        score=sum((4 if term in ('유치산업','입주업종','산업유치계획') else 1) for term in scoring_terms if term in text)
        rated.append((score,idx,text))
    rated.sort(key=lambda x:(-x[0],x[1]))
    picked={0}
    remaining=max_chars-len(sections[0])-2
    for score,idx,txt in rated:
        if score==0 and len(picked)>=4:
            break
        if len(txt)+2<=remaining:
            picked.add(idx); remaining-=len(txt)+2
    return '\n'.join(sections[i] for i in sorted(picked))


def _flatten_content(root: ET.Element, target: str, question: str, title: str = ''):
    if target == 'law':
        preferences=_law_topics(question,title)
        # Keep the controlling provisions in the per-source AI context; otherwise
        # a long unrelated article can push art.50 below the 2,200-char limit.
        focus = bool(_plan_concepts(question) and '개발행위' in question and
                     '국토의 계획 및 이용에 관한 법률' in title)
        scored=[]
        kw=[w for w in keywords(question) if len(w)>2]
        for el in root.iter():
            if el.tag.split('}')[-1] != '조문단위':
                continue
            number=_article_num(el)
            content=_compact_article(el,question,title, max_chars=750 if focus else 2450)
            if not content:
                continue
            matched=sum((3 if w in ('유치산업','산업유치계획','유치업종') else 1) for w in kw if w in content)
            rank=preferences.get(number,0)+matched
            if rank:
                scored.append((rank,number,content))
        scored.sort(key=lambda x:x[0],reverse=True)
        # Short enough to remain inside the AI source-context limit for each statute.
        result=[]
        total=0
        for score,num,body in scored[:5]:
            display_num = (f'제{num.split("의")[0]}조의{num.split("의")[1]}' if '의' in num else f'제{num}조')
            chunk=f'{display_num}\n{body}'
            if total+len(chunk)>4200:
                break
            result.append(chunk);total+=len(chunk)
        return '\n\n'.join(result)
    fields = ['질의요지','회답','이유','관련법령', '질의배경', '관련법령및판례']
    return '\n\n'.join(f'{field}: {_text(root, field)}' for field in fields if _text(root, field))[:15000]



def _official_link(target, ident, title=""):
    # Link to public document or search page. Never expose the OC API credential.
    from urllib.parse import quote
    if target == 'law' and title:
        return 'https://www.law.go.kr/법령/' + quote(title, safe='')
    if target == 'expc':
        return f'https://www.law.go.kr/LSW/expcInfoP.do?expcSeq={int(ident)}'
    return 'https://www.law.go.kr/expcSc.do'



async def _request_xml(client, endpoint, params):
    r = await client.get(urljoin(API_ROOT, endpoint), params=params, timeout=10.0)
    r.raise_for_status()
    # Protect against HTML login/error pages being mistaken for documents.
    if not r.content.lstrip().startswith(b'<') or b'<html' in r.content[:400].lower():
        raise ValueError('법제처 API에서 XML 대신 오류 페이지를 반환했습니다.')
    return r.content


def _best_law_records(records, query, max_results):
    # The official list may return Acts, enforcement decrees and regulations.
    # Prefer exact names before remote fetch, not merely the first 3 records.
    ranked=[]
    for rec in records:
        title=rec.get('법령명한글','')
        if not title: continue
        if title==query: rank=100
        elif title in (query+' 시행령',query+' 시행규칙'): rank=90
        elif query in title: rank=50
        else: rank=0
        if rank:
            ranked.append((rank, rec))
    ranked.sort(key=lambda pair:(-pair[0],len(pair[1].get('법령명한글',''))))
    return [rec for _,rec in ranked[:max_results]]


async def _search_target(client, oc, target, word, question, max_results=3):
    try:
        raw = await _request_xml(client, 'lawSearch.do', {
            'OC':oc, 'target':target, 'type':'XML', 'search':'1',
            'query':word, 'display':'50' if target=='law' else '10', 'page':'1',
        })
        recs = _records_from_xml(raw, target)
        if target == 'law':
            recs = _best_law_records(recs,word,max_results)
        else:
            recs = recs[:max_results]
        results = []
        for rec in recs:
            serial = next((rec.get(k) for k in SERIAL_KEYS[target] if rec.get(k)), None)
            if not serial or not str(serial).isdigit():
                continue
            title = rec.get('법령명한글') or rec.get('안건명') or rec.get('법령해석례명') or rec.get('법령해석명') or ''
            if not title:
                continue
            try:
                # Critical distinction in the MOLEG API: list `법령일련번호` is MST,
                # while detail `ID` must be `법령ID` (see official API guide).
                params={'OC':oc, 'target':target, 'type':'XML'}
                if target=='law':
                    law_id=rec.get('법령ID')
                    if law_id and str(law_id).isdigit():
                        params['ID']=str(law_id)
                    else:
                        params['MST']=str(serial)
                else:
                    params['ID']=str(serial)
                detail = await _request_xml(client, 'lawService.do', params)
                root = SafeET.fromstring(detail)
                if target == "law":
                    articles = extract_relevant_articles(
                        root, question, title, max_articles=2,
                        topic_weights=_law_topics(question, title))
                    body = articles[0]['body'] if articles else ''
                else:
                    articles = []
                    body = _flatten_content(root, target, question, title)
            except (httpx.HTTPError, ValueError, ET.ParseError):
                body = ''
                articles = []
            if not body:
                continue  # no heading-only sources presented as evidence
            if target == "law":
                for art in articles:
                    results.append({
                        'id': f'law-{serial}-{art["article_number"]}',
                        'kind': '법령',
                        'title': f'{title} {art["article_label"]}',
                        'law_title': title,
                        'law_level': law_level(title),
                        'article_number': art['article_number'],
                        'retrieval_score': art['retrieval_score'],
                        'organization': rec.get('소관부처명') or '법제처 국가법령정보센터',
                        'issued_date': rec.get('시행일자') or '',
                        'url': _official_link(target, serial, title),
                        'body': art['body'],
                        'source_note': '법제처 현행법령 해당 조문',
                    })
                continue
            results.append({
                'id':f'{target}-{serial}',
                'kind': ('법령' if target == 'law' else '법제처 해석례' if target == 'expc' else '법제처 법령해석' if target == 'molegCgmExpc' else '국토부 질의회신'),
                'title':title,
                'organization':rec.get('해석기관명') or rec.get('소관부처명') or '법제처 국가법령정보센터',
                'issued_date': rec.get('해석일자') or rec.get('회신일자') or rec.get('시행일자') or '',
                'url':_official_link(target, serial, title),
                'body':body,
                'source_note':'법제처 국가법령정보 공동활용 API',
            })
        return results
    except (httpx.HTTPError, ValueError, ET.ParseError):
        return []



# -------- Expanded official-interpretation search (v2) --------
# Fixed, allowlisted API targets only. No user-provided URLs or API keys exposed.
# A question runs multiple *bounded* title/body/number searches, then re-ranks
# the candidates after fetching the authentic full text.
INTERPRETATION_TARGETS = ('expc', 'molegCgmExpc', 'molitCgmExpc')
CASE_NUMBER = re.compile(r'(?<![0-9])([0-9]{2})\s*[-‐‑–—]\s*([0-9]{4})(?![0-9])')
SEARCH_TERMS = (
    '감정평가업자', '감정평가', '유치산업', '유치업종', '입주업종',
    '도시관리계획', '도시·군관리계획', '지구단위계획', '개발행위허가',
    '산업유치계획', '관리기본계획', '공유수면', '경제자유구역',
    '지구단위계획', '매립실시계획', '실시계획', '개발계획',
    '개발행위', '산업단지', '매립', '의제', '변경승인',
    '정산', '분양', '준공검사', '선시공', '기반시설', '어업피해',
)
TERM_EQUIVALENTS = {
    '유치업종': ('유치산업', '입주업종'),
    '경자구역': ('경제자유구역',),
    '경자법': ('경제자유구역',),
    '산집법': ('산업집적', '입주업종'),
    '감정평가업자': ('감정평가',),
    '매립실시계획': ('매립', '실시계획'),
}
GENERIC_TERMS = {'개발계획','실시계획','변경승인','의제','매립','산업단지','기반시설'}

def _case_number(question: str) -> str:
    match = CASE_NUMBER.search(question)
    if match:
        return ''.join(match.groups())
    # Accept the six-digit normalized form only when explicitly identified
    # as an interpretation case number, not incidental dates or amounts.
    m = re.search(r'(?:안건번호|해석번호|해석례번호)\s*[:：]?\s*([0-9]{6})(?![0-9])', question)
    return m.group(1) if m else ''

def _interpretation_terms(question: str, deep: bool=True) -> list[str]:
    terms=[]
    def add(term):
        if term and len(term)>=2 and term not in terms:
            terms.append(term)
    for term in SEARCH_TERMS:
        if term in question:
            add(term)
    for short, equivalent in TERM_EQUIVALENTS.items():
        if short in question:
            for term in equivalent:
                add(term)
    for term in keywords(question):
        if not term.isdigit():
            add(term)
    # Short subject-specific phrases are better than very long legal names.
    terms.sort(key=lambda t: (t in GENERIC_TERMS, -len(t)))
    distinct=[]
    for term in terms:
        if any(term in already or already in term for already in distinct):
            continue
        distinct.append(term)
    return distinct[:(4 if deep else 2)]

def _normalize(value: str) -> str:
    return re.sub(r'[^0-9가-힣a-z]', '', (value or '').lower())

def _candidate_score(question: str, rec: dict, searched_body=False) -> int:
    number = _normalize(rec.get('안건번호') or rec.get('case_number') or '')
    explicit = _case_number(question)
    if explicit and number == explicit:
        return 10000
    title = _normalize(rec.get('안건명') or rec.get('법령해석례명') or rec.get('법령해석명') or '')
    score=5 if searched_body else 0
    for term in _interpretation_terms(question):
        key=_normalize(term)
        if key and key in title:
            score += (9 if term not in GENERIC_TERMS else 4)
    return score

def _result_score(question: str, rec: dict) -> int:
    score = _candidate_score(question, rec)
    body = _normalize(rec.get('body','')[:15000])
    for term in _interpretation_terms(question):
        key=_normalize(term)
        if key in body:
            score += (4 if term not in GENERIC_TERMS else 2)
    return score

async def _interpretation_list(client, sem, oc, target, word='', scope=1, page=1, case=''):
    params = {
        'OC': oc, 'target': target, 'type': 'XML',
        'display': '40', 'page': str(page), 'sort': 'ddes',
    }
    if case:
        params['itmno']=case
    else:
        params.update({'search': str(scope), 'query': word})
    try:
        async with sem:
            raw = await _request_xml(client, 'lawSearch.do', params)
        records = _records_from_xml(raw, target)
        root = SafeET.fromstring(raw)
        count_text = _text(root,'totalCnt') or '0'
        total = int(count_text) if count_text.isdigit() else len(records)
        return records, total, None
    except (httpx.HTTPError, ValueError, ET.ParseError, AttributeError) as exc:
        # Only exception type is logged; never log OC or request URI.
        import logging
        logging.getLogger('landlex.law').warning('Interpretation index request %s failed: %s', target, type(exc).__name__)
        return [], 0, type(exc).__name__

async def _interpretation_detail(client, sem, oc, target, rec):
    serial = rec.get(SERIAL_KEYS[target][0], '')
    if not str(serial).isdigit():
        return None
    try:
        async with sem:
            raw = await _request_xml(client, 'lawService.do', {
                'OC':oc, 'target':target, 'type':'XML', 'ID':str(serial)
            })
        root=SafeET.fromstring(raw)
        title=rec.get('안건명') or rec.get('법령해석례명') or rec.get('법령해석명') or _text(root,'안건명')
        body=_flatten_content(root,target,'',title)
        if not body or not title:
            return None
        case=rec.get('안건번호') or _text(root,'안건번호') or ''
        kind={'expc':'법제처 해석례', 'molegCgmExpc':'법제처 법령해석',
              'molitCgmExpc':'국토부 질의회신'}[target]
        org=(rec.get('회신기관명') or rec.get('해석기관명') or
             _text(root,'해석기관명') or ('국토교통부' if target=='molitCgmExpc' else '법제처'))
        return {
            'id': f'{target}-{serial}',
            'kind':kind, 'title':title, 'case_number':case,
            'organization':org,
            'issued_date':rec.get('해석일자') or rec.get('회신일자') or _text(root,'해석일자') or '',
            'url':_official_link(target,serial,title),
            'body':body,
            'source_note':'법제처 국가법령정보 공동활용 API',
        }
    except (httpx.HTTPError, ValueError, ET.ParseError, AttributeError) as exc:
        import logging
        logging.getLogger('landlex.law').warning('Interpretation detail %s failed: %s', target, type(exc).__name__)
        return None

async def _search_interpretations(client, oc, question, *, deep=True, targets=INTERPRETATION_TARGETS):
    sem=asyncio.Semaphore(6)
    terms=_interpretation_terms(question, deep)
    case=_case_number(question)
    jobs=[]
    for target in targets:
        if case:
            jobs.append((target,'',0,1,case))
        for term in terms[:(4 if deep else 2)]:
            jobs.append((target,term,1,1,''))
        for term in terms[:(3 if deep else 1)]:
            jobs.append((target,term,2,1,''))
    if not jobs:
        return [], []
    fetched=await asyncio.gather(*[
        _interpretation_list(client,sem,oc,target,term,scope,page,number)
        for target,term,scope,page,number in jobs
    ])
    failures=[]
    candidates={}
    for (target,term,scope,page,number),(items,total,error) in zip(jobs,fetched):
        if error:
            failures.append(target)
        for rec in items:
            serial=rec.get(SERIAL_KEYS[target][0],'')
            if not str(serial).isdigit():
                continue
            key=(target,str(serial))
            score=_candidate_score(question,rec,searched_body=scope==2)
            old=candidates.get(key)
            if old is None or score>old[0]:
                candidates[key]=(score,target,rec)
    # A second page helps recall for broad, high-result queries but is strictly
    # bounded: at most four follow-on requests, not unbounded crawling.
    if deep and not case:
        next_jobs=[]
        for (target,term,scope,page,number),(items,total,error) in zip(jobs,fetched):
            if total>40 and scope==2 and len(next_jobs)<4:
                next_jobs.append((target,term,scope,2,''))
        if next_jobs:
            more=await asyncio.gather(*[
                _interpretation_list(client,sem,oc,target,term,scope,page,number)
                for target,term,scope,page,number in next_jobs
            ])
            for (target,term,scope,page,number),(items,total,error) in zip(next_jobs,more):
                if error: failures.append(target)
                for rec in items:
                    serial=rec.get(SERIAL_KEYS[target][0],'')
                    if not str(serial).isdigit(): continue
                    key=(target,str(serial)); score=_candidate_score(question,rec,True)
                    if key not in candidates or score>candidates[key][0]:
                        candidates[key]=(score,target,rec)
    ranked=sorted(candidates.values(), key=lambda x:-x[0])
    # Fairly reserve candidates from each official source, so one broad API
    # does not crowd out lawmaker opinions from another dataset.
    picked=[]; per_target={t:0 for t in INTERPRETATION_TARGETS}
    candidate_budget=27 if deep else 14
    for value in ranked:
        if per_target[value[1]]>= (11 if deep else 6):
            continue
        picked.append(value); per_target[value[1]]+=1
        if len(picked)>=candidate_budget:
            break
    full=await asyncio.gather(*[
        _interpretation_detail(client,sem,oc,target,rec)
        for _score,target,rec in picked
    ])
    results=[( _result_score(question, record), record) for record in full if record]
    # Avoid duplicate records appearing from both official interpretation APIs.
    unique=[]; seen=set()
    for score,record in sorted(results,key=lambda x:-x[0]):
        number=_normalize(record.get('case_number',''))
        signature= ('case',number,_normalize(record['title'])) if number else ('title', _normalize(record['title']))
        if signature in seen: continue
        seen.add(signature);unique.append(record)
    return unique[:(20 if deep else 10)], failures


async def search_official(question, oc, deep=True, categories=None):
    if not oc:
        return [], '법제처 API 인증값(LAW_OC)이 없어 공식 실시간 검색을 건너뛰었습니다.'
    words=keywords(question)
    if not words and not _case_number(question):
        return [], '검색할 키워드가 없습니다.'
    allowed=set(categories or ('law','expc','molit'))
    law_queries=family_queries(question, PREFERRED_LAWS,
               fallback=(words[0] if words and not _case_number(question) else ''))
    if 'law' not in allowed:
        law_queries=[]
    interpretation_targets=tuple(target for target, category in (('expc','expc'),('molegCgmExpc','expc'),('molitCgmExpc','molit')) if category in allowed)
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
            acts=asyncio.gather(*[
                _search_target(client,oc,'law',word,question,max_results=1)
                for word in law_queries
            ])
            interpretations=_search_interpretations(client,oc,question,deep=deep,targets=interpretation_targets)
            law_groups, (found,failed)=await asyncio.gather(acts,interpretations)
    except (httpx.HTTPError,ValueError,ET.ParseError) as exc:
        return [], '공식 데이터 조회에 실패했습니다. 인증값, 네트워크, 호출 제한을 확인하세요.'
    out=[];seen=set()
    for group in law_groups:
        for record in group:
            if record['id'] not in seen:
                out.append(record);seen.add(record['id'])
    for record in found:
        if record['id'] not in seen:
            out.append(record);seen.add(record['id'])
    warning=None
    if failed and not found:
        warning='법령해석 API 일부 호출이 실패했습니다. 법제처 인증·이용권한 및 API 일시 오류를 확인하세요.'
    if not out:
        warning=warning or '공식 API 검색 결과가 없거나 본문을 가져오지 못했습니다. 검색어 또는 API 이용권한을 확인하세요.'
    return out[:(24 if deep else 14)], warning
