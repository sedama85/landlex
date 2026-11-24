from app.law_api import _records_from_xml, _flatten_content, keywords, _official_link
from defusedxml import ElementTree


def test_keywords_alias():
    words=keywords('경자구역내 유치업종을 변경하려면 개발계획을 변경해야 하나요?')
    assert '경제자유구역' in words
    assert '유치업종' in words
    assert '개발계획' in words


def test_record_parser_molit():
    xml='''<LawSearch><totalCnt>1</totalCnt><molitCgmExpc>
    <법령해석일련번호>315912</법령해석일련번호><안건명>도로 관련 해석</안건명>
    <해석일자>20261101</해석일자></molitCgmExpc></LawSearch>'''.encode()
    recs=_records_from_xml(xml,'molitCgmExpc')
    assert len(recs)==1
    assert recs[0]['법령해석일련번호']=='315912'


def test_record_parser_law():
    xml='''<LawSearch><law><법령일련번호>100</법령일련번호><법령명한글>국토의 계획 및 이용에 관한 법률</법령명한글></law></LawSearch>'''.encode()
    assert _records_from_xml(xml,'law')[0]['법령명한글'].startswith('국토')


def test_detail_extraction():
    root=ElementTree.fromstring('''<root><질의요지>실시계획 변경 여부?</질의요지><회답>검토 필요</회답><이유>판단 근거</이유></root>''')
    body=_flatten_content(root,'expc','실시계획 변경')
    assert '회답: 검토 필요' in body
    assert '이유: 판단 근거' in body


def test_public_source_link_never_contains_auth_key():
    url=_official_link('expc','315912','테스트')
    assert 'law.go.kr' in url
    assert 'OC=' not in url
