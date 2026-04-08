import csv
import io
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import cloudinary
import cloudinary.uploader

from . import config, storage, renderer, senders
from .senders.base import Recipient

app = FastAPI(title="전인교육학회 뉴스레터 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return senders.AVAILABLE


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


@app.post("/api/send")
def post_send(req: SendRequest):
    html = renderer.render(req.template, req.data)
    sender = senders.get_sender(req.sender)
    rcpts = [Recipient(email=r["email"], name=r.get("name")) for r in req.recipients]
    res = sender.send(html, req.subject, rcpts, req.from_addr, req.from_name)
    return {"sent": res.sent, "failed": res.failed, "errors": res.errors[:20]}


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
