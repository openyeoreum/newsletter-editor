"""
NCP Cloud Outbound Mailer
https://api.ncloud-docs.com/docs/ai-application-service-cloudoutboundmailer
"""
import base64
import hashlib
import hmac
import time
import httpx
from .base import SendResult, personalize
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

        # 수신거부 링크가 수신자별로 달라야 하므로 1명씩 발송
        for rcpt in recipients:
            try:
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
                    "body": personalize(html, rcpt.email),
                    "individual": True,
                    "advertising": False,
                    "recipients": [
                        {"address": rcpt.email, "name": rcpt.name or "", "type": "R"}
                    ],
                }
                resp = httpx.post(API_HOST + API_PATH, headers=headers, json=body, timeout=60.0)
                if resp.status_code in (200, 201):
                    result.sent += 1
                else:
                    result.failed += 1
                    result.errors.append(f"{rcpt.email}: NCP {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                result.failed += 1
                result.errors.append(f"{rcpt.email}: {e}")
        return result
