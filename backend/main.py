import csv
import base64
import io
import secrets
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel
import cloudinary
import cloudinary.uploader

from . import config, storage, renderer, senders, jobs
from .senders.base import Recipient

app = FastAPI(title="전인교육학회 뉴스레터 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/api/subscribe", "/api/unsubscribe", "/health"}


def _is_public_path(path: str) -> bool:
    normalized = path.rstrip("/") or "/"
    return normalized in PUBLIC_PATHS


def _authorized(auth_header: str | None) -> bool:
    if not config.ADMIN_PASSWORD:
        return True
    if not auth_header or not auth_header.startswith("Basic "):
        return False
    try:
        raw = base64.b64decode(auth_header.removeprefix("Basic ").strip()).decode("utf-8")
        username, password = raw.split(":", 1)
    except Exception:
        return False
    return (
        secrets.compare_digest(username.encode("utf-8"), config.ADMIN_USERNAME.encode("utf-8"))
        and secrets.compare_digest(password.encode("utf-8"), config.ADMIN_PASSWORD.encode("utf-8"))
    )


@app.middleware("http")
async def require_admin_auth(request: Request, call_next):
    if config.ADMIN_PASSWORD and not _is_public_path(request.url.path):
        if not _authorized(request.headers.get("authorization")):
            return PlainTextResponse(
                "Authentication required",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Newsletter Admin"'},
            )
    return await call_next(request)

if config.CLOUDINARY_CLOUD_NAME:
    cloudinary.config(
        cloud_name=config.CLOUDINARY_CLOUD_NAME,
        api_key=config.CLOUDINARY_API_KEY,
        api_secret=config.CLOUDINARY_API_SECRET,
        secure=True,
    )


class RenderRequest(BaseModel):
    template: str = "classic"
    data: dict


class DraftIn(BaseModel):
    id: str | None = None
    name: str
    template: str
    subject: str
    data: dict


class SendRequest(BaseModel):
    sender: str
    template: str
    subject: str
    from_addr: str
    from_name: str = "전인교육학회"
    recipients: list[dict]  # [{email, name?}]
    data: dict


@app.get("/api/templates")
def get_templates():
    return [{"key": k, **v} for k, v in renderer.AVAILABLE_TEMPLATES.items()]


@app.get("/api/senders")
def get_senders():
    return senders.get_available()


@app.post("/api/render", response_class=HTMLResponse)
def post_render(req: RenderRequest):
    try:
        return renderer.render(req.template, req.data)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/export")
def export_html(req: RenderRequest):
    html = renderer.render(req.template, req.data)
    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": 'attachment; filename="newsletter.html"'},
    )


@app.get("/api/drafts")
def get_drafts():
    return storage.list_drafts()


@app.get("/api/drafts/{draft_id}")
def get_draft(draft_id: str):
    d = storage.get_draft(draft_id)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.post("/api/drafts")
def post_draft(d: DraftIn):
    return storage.save_draft(d.model_dump())


@app.delete("/api/drafts/{draft_id}")
def delete_draft(draft_id: str):
    return {"ok": storage.delete_draft(draft_id)}


class RenameIn(BaseModel):
    name: str


@app.patch("/api/drafts/{draft_id}")
def rename_draft(draft_id: str, body: RenameIn):
    d = storage.rename_draft(draft_id, body.name)
    if not d:
        raise HTTPException(404, "Not found")
    return d


@app.get("/api/default-draft")
def get_default_draft():
    return {"id": storage.get_default_draft_id()}


class DefaultDraftIn(BaseModel):
    id: str | None = None


@app.put("/api/default-draft")
def put_default_draft(body: DefaultDraftIn):
    ok = storage.set_default_draft_id(body.id)
    if not ok:
        raise HTTPException(404, "Draft not found")
    return {"ok": True, "id": body.id}


@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    if not config.CLOUDINARY_CLOUD_NAME:
        raise HTTPException(500, "Cloudinary 환경변수가 설정되지 않았습니다 (.env 확인)")
    content = await file.read()
    res = cloudinary.uploader.upload(content, folder="newsletter")
    return {"url": res["secure_url"], "public_id": res["public_id"]}


@app.post("/api/parse-recipients")
async def parse_recipients(file: UploadFile = File(...)):
    """CSV/XLSX 파싱: 'email' 단일 컬럼 또는 'email,name' 모두 지원."""
    filename = (file.filename or "").lower()
    content = await file.read()

    # Excel (.xlsx) 처리
    if filename.endswith(".xlsx") or filename.endswith(".xlsm"):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return {"recipients": [], "count": 0}
            # 첫 행을 헤더로 시도
            header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
            out = []
            if "email" in header:
                email_i = header.index("email")
                name_i = header.index("name") if "name" in header else None
                for row in rows[1:]:
                    if not row or email_i >= len(row):
                        continue
                    email = (str(row[email_i]).strip() if row[email_i] else "")
                    if not email or "@" not in email:
                        continue
                    name = None
                    if name_i is not None and name_i < len(row) and row[name_i]:
                        name = str(row[name_i]).strip()
                    out.append({"email": email, "name": name})
            else:
                # 헤더 없이 첫 컬럼을 이메일로 취급
                for row in rows:
                    if not row:
                        continue
                    cell = row[0]
                    if cell and "@" in str(cell):
                        out.append({"email": str(cell).strip()})
            return {"recipients": out, "count": len(out)}
        except Exception as e:
            raise HTTPException(400, f"Excel 파싱 실패: {e}")

    # CSV 처리
    try:
        raw = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            raw = content.decode("cp949")  # 한국어 엑셀에서 자주 보임
        except UnicodeDecodeError:
            raw = content.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(raw))
    fields = [f.strip().lower() for f in (reader.fieldnames or [])]
    if "email" not in fields:
        out = []
        for line in raw.splitlines():
            line = line.strip()
            if line and "@" in line:
                out.append({"email": line})
        return {"recipients": out, "count": len(out)}
    out = []
    for row in reader:
        norm = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
        if norm.get("email"):
            out.append({"email": norm["email"], "name": norm.get("name") or None})
    return {"recipients": out, "count": len(out)}


def _filter_send_recipients(recipients: list[dict]) -> tuple[list[Recipient], int]:
    unsub = storage.load_unsubscribed()
    seen: set[str] = set()
    out: list[Recipient] = []
    skipped = 0
    for raw in recipients:
        email = (raw.get("email") or "").strip().lower()
        if not email or "@" not in email:
            continue
        if email in seen:
            continue
        seen.add(email)
        if email in unsub:
            skipped += 1
            continue
        out.append(Recipient(email=email, name=raw.get("name")))
    return out, skipped


def _split_batch_result(batch: list[dict], errors: list[str], failed_count: int) -> tuple[list[str], list[dict]]:
    by_email = {row["email"].strip().lower(): row for row in batch}
    failed_by_id: dict[str, dict] = {}
    for err in errors:
        prefix = err.split(":", 1)[0].strip().lower() if ":" in err else ""
        row = by_email.get(prefix)
        if row:
            failed_by_id[row["id"]] = {**row, "error": err}

    if failed_count and not failed_by_id:
        message = errors[0] if errors else "발송 실패"
        for row in batch[:failed_count]:
            failed_by_id[row["id"]] = {**row, "error": message}
    elif len(failed_by_id) < failed_count:
        message = errors[0] if errors else "발송 실패"
        remaining = [row for row in batch if row["id"] not in failed_by_id]
        for row in remaining[: failed_count - len(failed_by_id)]:
            failed_by_id[row["id"]] = {**row, "error": message}

    failed_ids = set(failed_by_id)
    sent_ids = [row["id"] for row in batch if row["id"] not in failed_ids]
    return sent_ids, list(failed_by_id.values())


@app.post("/api/send")
def post_send(req: SendRequest):
    renderer.render(req.template, req.data)
    rcpts, skipped = _filter_send_recipients(req.recipients)

    if not rcpts:
        return {"job_id": None, "sent": 0, "failed": 0, "skipped": skipped, "message": "발송할 수신자가 없습니다 (모두 수신거부됨)"}

    job = jobs.create_job(req.model_dump(), rcpts, skipped=skipped, batch_size=config.SEND_BATCH_SIZE)
    return {"job_id": job["id"], "total": job["total"], "skipped": job["skipped"]}


@app.post("/api/send/{job_id}/process")
def process_send_job(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in {"done", "failed"}:
        return job

    batch = jobs.get_pending_recipients(job_id, config.SEND_BATCH_SIZE)
    if not batch:
        done = jobs.finish_if_complete(job_id)
        if not done:
            raise HTTPException(404, "Job not found")
        return done

    jobs.set_running(job_id)
    try:
        html = renderer.render(job["template"], job["data"])
        sender = senders.get_sender(job["sender"])
        recipients = [Recipient(email=row["email"], name=row.get("name")) for row in batch]
        result = sender.send(html, job["subject"], recipients, job["from_addr"], job["from_name"])
        sent_ids, failed_rows = _split_batch_result(batch, result.errors, result.failed)
        return jobs.mark_batch_result(job_id, sent_ids, failed_rows)
    except Exception as e:
        failed = jobs.fail_job(job_id, f"발송 실패: {e}", [str(e)])
        if not failed:
            raise HTTPException(404, "Job not found")
        return failed


@app.get("/api/send/{job_id}")
def get_send_status(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs")
def get_jobs():
    return jobs.list_jobs()


# ========== 수신거부 ==========

class UnsubIn(BaseModel):
    email: str


@app.get("/api/unsubscribe", response_class=HTMLResponse)
def unsubscribe_landing(email: str = ""):
    """이메일에서 수신거부 링크 클릭 시 진입하는 확인 페이지"""
    import html as _html
    _email = _html.escape(email.strip())
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>전인교육학회 수신거부</title>
<style>{_SUBSCRIBE_PAGE_CSS}</style></head><body>
  <div class="card">
    <div class="card-top">
      <h1>전인교육학회</h1>
      <p>소식 수신을 원하지 않으시면 이메일 주소를 확인해 주세요.</p>
    </div>
    <div class="card-body">
      <form method="POST" action="/api/unsubscribe">
        <label>이메일 <span class="req">*</span></label>
        <input type="email" name="email" required placeholder="example@email.com" value="{_email}">
        <button type="submit" class="btn">수신거부</button>
      </form>
    </div>
    <div class="footer">전인교육학회 Academic Society for Human Completion</div>
  </div>
</body></html>""")


@app.post("/api/unsubscribe", response_class=HTMLResponse)
def unsubscribe_submit(email: str = Form(...)):
    """수신거부 확인 버튼 제출 처리"""
    import html as _html
    email = email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "유효하지 않은 이메일입니다.")
    storage.add_unsubscribed(email)
    _email = _html.escape(email)
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>전인교육학회 수신거부 완료</title>
<style>{_SUBSCRIBE_PAGE_CSS}</style></head><body>
  <div class="card">
    <div class="card-top">
      <h1>전인교육학회</h1>
      <p>수신거부 처리가 완료되었습니다.</p>
    </div>
    <div class="card-body result">
      <div class="icon">✓</div>
      <h2>수신거부 완료</h2>
      <p>아래 이메일 주소는 더 이상 전인교육학회 소식을 수신하지 않습니다.</p>
      <div class="email">{_email}</div>
    </div>
    <div class="footer">잘못 클릭하셨다면 사무국으로 연락 주세요.<br>info@humancompletion.org</div>
  </div>
</body></html>""")


@app.get("/api/unsubscribed")
def list_unsubscribed():
    return {"emails": sorted(storage.load_unsubscribed())}


@app.post("/api/unsubscribed")
def post_unsubscribe(body: UnsubIn):
    added = storage.add_unsubscribed(body.email)
    return {"ok": True, "added": added}


@app.delete("/api/unsubscribed/{email}")
def delete_unsubscribed(email: str):
    storage.remove_unsubscribed(email)
    return {"ok": True}


# ========== 수신동의(구독) ==========

_SUBSCRIBE_PAGE_CSS = """
  * { box-sizing: border-box; }
  body { font-family: 'Apple SD Gothic Neo','Malgun Gothic',sans-serif; background:#f5f5f5; margin:0; padding:0; display:flex; align-items:center; justify-content:center; min-height:100vh; }
  .card { background:#fff; border-radius:14px; box-shadow:0 12px 32px rgba(15,23,42,0.08); max-width:460px; width:100%; margin:20px; overflow:hidden; }
  .card-top { background:#1a6b4a; padding:28px 36px; color:#fff; }
  .card-top h1 { margin:0; font-size:20px; font-weight:800; letter-spacing:-0.3px; }
  .card-top p { margin:6px 0 0; font-size:13px; opacity:0.85; }
  .card-body { padding:32px 36px; }
  label { display:block; font-size:13px; font-weight:600; color:#334155; margin-bottom:6px; }
  label .req { color:#e53e3e; }
  input[type=text], input[type=email] { width:100%; padding:10px 14px; border:1px solid #e2e8f0; border-radius:8px; font-size:14px; margin-bottom:16px; outline:none; transition:border .2s; }
  input:focus { border-color:#1a6b4a; box-shadow:0 0 0 3px rgba(26,107,74,0.1); }
  .consent { display:flex; gap:10px; align-items:flex-start; margin:18px 0 24px; padding:14px 16px; background:#f8faf9; border-radius:8px; border:1px solid #e8efe9; }
  .consent input[type=checkbox] { margin-top:3px; accent-color:#1a6b4a; flex-shrink:0; }
  .consent span { font-size:12px; color:#475569; line-height:1.65; }
  .btn { width:100%; padding:13px; background:#1a6b4a; color:#fff; border:none; border-radius:8px; font-size:15px; font-weight:700; cursor:pointer; transition:background .2s; }
  .btn:hover { background:#15573d; }
  .btn.danger { background:#9f3131; }
  .btn.danger:hover { background:#842727; }
  .result { text-align:center; }
  .result h2 { font-size:20px; color:#0f172a; margin:0 0 8px; letter-spacing:-0.3px; }
  .result p { color:#475569; font-size:14px; line-height:1.7; margin:0 0 18px; }
  .icon { width:64px; height:64px; border-radius:50%; background:#ecf5f0; color:#1a6b4a; display:inline-flex; align-items:center; justify-content:center; font-size:32px; margin-bottom:18px; }
  .email { display:inline-block; background:#f7f8fa; border:1px solid #e8eaed; padding:6px 14px; border-radius:8px; font-size:13px; color:#1a6b4a; font-weight:600; }
  .footer { text-align:center; padding:0 36px 28px; font-size:11px; color:#94a3b8; line-height:1.6; }
"""

_SUBSCRIBE_SUCCESS_CSS = """
  body { font-family: 'Apple SD Gothic Neo','Malgun Gothic',sans-serif; background:#f5f5f5; margin:0; padding:0; display:flex; align-items:center; justify-content:center; min-height:100vh; }
  .card { background:#fff; border-radius:14px; box-shadow:0 12px 32px rgba(15,23,42,0.08); padding:48px 56px; max-width:440px; text-align:center; }
  .icon { width:64px; height:64px; border-radius:50%; background:#ecf5f0; color:#1a6b4a; display:inline-flex; align-items:center; justify-content:center; font-size:32px; margin-bottom:18px; }
  h1 { font-size:20px; color:#0f172a; margin:0 0 8px; letter-spacing:-0.3px; }
  p { color:#475569; font-size:14px; line-height:1.7; margin:0 0 18px; }
  .email { display:inline-block; background:#f7f8fa; border:1px solid #e8eaed; padding:6px 14px; border-radius:8px; font-size:13px; color:#1a6b4a; font-weight:600; }
  .footer { margin-top:24px; font-size:12px; color:#94a3b8; }
"""


@app.get("/api/subscribe", response_class=HTMLResponse)
def subscribe_form(email: str = "", name: str = ""):
    """수신동의 폼 페이지"""
    import html as _html
    _email = _html.escape(email.strip())
    _name = _html.escape(name.strip())
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>전인교육학회 수신동의</title>
<style>{_SUBSCRIBE_PAGE_CSS}</style></head><body>
  <div class="card">
    <div class="card-top">
      <h1>전인교육학회</h1>
      <p>학회지, 학술대회, 캠프 등 소식을 이메일로 받아보세요.</p>
    </div>
    <div class="card-body">
      <form method="POST" action="/api/subscribe">
        <label>이름 <span class="req">*</span></label>
        <input type="text" name="name" required placeholder="홍길동" value="{_name}">
        <label>이메일 <span class="req">*</span></label>
        <input type="email" name="email" required placeholder="example@email.com" value="{_email}">
        <label>소속</label>
        <input type="text" name="organization" placeholder="대학교/기관명 (선택)">
        <div class="consent">
          <input type="checkbox" id="agree" name="agree" required>
          <span>
            <strong>개인정보 수집 및 이용 동의</strong><br>
            전인교육학회는 뉴스레터 발송을 위해 이름, 이메일, 소속 정보를 수집합니다.
            수집된 정보는 뉴스레터 발송 목적으로만 사용되며, 수신거부 시 즉시 파기합니다.
          </span>
        </div>
        <button type="submit" class="btn">수신동의</button>
      </form>
    </div>
    <div class="footer">전인교육학회 Academic Society for Human Completion</div>
  </div>
</body></html>""")


@app.post("/api/subscribe", response_class=HTMLResponse)
def subscribe_submit(
    email: str = Form(...),
    name: str = Form(""),
    organization: str = Form(""),
    agree: str = Form(""),
):
    """수신동의 폼 제출 처리"""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(400, "유효하지 않은 이메일입니다.")
    added = storage.add_subscriber(email, name, organization)
    if added:
        msg_title = "수신동의가 완료되었습니다"
        msg_body = "앞으로 전인교육학회 뉴스레터를<br>이메일로 받아보실 수 있습니다."
    else:
        msg_title = "이미 등록된 이메일입니다"
        msg_body = "해당 이메일은 이미 수신동의 되어 있습니다.<br>추가 조치가 필요하지 않습니다."
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>수신동의 완료</title>
<style>{_SUBSCRIBE_SUCCESS_CSS}</style></head><body>
  <div class="card">
    <div class="icon">✓</div>
    <h1>{msg_title}</h1>
    <p>{msg_body}</p>
    <div class="email">{email}</div>
    <div class="footer">전인교육학회 Academic Society for Human Completion</div>
  </div>
</body></html>""")


@app.get("/api/subscribers")
def list_subscribers():
    subs = storage.load_subscribers()
    return {"subscribers": subs, "count": len(subs)}


@app.delete("/api/subscribers/{email:path}")
def delete_subscriber(email: str):
    storage.remove_subscriber(email)
    return {"ok": True}


@app.get("/api/subscribers/export")
def export_subscribers():
    csv_str = storage.export_subscribers_csv()
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="subscribers.csv"'},
    )


@app.get("/api/manual")
def get_manual():
    import os
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "MANUAL.md"),
        "/app/MANUAL.md",
        "MANUAL.md",
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return {"content": f.read()}
    return {"content": "# 매뉴얼 파일을 찾을 수 없습니다."}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")

    dist = Path(config.FRONTEND_DIST_DIR)
    index = dist / "index.html"
    if not index.exists():
        raise HTTPException(404, "Frontend build not found")

    target = (dist / full_path).resolve()
    try:
        target.relative_to(dist.resolve())
    except ValueError:
        raise HTTPException(404, "Not found")

    if full_path and target.is_file():
        return FileResponse(target)
    return FileResponse(index)
