"""Public MOLEG administrative-rule API parser and bounded integration tests.

No live API key or network needed; tests use contract-shaped sample XML.
"""
import asyncio
from unittest.mock import Mock
import httpx
import pytest

from app.admin_rule_api import (
    parse_list, parse_detail, search_terms, search_administrative_rules,
)

LIST_XML='''<?xml version="1.0" encoding="utf-8"?>
<AdmRulSearch><totalCnt>2</totalCnt>
  <admrul><행정규칙일련번호>2100000274926</행정규칙일련번호>
    <행정규칙명>산업단지 관리지침</행정규칙명><행정규칙종류>고시</행정규칙종류>
    <발령일자>20260301</발령일자><소관부처명>산업통상자원부</소관부처명>
    <현행연혁구분>현행</현행연혁구분></admrul>
  <admrul><행정규칙일련번호>2100000282416</행정규칙일련번호>
    <행정규칙명>산업입지의 개발에 관한 통합지침</행정규칙명>
    <발령일자>20260801</발령일자><소관부처명>국토교통부</소관부처명></admrul>
</AdmRulSearch>'''.encode('utf-8')

DETAIL_XML='''<?xml version="1.0" encoding="utf-8"?>
<행정규칙><행정규칙명>산업단지 관리지침</행정규칙명>
<행정규칙종류>고시</행정규칙종류><발령일자>20260301</발령일자>
<시행일자>20260401</시행일자><소관부처명>산업통상자원부</소관부처명>
<조문단위><조문번호>0012</조문번호><조문내용>제12조(관리기본계획의 변경)</조문내용>
  <항내용>산업단지 관리기본계획 변경 기준을 정한다.</항내용></조문단위>
</행정규칙>'''.encode('utf-8')


def test_title_and_body_search_with_limit():
    terms=search_terms('산업단지 관리기본계획을 변경하려면 어떤 지침이 적용되나?')
    assert ('산업단지','1') in terms
    assert ('관리기본계획','2') in terms
    assert len(terms) <= 3


def test_no_unbounded_search_or_arbitrary_dates():
    terms=search_terms('규정 2026 12345?',3)
    assert all(value != '*' and len(value)<=25 for value,scope in terms)
    assert len(terms)<=3


def test_parse_list_preserves_organization_and_current():
    rows=parse_list(LIST_XML)
    assert len(rows)==2
    assert rows[0]['title']=='산업단지 관리지침'
    assert rows[0]['current']=='현행'
    assert rows[0]['organization']=='산업통상자원부'


def test_parse_detail_stays_separate_from_statutory_law():
    rec=parse_list(LIST_XML)[0]
    items=parse_detail(DETAIL_XML,'산업단지 관리기본계획 변경할 수 있나?',rec)
    assert items
    assert items[0]['kind']=='행정규칙'
    assert items[0]['law_level']=='행정규칙'
    assert '관리기본계획 변경' in items[0]['body']
    assert items[0]['issued_date']=='2026-03-01'
    assert items[0]['effective_date']=='2026-04-01'
    assert items[0]['url'].startswith('https://www.law.go.kr/admRulInfoP.do?admRulSeq=')


class FakeClient:
    def __init__(self,failed=False): self.calls=[]; self.failed=failed
    async def get(self,url,params=None,timeout=None):
        self.calls.append((url,params))
        if self.failed: raise httpx.ConnectError('Fake failure')
        data=LIST_XML if 'lawSearch.do' in url else DETAIL_XML
        response=httpx.Response(200,content=data,request=httpx.Request('GET',url))
        return response


def test_bounded_api_calls_and_no_wide_fetch():
    fake=FakeClient()
    results,failed=asyncio.run(search_administrative_rules(fake,'DUMMY',
        '산업단지 관리기본계획 변경 기준은?',deep=True))
    assert not failed
    assert results
    assert any(x['kind']=='행정규칙' for x in results)
    assert len(fake.calls)<=8  # 3 list searches + up to 5 details
    assert all(c[1]['target']=='admrul' for c in fake.calls)
    assert all(c[0].startswith('https://www.law.go.kr/DRF/') for c in fake.calls)
    assert any(c[1].get('nw')=='1' for c in fake.calls if 'lawSearch' in c[0])


def test_admin_api_failure_does_not_block_other_search():
    fake=FakeClient(failed=True)
    records,failed=asyncio.run(search_administrative_rules(fake,'DUMMY',
        '산업단지 관리기본계획 변경 기준은?',deep=True))
    assert records==[] and failed


def test_empty_key_does_not_touch_network():
    fake=FakeClient()
    records,failed=asyncio.run(search_administrative_rules(fake,'',
        '산업단지 관리기본계획 변경 기준은?'))
    assert records==[] and not failed and not fake.calls
