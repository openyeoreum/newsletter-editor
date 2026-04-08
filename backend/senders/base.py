from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import quote
from .. import config


def personalize(html: str, email: str) -> str:
    """[[UNSUB_URL]] 플레이스홀더를 수신자별 수신거부 URL로 치환"""
    url = f"{config.PUBLIC_BASE_URL}/api/unsubscribe?email={quote(email)}"
    return html.replace("[[UNSUB_URL]]", url)


@dataclass
class Recipient:
    email: str
    name: str | None = None


@dataclass
class SendResult:
    sent: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class Sender(Protocol):
    def send(
        self,
        html: str,
        subject: str,
        recipients: list[Recipient],
        from_addr: str,
        from_name: str = "전인교육학회",
        on_progress=None,
    ) -> SendResult: ...
