"""
NCP Cloud Outbound Mailer
https://api.ncloud-docs.com/docs/ai-application-service-cloudoutboundmailer
"""
import base64
import hashlib
import hmac
import time
import httpx
from .base import SendResult
from .. import config

API_HOST = "https://mail.apigw.ntruss.com"
API_PATH = "/api/v1/mails"


def _make_signature(method: str, uri: str, timestamp: str, access_key: str, secret_key: str) -> str:
    msg = f"{method} {uri}\n{timestamp}\n{access_key}"
    digest = hmac.new(secret_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


class NCPSender:
    def send(self, html, subject, recipients, from_addr, from_name="전인교육학회"):
        result = SendResult()
        ak = config.NCP_ACCESS_KEY
        sk = config.NCP_SECRET_KEY
        sender = from_addr or config.NCP_SENDER_ADDRESS
        if not (ak and sk and sender):
            result.errors.append("NCP_ACCESS_KEY / NCP_SECRET_KEY / NCP_SENDER_ADDRESS not set")
            result.failed = len(recipients)
            return result

        # NCP는 단일 요청에 최대 1,000명 수신자 가능
        ts = str(int(time.time() * 1000))
        sig = _make_signature("POST", API_PATH, ts, ak, sk)
        headers = {
            "Content-Type": "application/json",
            "x-ncp-apigw-timestamp": ts,
            "x-ncp-iam-access-key": ak,
            "x-ncp-apigw-signature-v2": sig,
        }
        body = {
            "senderAddress": sender,
            "senderName": from_name or config.NCP_SENDER_NAME,
            "title": subject,
            "body": html,
            "individual": True,
            "advertising": False,
            "recipients": [
                {"address": r.email, "name": r.name or "", "type": "R"}
                for r in recipients
            ],
        }
        try:
            r = httpx.post(API_HOST + API_PATH, headers=headers, json=body, timeout=60.0)
            if r.status_code in (200, 201):
                result.sent = len(recipients)
            else:
                result.failed = len(recipients)
                result.errors.append(f"NCP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            result.failed = len(recipients)
            result.errors.append(f"NCP request failed: {e}")
        return result
