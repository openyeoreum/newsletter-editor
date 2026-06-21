"""
발송 작업 저장소

Vercel 서버리스 환경에서는 백그라운드 스레드와 메모리 상태를 유지할 수 없으므로
Supabase의 send_jobs / send_job_recipients 테이블에 진행 상황을 저장한다.
Supabase 환경변수가 없을 때만 로컬 개발용 메모리 저장소를 사용한다.
"""
from __future__ import annotations

import math
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from . import storage, supabase_rest
from .senders.base import Recipient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _job_from_row(row: dict) -> dict:
    started = _parse_dt(row.get("started_at"))
    finished = _parse_dt(row.get("finished_at"))
    now = datetime.now(timezone.utc)
    elapsed = round(((finished or now) - started).total_seconds(), 1) if started else 0
    total = int(row.get("total") or 0)
    processed = int(row.get("sent") or 0) + int(row.get("failed") or 0)
    errors = row.get("errors") or []
    if not isinstance(errors, list):
        errors = []

    out = {
        "id": row["id"],
        "sender": row.get("sender") or "",
        "template": row.get("template") or "classic",
        "subject": row.get("subject") or "",
        "from_addr": row.get("from_addr") or "",
        "from_name": row.get("from_name") or "전인교육학회",
        "data": row.get("data") or {},
        "status": row.get("status") or "pending",
        "total": total,
        "sent": int(row.get("sent") or 0),
        "failed": int(row.get("failed") or 0),
        "skipped": int(row.get("skipped") or 0),
        "current_chunk": int(row.get("current_chunk") or 0),
        "total_chunks": int(row.get("total_chunks") or 0),
        "errors": errors,
        "message": row.get("message") or "",
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "elapsed": elapsed,
        "progress_percent": round(processed / total * 100, 1) if total else 0,
    }
    return out


def _summary_message(job: dict) -> str:
    return f"발송 완료 - {job['sent']}건 성공 / {job['failed']}건 실패 / {job['skipped']}건 수신거부 제외"


# ========== Supabase implementation ==========

def _sb_create_job(payload: dict, recipients: list[Recipient], skipped: int, batch_size: int) -> dict:
    job_id = uuid.uuid4().hex[:12]
    total = len(recipients)
    total_chunks = math.ceil(total / batch_size) if total else 0
    job_payload = {
        "id": job_id,
        "sender": payload["sender"],
        "template": payload["template"],
        "subject": payload["subject"],
        "from_addr": payload.get("from_addr") or "",
        "from_name": payload.get("from_name") or "전인교육학회",
        "data": payload.get("data") or {},
        "status": "pending",
        "total": total,
        "sent": 0,
        "failed": 0,
        "skipped": skipped,
        "current_chunk": 0,
        "total_chunks": total_chunks,
        "errors": [],
        "message": "발송 대기 중",
    }
    supabase_rest.insert("send_jobs", job_payload)
    rows = [
        {
            "job_id": job_id,
            "email": r.email.strip().lower(),
            "name": r.name or "",
            "status": "pending",
        }
        for r in recipients
    ]
    if rows:
        supabase_rest.insert("send_job_recipients", rows)
    return _job_from_row({**job_payload, "started_at": _now_iso(), "finished_at": None})


def _sb_get_job(job_id: str) -> dict | None:
    rows = supabase_rest.select("send_jobs", "*", {"id": f"eq.{job_id}"}, limit=1)
    return _job_from_row(rows[0]) if rows else None


def _sb_list_jobs(limit: int = 20) -> list[dict]:
    rows = supabase_rest.select("send_jobs", "*", order="started_at.desc", limit=limit)
    return [_job_from_row(row) for row in rows]


def _sb_set_running(job_id: str) -> dict | None:
    supabase_rest.update("send_jobs", {"status": "running"}, {"id": f"eq.{job_id}"})
    return _sb_get_job(job_id)


def _sb_pending_recipients(job_id: str, limit: int) -> list[dict]:
    rows = supabase_rest.select(
        "send_job_recipients",
        "id,email,name",
        {"job_id": f"eq.{job_id}", "status": "eq.pending"},
        order="created_at.asc",
        limit=limit,
    )
    return rows


def _sb_mark_batch_result(job_id: str, sent_ids: list[str], failed_rows: list[dict]) -> dict:
    now = _now_iso()
    if sent_ids:
        supabase_rest.update(
            "send_job_recipients",
            {"status": "sent", "processed_at": now},
            {"id": f"in.({','.join(str(i) for i in sent_ids)})"},
        )
    for row in failed_rows:
        supabase_rest.update(
            "send_job_recipients",
            {"status": "failed", "error": row.get("error") or "발송 실패", "processed_at": now},
            {"id": f"eq.{row['id']}"},
        )

    job = _sb_get_job(job_id)
    if not job:
        raise KeyError(job_id)
    sent = job["sent"] + len(sent_ids)
    failed = job["failed"] + len(failed_rows)
    processed = sent + failed
    done = processed >= job["total"]
    errors = list(job.get("errors") or [])
    errors.extend([f"{r.get('email')}: {r.get('error')}" for r in failed_rows])
    errors = errors[:50]
    payload = {
        "sent": sent,
        "failed": failed,
        "current_chunk": min(job["total_chunks"], job["current_chunk"] + 1),
        "errors": errors,
        "status": "done" if done else "running",
        "message": "",
    }
    if done:
        payload["finished_at"] = now
        payload["message"] = _summary_message({**job, "sent": sent, "failed": failed})
    supabase_rest.update("send_jobs", payload, {"id": f"eq.{job_id}"})
    return _sb_get_job(job_id)


def _sb_finish_if_complete(job_id: str) -> dict | None:
    job = _sb_get_job(job_id)
    if not job:
        return None
    if job["status"] in {"done", "failed"}:
        return job
    if job["sent"] + job["failed"] >= job["total"]:
        payload = {"status": "done", "finished_at": _now_iso(), "message": _summary_message(job)}
        supabase_rest.update("send_jobs", payload, {"id": f"eq.{job_id}"})
        return _sb_get_job(job_id)
    return job


def _sb_fail_job(job_id: str, message: str, errors: list[str] | None = None) -> dict | None:
    job = _sb_get_job(job_id)
    if not job:
        return None
    existing = list(job.get("errors") or [])
    if errors:
        existing.extend(errors)
    elif message:
        existing.append(message)
    payload = {
        "status": "failed",
        "finished_at": _now_iso(),
        "message": message,
        "errors": existing[:50],
    }
    supabase_rest.update("send_jobs", payload, {"id": f"eq.{job_id}"})
    return _sb_get_job(job_id)


# ========== Local fallback ==========

@dataclass
class LocalJob:
    id: str
    sender: str
    template: str
    subject: str
    from_addr: str
    from_name: str
    data: dict
    status: str = "pending"
    total: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    current_chunk: int = 0
    total_chunks: int = 0
    started_at: float = 0
    finished_at: Optional[float] = None
    errors: list[str] = field(default_factory=list)
    message: str = "발송 대기 중"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elapsed"] = round((self.finished_at or time.time()) - self.started_at, 1) if self.started_at else 0
        d["progress_percent"] = round((self.sent + self.failed) / self.total * 100, 1) if self.total else 0
        return d


_jobs: dict[str, LocalJob] = {}
_recipients: dict[str, list[dict]] = {}
_lock = threading.Lock()


def _local_create_job(payload: dict, recipients: list[Recipient], skipped: int, batch_size: int) -> dict:
    job_id = uuid.uuid4().hex[:12]
    total = len(recipients)
    job = LocalJob(
        id=job_id,
        sender=payload["sender"],
        template=payload["template"],
        subject=payload["subject"],
        from_addr=payload.get("from_addr") or "",
        from_name=payload.get("from_name") or "전인교육학회",
        data=payload.get("data") or {},
        total=total,
        skipped=skipped,
        total_chunks=math.ceil(total / batch_size) if total else 0,
        started_at=time.time(),
    )
    rows = [
        {
            "id": uuid.uuid4().hex,
            "email": r.email.strip().lower(),
            "name": r.name or "",
            "status": "pending",
            "error": "",
        }
        for r in recipients
    ]
    with _lock:
        _jobs[job_id] = job
        _recipients[job_id] = rows
    return job.to_dict()


def _local_get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return job.to_dict() if job else None


def _local_list_jobs(limit: int = 20) -> list[dict]:
    with _lock:
        items = sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)[:limit]
        return [j.to_dict() for j in items]


def _local_set_running(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job.status = "running"
        return job.to_dict()


def _local_pending_recipients(job_id: str, limit: int) -> list[dict]:
    with _lock:
        return [r.copy() for r in _recipients.get(job_id, []) if r["status"] == "pending"][:limit]


def _local_mark_batch_result(job_id: str, sent_ids: list[str], failed_rows: list[dict]) -> dict:
    with _lock:
        job = _jobs[job_id]
        sent_set = set(sent_ids)
        failed_by_id = {r["id"]: r for r in failed_rows}
        for row in _recipients.get(job_id, []):
            if row["id"] in sent_set:
                row["status"] = "sent"
            if row["id"] in failed_by_id:
                row["status"] = "failed"
                row["error"] = failed_by_id[row["id"]].get("error") or "발송 실패"
        job.sent += len(sent_ids)
        job.failed += len(failed_rows)
        job.current_chunk = min(job.total_chunks, job.current_chunk + 1)
        job.errors.extend([f"{r.get('email')}: {r.get('error')}" for r in failed_rows])
        job.errors = job.errors[:50]
        if job.sent + job.failed >= job.total:
            job.status = "done"
            job.finished_at = time.time()
            job.message = _summary_message(job.to_dict())
        else:
            job.status = "running"
        return job.to_dict()


def _local_finish_if_complete(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job.status in {"done", "failed"}:
            return job.to_dict()
        if job.sent + job.failed >= job.total:
            job.status = "done"
            job.finished_at = time.time()
            job.message = _summary_message(job.to_dict())
        return job.to_dict()


def _local_fail_job(job_id: str, message: str, errors: list[str] | None = None) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job.status = "failed"
        job.finished_at = time.time()
        job.message = message
        job.errors.extend((errors or [message])[:50])
        job.errors = job.errors[:50]
        return job.to_dict()


# ========== Public API ==========

def create_job(payload: dict, recipients: list[Recipient], skipped: int = 0, batch_size: int = 100) -> dict:
    if storage.using_supabase():
        return _sb_create_job(payload, recipients, skipped, batch_size)
    return _local_create_job(payload, recipients, skipped, batch_size)


def get_job(job_id: str) -> dict | None:
    if storage.using_supabase():
        return _sb_get_job(job_id)
    return _local_get_job(job_id)


def list_jobs(limit: int = 20) -> list[dict]:
    if storage.using_supabase():
        return _sb_list_jobs(limit)
    return _local_list_jobs(limit)


def set_running(job_id: str) -> dict | None:
    if storage.using_supabase():
        return _sb_set_running(job_id)
    return _local_set_running(job_id)


def get_pending_recipients(job_id: str, limit: int) -> list[dict]:
    if storage.using_supabase():
        return _sb_pending_recipients(job_id, limit)
    return _local_pending_recipients(job_id, limit)


def mark_batch_result(job_id: str, sent_ids: list[str], failed_rows: list[dict]) -> dict:
    if storage.using_supabase():
        return _sb_mark_batch_result(job_id, sent_ids, failed_rows)
    return _local_mark_batch_result(job_id, sent_ids, failed_rows)


def finish_if_complete(job_id: str) -> dict | None:
    if storage.using_supabase():
        return _sb_finish_if_complete(job_id)
    return _local_finish_if_complete(job_id)


def fail_job(job_id: str, message: str, errors: list[str] | None = None) -> dict | None:
    if storage.using_supabase():
        return _sb_fail_job(job_id, message, errors)
    return _local_fail_job(job_id, message, errors)
