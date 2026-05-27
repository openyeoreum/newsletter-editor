from .base import Sender, SendResult
from .gmail_smtp import GmailSender
from .mailhog import MailHogSender
from .ncp import NCPSender
from .. import config

REGISTRY: dict[str, type[Sender]] = {
    "gmail": GmailSender,
    "mailhog": MailHogSender,
    "ncp": NCPSender,
}

_AVAILABLE = [
    {"key": "mailhog", "label": "MailHog (로컬 테스트)", "bulk": True},
    {"key": "gmail", "label": "Gmail SMTP (개인/소규모, 일 500건 한도)", "bulk": False},
    {"key": "ncp", "label": "NCP Cloud Outbound Mailer (대량 발송, 권장)", "bulk": True},
]


def get_available():
    if config.APP_ENV == "production":
        return [s for s in _AVAILABLE if s["key"] != "mailhog"]
    return _AVAILABLE


AVAILABLE = get_available()


def get_sender(key: str) -> Sender:
    if config.APP_ENV == "production" and key == "mailhog":
        raise ValueError("MailHog is only available outside production")
    if key not in REGISTRY:
        raise ValueError(f"Unknown sender: {key}")
    return REGISTRY[key]()
