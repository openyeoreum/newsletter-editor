# Supabase + Vercel 배포 가이드

이 프로젝트는 운영에서 Vercel 한 프로젝트 안에 Vite 정적 프론트엔드와 FastAPI Python Function을 함께 배포하고, 데이터는 Supabase Postgres에 저장합니다.

## 1. Supabase 준비

1. Supabase 프로젝트를 생성합니다.
2. Project Settings에서 다음 값을 준비합니다.
   - `SUPABASE_URL`
   - Secret keys의 `default` 키 전체 값 (`sb_secret_...`)
3. Supabase SQL Editor에서 `supabase/schema.sql` 내용을 실행합니다.

브라우저에서 Supabase anon key를 사용하지 않습니다. FastAPI 함수만 `SUPABASE_SERVICE_ROLE_KEY`로 서버 측 접근을 수행합니다.

## 2. Vercel 프로젝트 설정

GitHub 저장소를 Vercel에 연결한 뒤 루트 프로젝트로 배포합니다. 이 저장소에는 다음 파일이 포함되어 있습니다.

- `vercel.json`: `/api/*`와 `/health`를 FastAPI 함수로, 나머지는 Vite 빌드 결과로 라우팅
- `api/index.py`: Vercel Python Function 진입점
- `middleware.js`: 관리자 Basic Auth 보호
- `requirements.txt`: Python Function 의존성

## 3. Vercel 환경변수

Vercel Dashboard의 Project Settings > Environment Variables에 아래 값을 Production 환경으로 입력합니다.

```env
APP_ENV=production
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<관리자 비밀번호>
PUBLIC_BASE_URL=https://newsletter.humancompletion.org

SUPABASE_URL=https://ngcfmpwiotnqdbzyokyf.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<Supabase Secret key default 값>

CLOUDINARY_CLOUD_NAME=<Cloudinary cloud name>
CLOUDINARY_API_KEY=<Cloudinary api key>
CLOUDINARY_API_SECRET=<Cloudinary api secret>

NCP_ACCESS_KEY=<NCP access key>
NCP_SECRET_KEY=<NCP secret key>
NCP_SENDER_ADDRESS=noreply@humancompletion.org
NCP_SENDER_NAME=전인교육학회
SEND_BATCH_SIZE=100
```

Gmail SMTP를 테스트 대안으로 사용할 경우 `GMAIL_USER`, `GMAIL_APP_PASSWORD`도 추가합니다.

## 4. 접근 정책

`ADMIN_PASSWORD`가 설정되면 편집기와 관리 API는 Basic Auth로 보호됩니다.

인증 없이 공개되는 경로:

- `/api/subscribe`
- `/api/unsubscribe`
- `/health`

## 5. 도메인 연결

Vercel Project Settings > Domains에서 `newsletter.humancompletion.org`를 추가합니다. Vercel이 안내하는 DNS 레코드를 `humancompletion.org` DNS에 등록한 뒤 Verify 상태와 HTTPS 인증서 발급을 확인합니다.

## 6. 운영 발송 구조

`POST /api/send`는 발송 작업과 대상자를 Supabase에 저장하고 즉시 `job_id`를 반환합니다. 프론트엔드는 `POST /api/send/{job_id}/process`를 반복 호출해 `SEND_BATCH_SIZE` 단위로 발송을 진행한 뒤 `GET /api/send/{job_id}`로 상태를 갱신합니다.

이 구조는 Vercel 서버리스 함수가 긴 백그라운드 작업을 계속 붙잡지 않도록 하기 위한 방식입니다.

## 7. 로컬 확인

```bash
cd frontend
npm install
npm run build
```

백엔드는 Supabase 환경변수가 없으면 로컬 파일 저장 fallback으로 동작합니다. 실제 운영 데이터 흐름을 확인하려면 로컬 `.env`에도 `SUPABASE_URL`과 `SUPABASE_SERVICE_ROLE_KEY`를 넣은 뒤 FastAPI를 실행합니다.
