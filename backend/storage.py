import csv
import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from . import config

try:
    from supabase import create_client
except Exception:  # pragma: no cover - local fallback when dependency is absent
    create_client = None


_client = None


def using_supabase() -> bool:
    return bool(config.USE_SUPABASE and create_client)


def client():
    global _client
    if not using_supabase():
        raise RuntimeError("Supabase is not configured")
    if _client is None:
        _client = create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)
    return _client


# ========== Local development fallback ==========

DRAFTS = Path(config.DRAFTS_DIR)
SAMPLE_DRAFT = Path(config.PROJECT_ROOT) / "drafts" / "sample.json"
UNSUB = Path(config.UNSUBSCRIBED_FILE)
SUBS = Path(config.SUBSCRIBERS_FILE)
_SUBS_HEADER = ["email", "name", "organization", "subscribed_at"]
_UNSUB_HEADER = ["email", "unsubscribed_at"]


def _local_list_drafts() -> list[dict]:
    if not DRAFTS.exists():
        return []
    items = []
    for f in sorted(DRAFTS.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            items.append({"id": d.get("id", f.stem), "name": d.get("name", f.stem), "template": d.get("template", "classic")})
        except Exception:
            pass
    return items


def _local_get_draft(draft_id: str) -> dict | None:
    f = DRAFTS / f"{draft_id}.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _unique_name(base_name: str, existing_names: set[str]) -> str:
    final_name = base_name
    n = 1
    while final_name in existing_names:
        n += 1
        final_name = f"{base_name} ({n})"
    return final_name


def _local_save_draft(draft: dict) -> dict:
    DRAFTS.mkdir(parents=True, exist_ok=True)
    if draft.get("id"):
        f = DRAFTS / f"{draft['id']}.json"
        if f.exists():
            f.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
            return draft

    base_name = (draft.get("name") or "untitled").strip()
    existing_names = {d["name"] for d in _local_list_drafts()}
    draft["name"] = _unique_name(base_name, existing_names)
    draft["id"] = uuid.uuid4().hex[:8]
    (DRAFTS / f"{draft['id']}.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def _local_rename_draft(draft_id: str, new_name: str) -> dict | None:
    d = _local_get_draft(draft_id)
    if not d:
        return None
    d["name"] = new_name.strip() or d.get("name", "untitled")
    (DRAFTS / f"{draft_id}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


def _local_delete_draft(draft_id: str) -> bool:
    f = DRAFTS / f"{draft_id}.json"
    if f.exists():
        f.unlink()
        return True
    return False


_DEFAULT_DRAFT_FILE = DRAFTS / ".default"


def _local_get_default_draft_id() -> str | None:
    if _DEFAULT_DRAFT_FILE.exists():
        draft_id = _DEFAULT_DRAFT_FILE.read_text(encoding="utf-8").strip()
        if draft_id and (DRAFTS / f"{draft_id}.json").exists():
            return draft_id
    return None


def _local_set_default_draft_id(draft_id: str | None) -> bool:
    if draft_id is None:
        if _DEFAULT_DRAFT_FILE.exists():
            _DEFAULT_DRAFT_FILE.unlink()
        return True
    if not (DRAFTS / f"{draft_id}.json").exists():
        return False
    DRAFTS.mkdir(parents=True, exist_ok=True)
    _DEFAULT_DRAFT_FILE.write_text(draft_id, encoding="utf-8")
    return True


# ========== Drafts ==========

def _draft_from_row(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row.get("name") or "untitled",
        "template": row.get("template") or "classic",
        "subject": row.get("subject") or "",
        "data": row.get("data") or {},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_sample_draft() -> dict | None:
    if not SAMPLE_DRAFT.exists():
        return None
    try:
        return json.loads(SAMPLE_DRAFT.read_text(encoding="utf-8"))
    except Exception:
        return None


def _supabase_draft_exists(draft_id: str) -> bool:
    rows = client().table("drafts").select("id").eq("id", draft_id).limit(1).execute().data or []
    return bool(rows)


def _draft_has_meaningful_content(draft: dict | None) -> bool:
    if not draft:
        return False
    data = draft.get("data") or {}
    greeting = data.get("greeting") or {}
    articles = data.get("articles") or []
    has_greeting = bool((greeting.get("body") or "").strip())
    has_articles = any((a.get("title") or "").strip() or (a.get("image") or "").strip() for a in articles if isinstance(a, dict))
    return has_greeting and has_articles


def _get_supabase_draft_row(draft_id: str) -> dict | None:
    rows = client().table("drafts").select("*").eq("id", draft_id).limit(1).execute().data or []
    return rows[0] if rows else None


def _ensure_sample_draft() -> None:
    if not using_supabase():
        return
    sample = _load_sample_draft()
    if not sample:
        return
    sample_id = sample.get("id") or "sample"
    payload = {
        "id": sample_id,
        "name": sample.get("name") or "예시 초안",
        "template": sample.get("template") or "classic",
        "subject": sample.get("subject") or "",
        "data": sample.get("data") or {},
        "updated_at": _utc_now(),
    }

    sample_row = _get_supabase_draft_row(sample_id)
    if not _draft_has_meaningful_content(sample_row):
        client().table("drafts").upsert(payload).execute()

    rows = client().table("app_settings").select("value").eq("key", "default_draft_id").limit(1).execute().data or []
    default_value = rows[0].get("value") if rows else None
    default_id = default_value.get("id") if isinstance(default_value, dict) else None
    default_row = _get_supabase_draft_row(default_id) if default_id else None
    if not _draft_has_meaningful_content(default_row):
        client().table("app_settings").upsert({"key": "default_draft_id", "value": {"id": payload["id"]}}).execute()


def list_drafts() -> list[dict]:
    if not using_supabase():
        return _local_list_drafts()
    _ensure_sample_draft()
    rows = client().table("drafts").select("id,name,template").order("updated_at", desc=True).execute().data or []
    return [{"id": r["id"], "name": r.get("name") or r["id"], "template": r.get("template") or "classic"} for r in rows]


def get_draft(draft_id: str) -> dict | None:
    if not using_supabase():
        return _local_get_draft(draft_id)
    _ensure_sample_draft()
    rows = client().table("drafts").select("*").eq("id", draft_id).limit(1).execute().data or []
    return _draft_from_row(rows[0]) if rows else None


def save_draft(draft: dict) -> dict:
    if not using_supabase():
        return _local_save_draft(draft)

    draft = dict(draft)
    now_id = draft.get("id") or uuid.uuid4().hex[:8]
    if not draft.get("id"):
        base_name = (draft.get("name") or "untitled").strip()
        existing_names = {d["name"] for d in list_drafts()}
        draft["name"] = _unique_name(base_name, existing_names)
    draft["id"] = now_id

    payload = {
        "id": draft["id"],
        "name": draft.get("name") or "untitled",
        "template": draft.get("template") or "classic",
        "subject": draft.get("subject") or "",
        "data": draft.get("data") or {},
        "updated_at": _utc_now(),
    }
    client().table("drafts").upsert(payload).execute()
    return _draft_from_row(payload)


def rename_draft(draft_id: str, new_name: str) -> dict | None:
    if not using_supabase():
        return _local_rename_draft(draft_id, new_name)
    payload = {"name": new_name.strip() or "untitled", "updated_at": _utc_now()}
    rows = client().table("drafts").update(payload).eq("id", draft_id).execute().data or []
    return get_draft(draft_id) if rows else None


def delete_draft(draft_id: str) -> bool:
    if not using_supabase():
        return _local_delete_draft(draft_id)
    client().table("drafts").delete().eq("id", draft_id).execute()
    return True


def get_default_draft_id() -> str | None:
    if not using_supabase():
        return _local_get_default_draft_id()
    _ensure_sample_draft()
    rows = client().table("app_settings").select("value").eq("key", "default_draft_id").limit(1).execute().data or []
    if not rows:
        return None
    value = rows[0].get("value")
    return value.get("id") if isinstance(value, dict) else None


def set_default_draft_id(draft_id: str | None) -> bool:
    if not using_supabase():
        return _local_set_default_draft_id(draft_id)
    if draft_id is not None and not get_draft(draft_id):
        return False
    payload = {"key": "default_draft_id", "value": {"id": draft_id} if draft_id else None}
    client().table("app_settings").upsert(payload).execute()
    return True


# ========== Unsubscribed ==========

def load_unsubscribed() -> set[str]:
    if not using_supabase():
        if not UNSUB.exists():
            return set()
        return {line.strip().lower() for line in UNSUB.read_text(encoding="utf-8").splitlines() if line.strip()}
    rows = client().table("unsubscribed").select("email").execute().data or []
    return {r["email"].strip().lower() for r in rows if r.get("email")}


def add_unsubscribed(email: str) -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
    if not using_supabase():
        UNSUB.parent.mkdir(parents=True, exist_ok=True)
        existing = load_unsubscribed()
        if email in existing:
            return False
        with UNSUB.open("a", encoding="utf-8") as f:
            f.write(email + "\n")
        return True
    existed = email in load_unsubscribed()
    if existed:
        return False
    try:
        client().table("unsubscribed").insert({"email": email}).execute()
        return True
    except Exception as exc:
        message = str(exc).lower()
        if "23505" in message or "duplicate" in message or "unique" in message:
            return False
        raise


def remove_unsubscribed(email: str) -> bool:
    email = email.strip().lower()
    if not using_supabase():
        if not UNSUB.exists():
            return False
        lines = [l for l in UNSUB.read_text(encoding="utf-8").splitlines() if l.strip().lower() != email]
        UNSUB.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
        return True
    client().table("unsubscribed").delete().eq("email", email).execute()
    return True


def export_unsubscribed_csv() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_UNSUB_HEADER)
    writer.writeheader()
    if not using_supabase():
        writer.writerows({"email": email, "unsubscribed_at": ""} for email in sorted(load_unsubscribed()))
        return buf.getvalue()
    rows = (
        client()
        .table("unsubscribed")
        .select("email,unsubscribed_at")
        .order("unsubscribed_at", desc=True)
        .execute()
        .data
        or []
    )
    writer.writerows(rows)
    return buf.getvalue()


# ========== Subscribers ==========

def _ensure_subs_file():
    SUBS.parent.mkdir(parents=True, exist_ok=True)
    if not SUBS.exists():
        SUBS.write_text(",".join(_SUBS_HEADER) + "\n", encoding="utf-8")


def load_subscribers() -> list[dict]:
    if not using_supabase():
        if not SUBS.exists():
            return []
        rows = []
        reader = csv.DictReader(io.StringIO(SUBS.read_text(encoding="utf-8")))
        for row in reader:
            if row.get("email"):
                rows.append({k: (row.get(k) or "").strip() for k in _SUBS_HEADER})
        return rows
    rows = client().table("subscribers").select("*").execute().data or []
    rows.sort(key=lambda row: row.get("subscribed_at") or row.get("created_at") or "", reverse=True)
    return [
        {
            "email": r.get("email") or "",
            "name": r.get("name") or "",
            "organization": r.get("organization") or "",
            "subscribed_at": r.get("subscribed_at") or r.get("created_at") or "",
        }
        for r in rows
    ]


def add_subscriber(email: str, name: str = "", organization: str = "") -> bool:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False
    if not using_supabase():
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
    existing = {s["email"] for s in load_subscribers()}
    if email in existing:
        return False
    payload = {
        "email": email,
        "name": name.strip(),
        "organization": organization.strip(),
    }
    try:
        client().table("subscribers").insert(payload).execute()
    except Exception as exc:
        message = str(exc).lower()
        if "23505" in message or "duplicate" in message or "unique" in message:
            return False
        if "organization" not in message:
            raise
        payload.pop("organization", None)
        try:
            client().table("subscribers").insert(payload).execute()
        except Exception as retry_exc:
            retry_message = str(retry_exc).lower()
            if "23505" in retry_message or "duplicate" in retry_message or "unique" in retry_message:
                return False
            raise
    return True


def remove_subscriber(email: str) -> bool:
    email = email.strip().lower()
    if not using_supabase():
        if not SUBS.exists():
            return False
        rows = [s for s in load_subscribers() if s["email"] != email]
        _ensure_subs_file()
        with SUBS.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_SUBS_HEADER)
            writer.writeheader()
            writer.writerows(rows)
        return True
    client().table("subscribers").delete().eq("email", email).execute()
    return True


def export_subscribers_csv() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_SUBS_HEADER)
    writer.writeheader()
    writer.writerows(load_subscribers())
    return buf.getvalue()
