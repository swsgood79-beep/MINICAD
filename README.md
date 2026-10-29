# 무료 웹 버전 — GitHub Pages

**PC 설치나 Render 가입 없이 브라우저에서 DXF를 열고 측정·수정·저장하는 버전**을 추가했습니다. 기존 FastAPI/ODA 서버 버전도 유지합니다.

- GitHub Pages 정적 사이트에서 Pyodide(WebAssembly Python)와 ezdxf를 Web Worker로 실행합니다.
- 도면은 브라우저 메모리에서만 처리합니다. 업로드 API, 분석/추적 서비스, 외부 CDN 요청을 사용하지 않습니다. 실행 파일과 라이브러리도 같은 사이트에서 제공합니다.
- 첫 파일을 열 때 약 20 MB의 실행 파일을 불러오므로 잠시 기다려야 합니다. 이후 같은 탭에서 재사용합니다.
- `예제 도면` 버튼으로 바로 시험할 수 있습니다. 새로고침/탭 닫기 전에 변경 파일을 다운로드하세요.
- **무료 웹 버전은 DXF 전용입니다.** DWG는 기존 CAD에서 DXF로 내보낸 뒤 여세요. ODA 실행 파일은 브라우저에서 실행할 수 없습니다.
- 미표시 객체 보존, 원자적 편집, 이력, 측정 계산에 서버와 동일한 `cad_core.py`를 사용합니다. 화면 객체 목록으로 DXF를 다시 만드는 방식이 아닙니다.
- 큰 파일과 긴 이력은 브라우저 메모리를 소비합니다. 입력 한도는 40 MiB지만 그 크기의 모든 도면 처리를 보장하지 않습니다.

## GitHub Pages 배포

`.github/workflows/pages.yml`이 `main` 변경 시 정적 웹 빌드와 배포를 실행합니다. GitHub 저장소에서 **Settings → Pages → Build and deployment → Source → GitHub Actions**를 최초 한 번 선택해야 할 수 있습니다. 이후 **Actions → Deploy MiniCAD to GitHub Pages → Run workflow**를 실행하면 됩니다. 성공한 배포의 실제 주소는 Actions 결과와 Pages 설정에 표시됩니다. 무료 GitHub Pages는 공개 저장소 기준이며, 비공개 저장소는 계정 플랜에 따릅니다. 이 작업은 저장소 공개 범위를 변경하지 않습니다.

Pages 활성화는 일반 Git push와 별도 권한입니다. 설정 파일 추가나 push 성공만으로 사이트가 가동됐다고 간주하지 않습니다.

## 브라우저 버전 로컬 검증

아래 명령은 개발자용이며 웹사이트 이용자는 실행할 필요가 없습니다.

```sh
cd frontend
npm ci
cd ..
python scripts/prepare_browser.py
cd frontend
npm run build:pages
cd ..
python -m http.server 8081 --directory frontend/dist
```

`prepare_browser.py`는 npm 잠금 파일로 설치한 Pyodide 0.29.3과 공식 배포 wheel을 준비하고 SHA-256을 검증합니다. 생성된 런타임 파일은 Git에 포함하지 않으며 Actions에서 재현합니다. TLS/체크섬 검증을 끄지 않습니다. 사이트 이용 중 별도 Python 서버는 필요하지 않습니다.

실제 정적 사이트 브라우저 테스트는 `MINICAD_TEST_BROWSER=1 MINICAD_TEST_URL=<정적 사이트 주소> python tests/browser_smoke.py`로 실행합니다. 테스트는 API 요청/업로드/제3자 요청이 하나라도 발생하면 실패합니다. Playwright와 Chromium이 필요합니다. 현재 정적 사이트에서 실제 편집·측정·다운로드 검증을 통과했고, 공유 엔진/API/접근 제어 Python 테스트 19개와 기하 테스트 11개도 통과했습니다.

추가 파일: `cad_core.py`(공유 문서 엔진), `browser_runtime.py`(브라우저 세션), `frontend/public/cad-worker.js`(Python Worker), `frontend/src/transport.ts`(정적/서버 연결 구분), `scripts/prepare_browser.py`(검증 및 실행 파일 준비), `tests/test_browser_runtime.py`(브라우저 문서 회귀).

---

# MiniCAD Web — 1차 개발 버전

브라우저에서 DXF를 열어 2D 도면을 측정·수정하고 별도 파일로 다운로드하는 React + TypeScript / Canvas / FastAPI / ezdxf 프로그램입니다. DWG는 별도 설치된 **ODA File Converter** 공개 연동을 사용합니다. AutoCAD의 독점 코드나 역공학 코드를 사용하지 않습니다.

실무 도면 검증을 위한 기반 버전입니다. 생산·검사에 사용하기 전에 원본 CAD와 표시·측정·저장 결과를 대조하세요. 대형 도면, 다양한 실제 DWG, Windows Chrome/Edge에서의 호환성 검증은 아직 필요합니다.

## 설치 및 실행

필수: **Python 3.12+**, **Node.js 22.12+** (24 LTS 권장), Chrome 또는 Edge. 현재 고정된 numpy 버전은 Python 3.12 이상이 필요합니다.

Windows에서는 `start_windows.bat`을 실행합니다. 가상환경 생성, 고정 의존성 설치, 프론트 빌드 후 로컬 서버를 시작합니다. 스크립트가 출력하는 주소를 브라우저에서 열고 Ctrl+C로 서버를 종료하세요. Windows 배치 자체는 Linux 검증 환경에서 실행하지 않았습니다.

수동 설치 (Windows PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Linux/cloud:

```sh
cd /workspace/MINICAD
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

접속 주소는 서버가 출력합니다(포트 8000). API와 빌드된 UI를 같은 FastAPI 서버가 제공합니다. 개발 중에는 백엔드를 실행하고 `frontend`에서 `npm run dev`를 실행하면 Vite가 `/api`를 프록시합니다. Python 의존성을 바꿀 때는 `requirements.txt`와 테스트한 `requirements.lock`을 함께 관리하세요. npm 잠금 파일은 `frontend/package-lock.json`입니다.

### DWG / ODA

[공식 ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter)를 운영체제에 맞게 별도 설치하고 이용 조건을 확인하세요. 일반 설치 위치는 ezdxf가 탐색합니다. 찾지 못하면 서버 프로세스를 시작하기 전에 실행 파일의 절대 경로를 지정하세요.

```powershell
$env:ODA_FILE_CONVERTER = 'C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe'
```

설치 경로는 실제 버전별 위치에 맞춰 변경합니다. Linux ODA는 배포판별 런타임/디스플레이 의존성을 추가로 요구할 수 있습니다. 설치 여부는 `/api/status`가 보고하지만, 설치 감지만으로 변환 성공을 보장하지 않습니다. DWG 저장은 R2018로 변환합니다. 버전, 프록시 객체, 외부 참조, 글꼴, 치수 스타일 등의 변경·손실 가능성이 있으므로 원본을 보관하고 대상 CAD에서 다시 열어 비교해야 합니다.

## 구현한 1차 기능

- DWG/DXF 확장자·40 MiB 제한·파싱 실패 안내. 도면별 임의 세션 ID와 쿠키로 이전의 전역 `active` 도면 공유 문제 제거.
- LINE, CIRCLE, ARC, LWPOLYLINE, 2D POLYLINE, POINT 표시. 폴리라인 bulge는 ezdxf의 선/호 분해를 사용해 곡선으로 표시.
- TEXT/MTEXT는 일반 문자열과 근사 배치로 표시(복잡한 서식·정렬·폰트·문자 폭 재현은 후속 단계).
- 레이어 표시/숨김. 원본의 off/frozen 상태를 초기 반영. 잠긴 레이어의 객체 수정 거부. 표시 토글은 화면 전용이며 DXF 레이어 상태를 저장하는 편집이 아님.
- 마우스 휠: 커서 위치 중심 확대·축소. 가운데 또는 오른쪽 버튼 드래그: 화면 이동. 전체 도면 맞춤. Shift+클릭 다중 선택.
- 끝점·중간점·원/호 중심점 스냅, 픽셀 기반 허용 반경, 스냅 표시. 숨긴 레이어는 스냅/선택 대상에서 제외.
- 두 점/수평/수직 거리, 원·호의 반지름/직경, 두 직선의 방향 벡터 사이 0–180° 각도, 폴리라인/선/호/원 길이. 폴리라인 호의 길이는 테셀레이션 근사가 아닌 해석적 길이. 소수점 0–6자리 설정은 이후 측정에 적용.
- 선·원 추가, 다중 이동·복사·삭제, 선/원 좌표 편집, 방향 유지 선 길이 변경, 원 반지름 변경.
- 문서 전체를 보존하는 최대 30단계 실행 취소/다시 실행. 일괄 편집은 복제 문서에 원자적으로 적용하고 실패 시 전체 취소. 버전 불일치 편집 거부.
- 별도 `원본이름_edited.dxf/dwg` 다운로드. 업로드한 원본 파일에 쓰지 않음. 브라우저를 닫거나 도면을 교체할 때 미저장 변경 경고.
- 한국어의 어두운 작업 화면: 상단 파일/이력 메뉴, 좌측 도구, 중앙 Canvas, 우측 레이어·속성·측정, 하단 좌표·단위·스냅·상태.

정밀 측정은 화면 픽셀과 분리된 도면 실좌표(IEEE 754 double)로 계산합니다. 단위는 `$INSUNITS`를 표시하며 숫자를 자동 환산하지 않습니다. 단위가 미지정이면 임의로 mm로 간주하지 않습니다. 마우스 자유 클릭에는 픽셀 해상도 한계가 있으므로 정확한 점은 스냅, 정확한 편집은 좌표 입력을 사용하세요.

이동/복사: 선택 모드에서 객체 선택 → 이동/복사 도구 → 기준점 → 목적점. Delete로 삭제, Esc로 취소. Ctrl+Z로 실행 취소, Ctrl+Y 또는 Ctrl+Shift+Z로 다시 실행합니다.

## 원본 보존과 제한

화면에 표시된 객체 목록으로 DXF를 새로 만드는 대신 **원래 ezdxf 문서 전체를 유지하며 선택한 객체만 수정**합니다. 미지원 SPLINE, INSERT, DIMENSION, 블록 정의 등을 화면에서 누락하더라도 저장 시 임의 삭제하지 않습니다. 다만 ezdxf의 DXF 재기록 및 ODA 변환이 원본과 바이트 단위 동일성이나 모든 CAD 확장 데이터의 무손실을 보장하지는 않습니다.

현재 INSERT/DIMENSION/HATCH/SPLINE/외부 참조는 표시·편집하지 않습니다. 미표시 객체 종류/개수와 경고를 보여줍니다. 3D POLYLINE, XY 평면 외 extrusion, 경사진 3D 선은 미지원으로 처리합니다. 화면은 modelspace의 XY 투영만 다루며 paperspace/레이아웃, 객체별 Z 측정은 미구현입니다. 객체별 색·선종류·선가중치, SHX/폰트, MTEXT 스타일 및 정교한 문자 선택 영역도 후속 과제입니다. 문자 편집은 아직 지원하지 않습니다.

표시 한도는 modelspace 객체 120,000개이며 초과 시 경고합니다. 생략된 객체는 문서에 보존됩니다. 공간 인덱스/뷰포트 컬링/곡선별 확대율 적응 렌더링은 아직 없어 대형 도면에서 성능 한계가 있습니다. 세션당 전체 문서를 복제하는 이력 방식도 메모리를 소비합니다.

**로컬 단일 운영자 용도**입니다. 최대 8개 도면 세션, 프로세스 메모리 저장이며 서버 재시작/브라우저 새로고침 후 세션 복구를 제공하지 않습니다. 사용 후 `도면 닫기`로 메모리를 해제하세요. 임의 문서 ID는 인증/권한 관리의 대체물이 아닙니다. 공유 웹 배포 전에는 로그인·문서 접근 제어·세션 만료·용량 제한·영구 저장·변환 작업 격리를 구현해야 합니다. 현재 서버를 공용 네트워크에 공개하지 마세요.

## 코드 구조와 기존 MVP 분석

- `server.py`: 기존 FastAPI·ezdxf·odafc 입출력 구조를 재사용한 문서 세션/직렬화/편집/이력/저장 API.
- `frontend/src/main.tsx`, `style.css`: React 한국어 CAD UI, 입력 및 명령 처리.
- `frontend/src/geometry.ts`: 실좌표/화면좌표 변환, 스냅, 측정, 선택, 전체 맞춤. 표시용 곡선 샘플과 측정 공식 분리.
- `legacy/`: 업로드한 MVP의 Python 및 HTML 원본 보관. `/legacy`에서 원래 화면을 사용할 수 있으며 새 API는 쿠키 세션으로 기존 호출 형식을 지원. 기존 화면의 제한(단일 선택, 불완전한 스냅/곡선 표시)은 그대로이므로 새 React 화면을 권장. `legacy/server.py`를 별도로 실행하지 마세요.
- `tests/`: API 회귀 및 브라우저 시나리오. `frontend/src/geometry.test.ts`: 수학/스냅 테스트.

첨부 MVP에서 확인한 문제: 공유 전역 도면, 실행 취소 없음, 호의 마지막 끝점 누락/곡선 샘플을 끝점으로 취급하는 스냅, bulge 직선화, 대형 도면 맞춤의 인자 spread 위험, 레이어/POLYLINE 누락. 첫 단계에서 이를 개선했습니다. GitHub 저장소는 조회 당시 커밋/파일이 없는 빈 저장소였으므로 첨부 ZIP을 기준으로 새 코드를 추가했고 자동 커밋·push는 수행하지 않았습니다.

## 테스트

```sh
# 저장소 루트
.venv/bin/python -m unittest discover -s tests -v
# Windows: .\.venv\Scripts\python -m unittest discover -s tests -v
cd frontend
npm test
npm run build
```

브라우저 스모크 테스트는 서버를 먼저 시작한 뒤 Playwright가 설치된 Python에서 `python tests/browser_smoke.py`로 실행합니다. `python -m pip install playwright`와 `python -m playwright install chromium`이 추가로 필요할 수 있습니다. 기본 브라우저는 Playwright Chromium이며 Linux 시스템 Chromium이 있으면 이를 사용합니다. 테스트는 자체 DXF를 생성하고 측정·이동·다운로드 결과를 검사하며 `test-results/cad-smoke.png`를 생성합니다. 실제 사용자 파일을 사용하지 않습니다.

현재 Linux 검증 결과:

- Python API 테스트 **12개 통과**: 입출력, 잘못된 파일/40 MiB 한도, 레이어, 곡선, 문자, 이동·복사·삭제·좌표 편집, 이력, 원자성, 잠금/유효성, 세션 분리·한도, 미지원 객체/블록/치수 보존 및 export 후 DXF audit.
- TypeScript 기하 테스트 **11개 통과**: 좌표 왕복, 커서 중심 줌, 축척과 독립된 거리, 끝점/중간점/중심점, 호 끝점, 곡선 길이, 각도, 대량 전체 맞춤, 숨김 객체 제외.
- TypeScript 타입 검사 및 Vite 프로덕션 빌드 통과.
- Chromium 실제 UI 시나리오: 파일 열기 → 끝점/중심점 스냅 거리 → 휠/가운데 팬 후 거리 → 다중 선택 → 이동 → 취소/재실행 → 삭제/취소 → 별도 DXF 다운로드 → 재열기·좌표/미지원 객체/원본 보존 확인. 브라우저 오류 없음.
- 실제 DWG 왕복과 Windows Chrome/Edge, 원래 `/legacy` 화면의 전체 수동 조작은 미검증. ODA 미설치/변환 실패 경로는 모킹하여 검증했으며, 실제 ODA 성공 변환으로 간주하지 않음.

## 다음 단계

1. ODA가 설치된 Windows에서 고객 DWG/DXF 표본의 왕복 검증 및 회귀 도면 모음.
2. INSERT의 중첩 블록 변환/속성, DIMENSION의 가상 객체, HATCH, 정교한 TEXT/MTEXT 렌더링.
3. 선·원·호의 교차점 스냅, 직교/접선/사분점 스냅, 박스 선택과 치수 주석. **교차점 스냅은 이번 단계에 미구현**.
4. 대형 도면 공간 인덱스, 렌더링 캐시, 작업 스레드, 명령 기반 이력과 메모리 예산.
5. 단위 환산, 레이어 상태 저장 편집, 고급 객체 속성, 추가 CAD 편집 명령.
6. 인증·권한·세션/작업 큐·안전한 업로드·영구 저장을 갖춘 배포 구성과 GitHub CI.

## 주소로 접속하는 웹 배포 (비공개 운영자용)

사용자 PC에는 Python/Node/AutoCAD를 설치하지 않습니다. Docker 이미지가 React 화면과 FastAPI를 함께 제공하고, 호스팅 서비스가 HTTPS 주소를 발급합니다. 이 저장소의 `Dockerfile`과 `render.yaml`은 Render용 구성이며, 설정 파일 생성만으로 인터넷 배포가 실행되지는 않습니다.

Render 계정에서 이 소스가 들어 있는 GitHub 저장소를 연결하여 **Blueprint**를 만들면 `render.yaml`을 읽습니다. `minicad-web` 서비스의 실제 주소는 배포 완료 후 Render가 발급합니다. URL을 임의로 가정하지 마세요. 무료 플랜은 서비스 휴면/메모리 제한이 있어 첫 접속 지연과 큰 도면 처리 제한이 있습니다. 요금/한도는 배포 시 서비스 화면에서 확인하세요.

- `MINICAD_DEPLOYED=1`: 로그인 설정 없이 시작하는 것을 거부합니다.
- `MINICAD_USERNAME`: Blueprint의 기본 로그인 이름은 `minicad`.
- `MINICAD_PASSWORD`: Render가 생성하는 비밀번호. Render 환경변수 설정에서 안전하게 확인/변경하세요. 비밀번호를 코드나 채팅에 넣지 마세요.
- 브라우저는 최초 접속 시 HTTP Basic 로그인 창을 표시합니다. 화면과 API 모두 같은 계정으로 보호합니다. **HTTPS에서만 사용하세요.**
- `/healthz`는 로그인 없이 호스팅 상태 확인용으로만 공개합니다.
- 세션을 메모리에서 관리하므로 프로세스는 하나만 실행합니다. 재시작/휴면 후 업로드한 도면은 다시 열어야 합니다. 장기 보관은 다운로드한 파일로 합니다.
- 이 구성은 한 운영자/신뢰하는 사용자를 위한 비공개 배포입니다. 계정별 문서 소유권을 갖춘 다중 사용자 SaaS가 아닙니다.
- 기본 이미지에는 ODA가 없습니다. DXF 기능을 먼저 사용할 수 있고, 실제 DWG 처리는 라이선스/런타임을 확인한 ODA 설치 서버가 별도로 필요합니다.

직접 컨테이너 실행 시 호스팅 플랫폼의 비밀값 관리 기능으로 위 계정 정보를 주입하세요. `PORT`는 기본 10000이며 외부 TLS는 호스팅 서비스가 종료합니다. `.dockerignore`가 가상환경, 캐시, Git 메타데이터와 `.env` 파일을 빌드 컨텍스트에서 제외합니다.

배포 접근 제어 테스트는 `tests/test_deployment.py`에 포함됩니다. 배포 성공 여부와 실제 접속 주소는 호스팅에서 실행·검증한 뒤에만 확정할 수 있습니다.

배포 구성 검증: API/접근 제어 테스트 총 **15개 통과**. Docker 이미지 빌드 및 비관리자 실행, 공개 health check, 미인증 접근 차단, 로그인 후 React HTML 응답, DXF 업로드→이동→다운로드→재열기를 실제 컨테이너에서 검증했습니다. 반복 검증은 이미지 빌드 후 `python tests/container_smoke.py`로 실행합니다. **Render 실제 배포와 공개 URL은 호스팅 계정 연결 전이므로 미검증/미발급 상태입니다.**
