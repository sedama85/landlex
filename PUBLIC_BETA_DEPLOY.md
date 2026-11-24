# LandLex 공개 베타 배포 안내 (2026-11-24)

## 1. GitHub 새 저장소 생성

1. https://github.com/new 접속
2. Repository name: `landlex` (권장)
3. Public 또는 Private 선택 (검증 전에는 Private 권장)
4. **Add a README file / .gitignore / license는 선택하지 않기** (빈 저장소 생성)
5. Create repository 클릭

> 연결된 GitHub 계정은 sedama85입니다. 기존 `map` 저장소는 LandLex와 다른 프로젝트이므로 건드리지 않습니다.

## 2. 소스 업로드 (Windows 권장: 원클릭 파일)

Git 설치 후 압축 해제 폴더의 `upload_to_github_windows.bat`를 더블클릭하고, 스테이징 목록을 확인한 뒤 `Y`를 입력하면 GitHub 인증과 업로드가 진행됩니다. 기존 `map` 저장소는 수정하지 않습니다.

수동으로 하려면 아래 명령을 사용하세요.

## 2-1. 수동 업로드 (Windows PowerShell)

프로젝트 ZIP을 압축 해제한 폴더에서 PowerShell을 열고, Git 설치 후 다음 명령어를 차례로 실행합니다.

```powershell
git init
git branch -M main
git add .
git status
git commit -m "LandLex public beta"
git remote add origin https://github.com/sedama85/landlex.git
git push -u origin main
```

Git이 없다면 https://git-scm.com/downloads 에서 설치하세요. 브라우저 인증이 열릴 수 있습니다.

**업로드 전 `git status`를 확인하세요. `.env`, API 키, `data/` 또는 *.db가 보이면 중단하세요.**

## 3. Render 무료 웹서버 생성

1. https://dashboard.render.com/ 가입/로그인
2. New -> Blueprint 선택
3. GitHub의 `sedama85/landlex` 저장소 선택
4. 저장소 루트의 `render.yaml` 인식 확인
5. `LAW_OC`, `GEMINI_API_KEY` 두 항목을 Render 화면에서 비밀 환경변수로 입력
6. Deploy 실행. 상태가 Live로 바뀌면 Render가 제공하는 `https://...onrender.com` 주소로 접속

`render.yaml`은 무료 FastAPI 한 서버를 배포하며, **비밀키를 코드에 기록하지 않습니다.**

## 4. 첫 배포 후 검증

- `/healthz` → `{"status":"ok"}`
- `/api/status` → law_api_connected=true, ai_connected=true 표시 (실제 인증 검증과는 다릅니다)
- 질문 1개 검색 → 법령/법령해석/질의회신이 검색되는지 확인
- 답변 인용 `[1]` 클릭 → 오른쪽 패널 열림/닫힘 확인
- 질문 연속 요청 때 한도 오류가 정상 작동하는지 확인

## 무료 배포의 중요한 제한

- Render Free는 15분 비활성 시 절전되며 다시 접속할 때 느릴 수 있습니다.
- 서버 종료·재시작·재배포·절전 후 **SQLite 파일 및 업로드한 PDF/HWP 검색 색인이 사라집니다**. 따라서 이 배포본은 실시간 법제처 검색 테스트용입니다.
- 대용량 자료를 **지속 보관**하려면 유료 영구 디스크 또는 PostgreSQL+별도 문서 저장소로 전환해야 합니다.
- 공개 베타에서 `ADMIN_TOKEN`은 비워 관리자 업로드를 막았습니다. 공개 업로드 허용은 권장하지 않습니다.
- 무료 Gemini 사용량은 Google 정책에 따라 제한되며, 무료 요청/응답 콘텐츠는 제품 개선에 쓰일 수 있습니다. 개인·비공개 자료를 입력하지 마세요.
- 질문당 인용 자료의 정확성, 법령 시행일, 회신의 효력은 직접 확인해야 합니다.
- 현재 인메모리 요청 제한은 1개 서버 프로세스에만 적용됩니다. 대규모 공개/상용 서비스 전에는 API Gateway/Redis/인증/모니터링 등이 필요합니다.

## 권장 다음 단계

- 테스터 5~20명으로 비공개 소규모 파일럿
- 사용자 피드백과 429/500 오류 확인
- 비용, 공개 데이터 재이용 조건, 개인정보처리방침 검토
- 영구 저장소 및 가입/관리자 인증, 서비스 모니터링을 넣은 이후 일반 공개
