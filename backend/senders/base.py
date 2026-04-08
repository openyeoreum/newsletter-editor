from dataclasses import dataclass, field
from typing import Protocol


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
    ) -> SendResult: ...
