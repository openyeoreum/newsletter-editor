# 전인교육학회 뉴스레터 시스템

회장 인사말 + 5개 아티클로 구성된 뉴스레터를 **3가지 템플릿**(Classic / Magazine / Minimal)으로 렌더링하고, 웹 UI에서 편집·미리보기·발송까지 처리하는 풀스택 프로젝트입니다.

---

## 🏗 구성

```
EmailTemplate/
├── backend/              # FastAPI (Python) — 렌더링, 저장, 발송 API
├── frontend/             # React + Vite — 편집기 UI
├── templates/            # Jinja2 템플릿 3종 + 공통 매크로
├── drafts/               # 저장된 뉴스레터 초안 (JSON)
├── recipients/           # 수신자 CSV
├── image/                # (참고용) 원본 이미지
├── compose.yml           # 도커 컴포즈 (backend + frontend + mailhog)
└── .env.example
```

### 템플릿 3종

| 키 | 이름 | 특징 |
|---|---|---|
| `classic` | Classic | 원본 디자인. Hero + 좌/우 이미지 교차 + 카드 배너 + 좌측 세로형 |
| `magazine` | Magazine | 와이드 회장 인사말 + 큰 첫 기사 + 2x2 카드 그리드 |
| `minimal` | Minimal | 텍스트 중심. 100×100 썸네일 + 균일 리스트 5개 |

3개 모두 **동일한 데이터 스키마**를 사용하므로, 한 번 작성한 내용을 템플릿만 바꿔 즉시 다른 디자인으로 미리볼 수 있습니다.

---

## 🚀 실행 방법

### 1. 환경변수 준비

```bash
cp .env.example .env
# .env 편집: Cloudinary 키 + 사용할 발송 서비스 키
```

| 변수 | 필수 여부 | 설명 |
|---|---|---|
| `CLOUDINARY_*` | **필수** | 이메일 클라이언트는 외부에 호스팅된 이미지만 안정적으로 표시. https://cloudinary.com 무료 가입 |
| `GMAIL_*` | 선택 | Gmail SMTP 발송 시. 앱 비밀번호 필요 |
| `NCP_*` | 선택 | 국내 대량 발송용 (네이버 클라우드 플랫폼) |

### 2. 도커로 한 번에 실행

```bash
docker compose up --build
```

| 서비스 | URL | 용도 |
|---|---|---|
| Frontend | http://localhost:5173 | 편집기 |
| Backend API | http://localhost:8000/docs | Swagger UI |
| MailHog UI | http://localhost:8025 | 로컬 테스트 메일 확인 |

종료: `docker compose down`

### 3. 도커 없이 로컬 실행 (선택)

```bash
# Backend
cd backend && pip install -r requirements.txt
TEMPLATES_DIR=../templates DRAFTS_DIR=../drafts uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

---

## ✏️ 사용 흐름

1. **편집 탭**에서 호수, 회장 인사, 5개 아티클(이미지 업로드/제목/요약/링크), 푸터 입력
2. 우측 미리보기는 **자동 갱신**됩니다 (300ms debounce)
3. 상단의 **템플릿** 드롭다운으로 Classic / Magazine / Minimal 즉시 전환
4. **💾 저장** → 초안이 `drafts/<id>.json`으로 저장
5. **초안 탭**에서 이전 작업 불러오기/삭제
6. **발송 탭**:
   - 발송 방식 선택 (MailHog / Gmail / NCP)
   - 수신자 CSV 업로드 (`email` 단일 컬럼 또는 `email,name` 모두 지원)
   - **테스트 발송** → 한 명에게만 보내 확인
   - **전체 발송** → 전체 수신자에게 일괄 발송
7. **⬇ HTML 다운로드** → 다른 메일 서비스에 붙여넣을 수 있는 HTML 파일 생성

---

## 📮 발송 방식 비교

| 방식 | 1,000건 동시 발송 | 일일 한도 | 용도 |
|---|---|---|---|
| **MailHog** | ✅ | 무제한 | 로컬 테스트 (실제 발송 X — 웹 UI에서만 확인) |
| **Gmail SMTP** | ❌ | 500건 | 개인/소규모. 앱 비밀번호 필요 |
| **NCP Cloud Outbound Mailer** | ✅ (1요청에 1,000명) | 사용량제 | **국내 대량 발송 권장**. https://www.ncloud.com |

### NCP 발송 설정

1. 네이버 클라우드 플랫폼 가입 → Cloud Outbound Mailer 신청
2. 마이페이지 → 인증키 관리 → Access Key / Secret Key 발급
3. 발신자 도메인 등록 (SPF/DKIM)
4. `.env`에 키 입력 후 컨테이너 재시작

### 새 발송 서비스 추가하기

`backend/senders/`에 새 클래스를 만들고 `Sender` 프로토콜을 구현한 뒤, `senders/__init__.py`의 `REGISTRY`에 등록하면 끝입니다.

```python
class MyNewSender:
    def send(self, html, subject, recipients, from_addr, from_name="..."):
        ...
        return SendResult(sent=N, failed=0, errors=[])
```

---

## 🖼 이미지 호스팅 (Cloudinary)

이메일 클라이언트(특히 Gmail)는 로컬 이미지를 차단하기 때문에 **모든 이미지를 외부 URL로 제공해야** 합니다. 편집기에서 파일 선택만 하면 자동으로 Cloudinary에 업로드되고 URL이 채워집니다.

무료 티어: 25 GB 저장공간 + 25 GB/월 대역폭 (학회 뉴스레터 용도로 충분).

### 📐 이미지 권장 사이즈

이메일 본문 너비는 **620px** 기준입니다. 레티나 디스플레이 대응을 위해 **표시 크기의 2배**로 업로드하는 것을 권장합니다. JPG/PNG 모두 가능하며, 파일당 **300KB 이하**로 압축하면 로딩이 빠릅니다.

| 위치 | 표시 크기 | **권장 업로드 (2x)** | 비율 | 용도 |
|---|---|---|---|---|
| 회장 인사 사진 | 80×80 | **160×160** | 1:1 (정사각) | 인물 정면 |
| Hero 이미지 (Classic 1번 / Magazine 1번) | 540×auto | **1080×720** | 3:2 권장 | 가로 와이드 |
| 좌/우 이미지 카드 (Classic 2·3번) | 180×130 | **360×260** | 약 4:3 | 가로형 |
| 카드 배너 (Classic 4번) | 540×auto | **1080×540** | 2:1 권장 | 가로 와이드 |
| 세로형 카드 (Classic 5번 — 학회지 표지 등) | 140×190 | **280×380** | 약 3:4 | 세로형 |
| Magazine 2x2 그리드 | 250×160 | **500×320** | 약 3:2 | 가로형 |
| Minimal 썸네일 | 100×100 | **200×200** | 1:1 (정사각) | 자동 크롭됨 |

**Tip**: Cloudinary는 업로드 후 URL 파라미터(`w_540,c_fill,q_auto,f_auto`)로 자동 리사이즈/포맷 변환이 가능하므로, 원본만 큰 사이즈로 올려두어도 됩니다. 가장 큰 가로 사이즈인 **1080px 폭** 정도면 모든 슬롯에서 충분합니다.

---

## 📂 데이터 스키마 (drafts/*.json)

```json
{
  "id": "abc12345",
  "name": "초안 이름",
  "template": "classic",
  "subject": "메일 제목",
  "data": {
    "volume": "24",
    "issue_date": "2026년 4월",
    "web_view_url": "https://...",
    "greeting": { "photo": "...", "name": "...", "title": "...", "body": "...", "signature": "..." },
    "articles": [
      { "image": "...", "badge_text": "...", "title": "...", "summary": "...", "meta": "...", "link": "..." }
    ],
    "footer": { "address": "...", "contact": "...", "links": [{"text":"...","url":"..."}] }
  }
}
```

샘플: `drafts/sample.json` 참고.

---

## 🛠 API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/api/templates` | 사용 가능한 템플릿 목록 |
| GET | `/api/senders` | 사용 가능한 발송 서비스 목록 |
| POST | `/api/render` | `{template, data}` → HTML |
| POST | `/api/export` | HTML 파일 다운로드 |
| GET | `/api/drafts` | 초안 목록 |
| GET | `/api/drafts/{id}` | 초안 단건 |
| POST | `/api/drafts` | 초안 저장 |
| DELETE | `/api/drafts/{id}` | 초안 삭제 |
| POST | `/api/upload-image` | 이미지 → Cloudinary URL |
| POST | `/api/parse-recipients` | CSV 파싱 |
| POST | `/api/send` | 메일 발송 |

전체 스펙: http://localhost:8000/docs

---

## ✅ 체크리스트

- [ ] `.env` 파일 작성 (Cloudinary 필수)
- [ ] `docker compose up --build` 실행
- [ ] http://localhost:5173 접속해서 편집기 동작 확인
- [ ] http://localhost:8025 에서 MailHog로 테스트 발송 확인
- [ ] (선택) NCP 키 등록 후 실제 대량 발송 테스트
