# LandLex — 국토·도시개발 법령 AI (공개형 웹사이트 MVP)

법령, 법제처 공식 법령해석례, 국토교통부 법령해석, 관리자 등록 PDF/TXT/MD 자료를 함께 검색하고 근거를 표시하는 웹사이트 초안입니다.

## Windows start error (fixed package)

The previous `start_windows.bat` included Korean UTF-8 messages that could be misread by Windows Command Prompt. This replacement uses ASCII-only batch commands and checks both `py -3` and `python`.

- Run `py -3 --version` in Command Prompt. If it fails, also try `python --version`.
- Install Python 3.11+ from https://www.python.org/downloads/windows/ if neither command shows a supported version.
- Double-click `start_windows.bat` in the **extracted** project directory. The script installs dependencies into `.venv` and opens the local URL.
- If you already entered secrets in `.env`, keep the existing project folder and **replace only `start_windows.bat`**; do not overwrite or upload your `.env`.
- If an earlier run left a damaged `.venv` directory, close the script, delete only `.venv`, and rerun the repaired batch file.

## 1. 윈도우에서 5단계로 시작

1. Python 3.11 이상 설치 (설치 시 **Add python.exe to PATH** 체크).
2. ZIP 압축 해제 후 `start_windows.bat` 실행. 처음에는 라이브러리를 설치합니다.
3. `.env` 파일에서 비어 있는 `ADMIN_TOKEN=` 뒤에 길고 안전한 무작위 문자열을 설정. **설정하기 전까지 관리 화면은 접근 불가**입니다.
4. 공식 법령 실시간 검색용으로 [법제처 공동활용](https://open.law.go.kr/)에 신청 후 `.env`의 `LAW_OC=발급값` 설정. AI 답변은 별도로 `OPENAI_API_KEY=발급값` 설정.
5. `.env`를 변경했으면 서버 창을 종료한 뒤 `start_windows.bat` 재실행. 브라우저에서 **http://127.0.0.1:8000** 접속.

> 공개 웹사이트 주소는 아직 없습니다. `127.0.0.1`은 본인 PC에서만 접속하는 주소입니다. 웹 공개는 별도 호스팅/도메인/보안 설정이 필요합니다.

## 2. 자료 등록

좌측 **자료 관리**를 누르고 `.env`에 설정한 `ADMIN_TOKEN`으로 관리자를 인증한 뒤 PDF/TXT/MD 파일과 제목, 기관, 발행일, 공개 원문 주소를 입력합니다.

- **스캔 PDF OCR은 미지원**: 텍스트가 선택 가능한 PDF만 추출합니다.
- 공개·재배포 가능한 자료만 등록해야 합니다. 법령·회신집별 이용허락 및 개인정보를 확인하세요.
- 현재 데이터베이스는 SQLite입니다. 대량의 동시 이용자와 수백만 건 문서는 PostgreSQL + 전문검색 전환이 권장됩니다.
- AI와 법제처 API 키는 **서버**에만 보관되고 브라우저에 노출하지 않습니다.
- 대화내역은 서버에 저장하지 않으며 브라우저 탭의 `sessionStorage`에만 기록됩니다.

## 3. 검색 동작과 제약

- `LAW_OC`가 있으면 법령 목록/본문, 법제처 법령해석례 목록/본문, 국토교통부 법령해석 목록/본문을 공식 API에서 조회합니다.
- 검색 키워드를 추출해 호출합니다. 1차 버전은 완전한 자연어 의미검색이 아니라 키워드 검색이므로 놓치는 자료가 있을 수 있습니다.
- 원문 **본문이 조회된 자료만** AI 답변의 근거에 넣습니다. 단순 제목만 나온 검색 결과는 근거로 사용하지 않습니다.
- 관리자 등록 자료는 기본 키워드/제목 매칭으로 검색합니다. 대규모 자료용 벡터검색, 판례 자동수집, 버전별 법령 비교는 아직 미구현입니다.
- `OPENAI_API_KEY`가 없으면 근거검색은 수행하되 AI가 결론을 임의 생성하지 않습니다.
- 검색된 법령과 과거 질의회신 사이의 현행성·효력 충돌을 **자동 검증하는 기능은 아직 없습니다.** 적용 법령·시행일과 회신일을 반드시 직접 확인하세요.
- 공공 API의 일시적 오류, 인증 실패, 호출 제한 시 데이터가 없거나 경고가 표시됩니다.
- 국토부 해석례의 `원문 페이지` 버튼은 현재 **공식 해석 검색 페이지**로 연결될 수 있습니다. 문서 직접 링크는 추후 공식 메타데이터 링크 검증 후 연결하세요.

## 4. 개발용 실행

```bash
pip install -r requirements.txt
cp .env.example .env   # Windows CMD: copy .env.example .env
# .env 편집 후
python -m uvicorn app.main:app --reload
```

테스트:

```bash
pip install pytest
pytest -q
```

API 문서: http://127.0.0.1:8000/api/docs

## 5. Docker (테스트/소규모 서버)

```bash
cp .env.example .env
# secrets 수정

docker compose up --build -d
```

공개 배포 전에 반드시 HTTPS/리버스 프록시, 서버 측 rate limiting(예: Redis), 관리자 로그인·권한 관리, 악성 파일 검사, 개인정보 보호정책, 이용약관, 백업, 법령 업데이트/인용 검증을 보완하세요. 현재 **프로덕션 준비 완료 버전이 아닙니다.**

## 6. 공식 API 문서 (2026-11-23 확인)

- [법령 목록](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsNwListGuide)
- [법령 본문](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsNwInfoGuide)
- [법제처 법령해석례 목록](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide)
- [법제처 법령해석례 본문](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcInfoGuide)
- [국토교통부 법령해석 목록](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cgmExpcMolitListGuide)
- [국토교통부 법령해석 본문](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cgmExpcMolitInfoGuide)
- [OpenAI Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create)

## 기술 구성

FastAPI · HTML/CSS/JavaScript · SQLite · pdfplumber · 법제처 국가법령정보 공동활용 · OpenAI Responses API(선택)

**주의:** 법률 자문 서비스가 아닙니다. 특정 행정처분 또는 소송에서의 근거 판단은 공인된 원문과 담당 법무전문가 검토가 필요합니다.


## AI 생성 실패 진단 개선판

- API 생성 오류가 나면 기존의 일괄 오류문 대신 HTTP 401/403/404/429, 네트워크/타임아웃, 모델 응답 없음 등의 유형별 안전한 안내를 표시합니다.
- API 키나 원문 API 오류 응답은 사용자에게 노출하지 않습니다. 명령창에는 오류 유형/상태코드만 기록합니다.
- 기존 `.env`와 등록자료 DB는 수정하지 않습니다. 기존 사용자는 `app/main.py` 파일만 교체한 뒤 재시작할 수 있습니다.
- `/api/status`에서 `ai_connected: true`는 API 키가 *설정되었다*는 뜻이며 정상 인증까지 보장하지 않습니다.


## Large casebook uploads (2026-11)

- In the left **자료 관리** menu, select a PDF / HWP / HWPX / TXT / MD.
- The upload accepts up to **512 MB on the local Python server by default** (`MAX_UPLOAD_MB` in `.env`).
- Files are uploaded to a temporary folder, indexed in a background worker into
  2,600-character overlapping chunks, and the raw temporary file is deleted.
- PDF page numbers are stored with each matching chunk. HWP/HWPX do not have
  reliable physical page numbers in the extracted text, so they show a segment.
- A file with only scanned images is **not OCRed** and cannot be searched.
- The HWP/HWPX parser is the independent open-source Python package `syhwp`.
  Its integration is tested using a simulated parser; test with a real HWP from
  your own collection before relying on extraction quality.
- Search is a lightweight local full-text search; it is **not** automatic
  separation of each question/answer into verified standalone cases.
- Keep the CMD window open during indexing and do not restart the server
  until a background job reports completed. Upload job progress is in memory;
  restarting during indexing loses the job and its temporary upload.
- New `document_chunks` is created alongside the old `documents` table,
  with an automatic one-time migration. Before upgrading, back up `data/`.
- Never commit `.env`, `data/`, sensitive documents, or licensed casebooks to
  a public GitHub repository. Before public deployment, configure persistent
  storage, reverse-proxy limits, authentication, antivirus scanning, and a
  separate indexing queue (SQLite and in-process jobs are for small pilots).

## 검색 확장 v2 (2026-11-24)

- 질문창의 **확장 검색**이 기본 선택됩니다. 느릴 때는 체크를 해제해 간단 검색으로 바꿀 수 있습니다.
- 법제처 법령해석례(`expc`), 법제처 법령해석(`molegCgmExpc`), 국토교통부 법령해석(`molitCgmExpc`)을 동시에 조회합니다.
- 법령해석 자료는 안건명 검색(`search=1`)과 본문 검색(`search=2`)을 교차 실행하며, `20-0098` 같은 안건번호는 `itmno=200098`로 직접 조회합니다.
- 각 검색에서 첫 페이지의 결과를 합산하고, 확장 모드에서는 일부 본문 검색의 2페이지도 읽습니다. 결과는 최대 24건 화면에 표시하되 AI에는 검색순위 상위 12건에서 약 3만 자 이하만 전달합니다.
- 여러 법률이 질문에 언급되면 최대 세 법률과 시행령을 함께 검색합니다.
- 등록한 PDF/HWP/HWPX 검색에도 '경자구역 → 경제자유구역', '유치업종 → 유치산업' 같은 검색어 확장 기능을 적용합니다.
- API 호출은 동시 요청 6개로 제한하고 상세 원문 조회 수를 최대 27건으로 제한합니다. 검색 속도와 데이터 제공자의 호출량 제한이 달라질 수 있습니다.
- 검색 결과의 날짜는 회신/해석 일자 필드를 확인하여 표시하고, 안건번호도 함께 표시합니다.
- **주의:** 법제처 인증·호출 제한·자료별 API 제공 범위에 따라 일부 회신은 여전히 누락될 수 있습니다. 전체 법제처 DB 복제 또는 법제처 사이트 전체 웹 수집을 구현한 것은 아닙니다.
- 공식 API 문서: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=expcListGuide , https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=cgmExpcMolegListGuide

### 기존 LandLex에 덮어쓰기

1. CMD 창에서 `Ctrl+C`로 서버를 종료합니다.
2. 프로젝트의 `.env`와 `data/` 폴더를 복사해 백업합니다.
3. 기존 `landlex-large-doc-upload` 버전에 패치 ZIP의 `app/`, `static/` 파일을 덮어쓰거나, 전체판 ZIP의 파일을 같은 폴더에 덮어씁니다.
4. **.env와 data/는 덮어쓰거나 삭제하지 않습니다.** 전체판에도 비밀 키가 담긴 `.env`나 DB 자료는 없습니다.
5. `start_windows.bat` 실행, `Ctrl+F5`로 브라우저를 새로고침합니다.
6. 질문창에서 `법제처 법령해석 20-0098을 찾아줘`를 테스트합니다. 원문에 연결 가능한지와 실제 제공 내용을 직접 확인하세요.


---

## v4 추가 기능: 관련도 기반 근거 선택 및 색상 출처 표시

- 검색 결과는 제목, 본문, 안건번호의 **키워드 일치 점수**로 순위를 산정합니다. 점수는 법적 정확도나 AI 의미 유사도 점수가 아닙니다.
- 관련성이 확인된 법령을 최대 3개 우선 확보한 후, 자료 종류에 관계없이 높은 순위의 근거를 골라 **최대 12건을 AI에 전달**합니다. 아래쪽에는 최대 24건이 표시됩니다.
- 답변 속 `[1]`, `[2]`는 클릭 가능한 출처 표시로 바뀝니다. **파란색은 법령, 초록색은 법령해석·질의회신, 보라색은 판례, 회색은 기타**입니다. 번호 옆에 축약 출처명이 보입니다.
- 사용자 체크박스로 근거를 최대 12건 선택하고 **선택 자료로 다시 분석**을 누르면, 추가 검색 없이 해당 자료만 AI에 전달합니다.
- 답변에 붙는 번호는 처음 검색 목록의 번호와 정확히 일치합니다. 예: `[2]`, `[17]`만 선택하면 AI 입력의 근거 번호도 `[2]`, `[17]`입니다.
- AI가 선택하지 않은 출처 번호를 잘못 인용하면 클릭 링크로 확인된 것처럼 표시하지 않습니다(주황색 점선 표시).
- 다시 분석하기 위한 검색 결과는 서버 메모리에 30분, 최대 100건까지 임시 보관하며, 서버를 재시작하면 사라집니다. 이 경우 새로 질문해 주세요. 공개 다중 서버에서는 Redis 같은 공용 저장소가 추가로 필요합니다.

**업데이트:** 사용 중인 서버 종료 → 기존 `.env`와 `data` 백업 → 패치 ZIP의 `app`, `static` 폴더를 기존 LandLex 폴더에 덮어쓰기 → `start_windows.bat` 실행 → `Ctrl+F5`로 새로고침. API 키를 다시 발급하거나 입력할 필요는 없습니다.

### 수동 검증 시나리오

1. `경제자유구역 내 유치업종을 추가하려면 개발계획을 변경해야 하나요?`로 검색합니다.
2. 법령 `[1]` 등의 파란색 출처, 법제처 해석례 `[n]` 등의 초록색 출처가 표시되는지 확인합니다.
3. 답변 속 번호를 클릭했을 때 아래 검색 근거자료 해당 번호가 열리는지 확인합니다.
4. `AI` 체크박스를 변경하여 2~3개만 남기고 **선택 자료로 다시 분석**을 누릅니다.
5. 답변의 인용 번호가 원래 검색 결과 목록 번호를 그대로 사용하는지 확인합니다.

주의: 자동 선택은 법령 해석의 적합성을 보증하지 않습니다. 특히 법령 개정일과 판례·회신의 현행 적용 여부는 원문에서 확인해야 합니다.
