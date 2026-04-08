"""
NCP Cloud Outbound Mailer — 청크 분할 + 변수 치환 + 안전 발송

10만명 발송 전략:
- chunk_size: 500명/요청 (NCP 한도 1,000명의 절반으로 안전 마진)
- chunks 사이 sleep: 5초 (TPS 보호 + ISP 평판 보호)
- 변수 치환: ${(UNSUB_URL)} 으로 수신자별 수신거부 링크 개인화
- 1,000건 단위로 진행 콜백 호출
"""
import base64
import hashlib
import hmac
import time
from urllib.parse import quote
import httpx
from .base import SendResult, Recipient
from .. import config

API_HOST = "https://mail.apigw.ntruss.com"
API_PATH = "/api/v1/mails"

CHUNK_SIZE = 500           # 한 요청 당 수신자
SLEEP_BETWEEN_CHUNKS = 5.0 # 초
MAX_RETRIES = 3
RETRY_DELAY = 10.0


def _make_signature(method: str, uri: str, timestamp: str, access_key: str, secret_key: str) -> str:
    msg = f"{method} {uri}\n{timestamp}\n{access_key}"
    digest = hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_headers(ak: str, sk: str) -> dict:
    ts = str(int(time.time() * 1000))
    sig = _make_signature("POST", API_PATH, ts, ak, sk)
    return {
        "Content-Type": "application/json",
        "x-ncp-apigw-timestamp": ts,
        "x-ncp-iam-access-key": ak,
        "x-ncp-apigw-signature-v2": sig,
    }


class NCPSender:
    def send(self, html, subject, recipients, from_addr, from_name="전인교육학회", on_progress=None):
        result = SendResult()
        ak = config.NCP_ACCESS_KEY
        sk = config.NCP_SECRET_KEY
        sender = from_addr or config.NCP_SENDER_ADDRESS
        if not (ak and sk and sender):
            result.errors.append("NCP_ACCESS_KEY / NCP_SECRET_KEY / NCP_SENDER_ADDRESS not set")
            result.failed = len(recipients)
            return result

        # body의 [[UNSUB_URL]] 을 NCP 변수 ${(UNSUB_URL)} 로 치환
        body = html.replace("[[UNSUB_URL]]", "${(UNSUB_URL)}")
        sender_name = from_name or config.NCP_SENDER_NAME

        total = len(recipients)
        total_chunks = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
        if on_progress:
            on_progress(total_chunks=total_chunks, current_chunk=0, sent=0, failed=0)

        for chunk_i, start in enumerate(range(0, total, CHUNK_SIZE), start=1):
            chunk = recipients[start:start + CHUNK_SIZE]
            payload_recipients = [
                {
                    "address": r.email,
                    "name": r.name or "",
                    "type": "R",
                    "parameters": {
                        "UNSUB_URL": f"{config.PUBLIC_BASE_URL}/api/unsubscribe?email={quote(r.email)}"
                    },
                }
                for r in chunk
            ]
            body_payload = {
                "senderAddress": sender,
                "senderName": sender_name,
                "title": subject,
                "body": body,
                "individual": True,
                "advertising": False,
                "recipients": payload_recipients,
            }

            chunk_sent, chunk_failed, error_msg = self._post_with_retry(ak, sk, body_payload)
            result.sent += chunk_sent
            result.failed += chunk_failed
            if error_msg:
                result.errors.append(f"chunk {chunk_i}: {error_msg}")

            # 진행 보고
            if on_progress:
                on_progress(
                    current_chunk=chunk_i,
                    total_chunks=total_chunks,
                    sent=result.sent,
                    failed=result.failed,
                )

            # 마지막 청크가 아니면 sleep
            if chunk_i < total_chunks:
                time.sleep(SLEEP_BETWEEN_CHUNKS)

        return result

    def _post_with_retry(self, ak, sk, body_payload) -> tuple[int, int, str]:
        n = len(body_payload["recipients"])
        last_err = ""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                headers = _build_headers(ak, sk)
                resp = httpx.post(API_HOST + API_PATH, headers=headers, json=body_payload, timeout=120.0)
                if resp.status_code in (200, 201):
                    return n, 0, ""
                # 429 (rate limit) 또는 5xx → 재시도
                last_err = f"NCP {resp.status_code}: {resp.text[:200]}"
                if resp.status_code == 429 or resp.status_code >= 500:
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY * attempt)
                        continue
                # 4xx (auth/payload 오류)는 즉시 실패
                return 0, n, last_err
            except Exception as e:
                last_err = str(e)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
                    continue
        return 0, n, last_err
