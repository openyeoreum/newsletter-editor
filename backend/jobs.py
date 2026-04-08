"""
백그라운드 발송 작업 진행 상황 추적
- 메모리 기반 단순 dict (단일 컨테이너 가정)
- 컨테이너 재시작 시 사라짐 — 진행 중인 작업은 잃을 수 있으므로
  10만 명 발송 중 재시작 금지
"""
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Job:
    id: str
    status: str = "pending"   # pending | running | done | failed
    total: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    started_at: float = 0
    finished_at: Optional[float] = None
    errors: list[str] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elapsed"] = round((self.finished_at or time.time()) - self.started_at, 1) if self.started_at else 0
        d["progress_percent"] = round((self.sent + self.failed) / self.total * 100, 1) if self.total else 0
        return d


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(total: int) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], total=total, started_at=time.time(), status="pending")
    with _lock:
        _jobs[job.id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 20) -> list[dict]:
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)[:limit]
        return [j.to_dict() for j in items]


def update(job_id: str, **kwargs):
    with _lock:
        j = _jobs.get(job_id)
        if not j:
            return
        for k, v in kwargs.items():
            if k == "errors_append":
                j.errors.append(v)
            else:
                setattr(j, k, v)
