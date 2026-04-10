import csv
import io
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from . import config

DRAFTS = Path(config.DRAFTS_DIR)
DRAFTS.mkdir(parents=True, exist_ok=True)


def list_drafts() -> list[dict]:
    items = []
    for f in sorted(DRAFTS.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            items.append({"id": d.get("id", f.stem), "name": d.get("name", f.stem), "template": d.get("template", "classic")})
        except Exception:
            pass
    return items


def get_draft(draft_id: str) -> dict | None:
    f = DRAFTS / f"{draft_id}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def save_draft(draft: dict) -> dict:
    # id가 주어지면 덮어쓰기, 없으면 새 파일 생성
    if draft.get("id"):
        f = DRAFTS / f"{draft['id']}.json"
        if f.exists():
            f.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
            return draft

    # 새 파일: 같은 이름 있으면 (2), (3)... 자동 부여
    base_name = (draft.get("name") or "untitled").strip()
    existing_names = set()
    for f in DRAFTS.glob("*.json"):
        try:
            existing_names.add(json.loads(f.read_text(encoding="utf-8")).get("name", ""))
        except Exception:
            pass
    final_name = base_name
    n = 1
    while final_name in existing_names:
        n += 1
        final_name = f"{base_name} ({n})"
    draft["name"] = final_name
    draft["id"] = uuid.uuid4().hex[:8]
    f = DRAFTS / f"{draft['id']}.json"
    f.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def rename_draft(draft_id: str, new_name: str) -> dict | None:
    f = DRAFTS / f"{draft_id}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    d["name"] = new_name.strip() or d.get("name", "untitled")
    f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def delete_draft(draft_id: str) -> bool:
    f = DRAFTS / f"{draft_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False


# ========== 대표 초안 ==========

_DEFAULT_DRAFT_FILE = DRAFTS / ".default"


def get_default_draft_id() -> str | None:
    if _DEFAULT_DRAFT_FILE.exists():
        draft_id = _DEFAULT_DRAFT_FILE.read_text(encoding="utf-8").strip()
        if draft_id and (DRAFTS / f"{draft_id}.json").exists():
            return draft_id
    return None


def set_default_draft_id(draft_id: str | None) -> bool:
    if draft_id is None:
        if _DEFAULT_DRAFT_FILE.exists():
            _DEFAULT_DRAFT_FILE.unlink()
        return True
    if not (DRAFTS / f"{draft_id}.json").exists():
        return False
    _DEFAULT_DRAFT_FILE.write_text(draft_id, encoding="utf-8")
    return True


# ========== 수신거부 관리 ==========

UNSUB = Path(config.UNSUBSCRIBED_FILE)


def load_unsubscribed() -> set[str]:
    if not UNSUB.exists():
        return set()
    return {line.strip().lower() for line in UNSUB.read_text(encoding="utf-8").splitlines() if line.strip()}


def add_unsubscribed(email: str) -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
    UNSUB.parent.mkdir(parents=True, exist_ok=True)
    existing = load_unsubscribed()
    if email in existing:
        return False
    with UNSUB.open("a", encoding="utf-8") as f:
        f.write(email + "\n")
    return True


def remove_unsubscribed(email: str) -> bool:
    if not UNSUB.exists():
        return False
    email = email.strip().lower()
    lines = [l for l in UNSUB.read_text(encoding="utf-8").splitlines() if l.strip().lower() != email]
    UNSUB.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    return True


# ========== 구독자(수신동의) 관리 ==========

SUBS = Path(config.SUBSCRIBERS_FILE)
_SUBS_HEADER = ["email", "name", "organization", "subscribed_at"]


def _ensure_subs_file():
    SUBS.parent.mkdir(parents=True, exist_ok=True)
    if not SUBS.exists():
        SUBS.write_text(",".join(_SUBS_HEADER) + "\n", encoding="utf-8")


def load_subscribers() -> list[dict]:
    if not SUBS.exists():
        return []
    rows = []
    reader = csv.DictReader(io.StringIO(SUBS.read_text(encoding="utf-8")))
    for row in reader:
        if row.get("email"):
            rows.append({k: (row.get(k) or "").strip() for k in _SUBS_HEADER})
    return rows


def add_subscriber(email: str, name: str = "", organization: str = "") -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
    _ensure_subs_file()
    existing = {s["email"] for s in load_subscribers()}
    if email in existing:
        return False
    with SUBS.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_SUBS_HEADER)
        writer.writerow({
            "email": email,
            "name": name.strip(),
            "organization": organization.strip(),
            "subscribed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
    return True


def remove_subscriber(email: str) -> bool:
    if not SUBS.exists():
        return False
    email = email.strip().lower()
    rows = [s for s in load_subscribers() if s["email"] != email]
    _ensure_subs_file()
    with SUBS.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_SUBS_HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return True


def export_subscribers_csv() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_SUBS_HEADER)
    writer.writeheader()
    writer.writerows(load_subscribers())
    return buf.getvalue()
