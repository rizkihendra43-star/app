from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import re
import zipfile
import logging
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import requests
import pikepdf
import msoffcrypto
from pypdf import PdfWriter, PdfReader

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ---------- Object storage ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "mass-unlocker"
storage_key = None


def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> bytes:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content

app = FastAPI()
api_router = APIRouter(prefix="/api")

PDF_EXT = {'.pdf'}
EXCEL_EXT = {'.xlsx', '.xls', '.xlsm', '.xlsb'}
ALLOWED_EXT = PDF_EXT | EXCEL_EXT

SID_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB per file
MAX_FILES = 100


def check_sid(sid: str):
    if not sid or not SID_RE.match(sid):
        raise HTTPException(status_code=400, detail="Invalid session id")


def safe_filename(name: str) -> str:
    name = os.path.basename(name or "file")
    name = name.replace('"', '').replace('\r', '').replace('\n', '').strip()
    return name or "file"


async def read_capped(up: UploadFile) -> bytes:
    data = b''
    while True:
        chunk = await up.read(1024 * 1024)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 50MB limit")
    return data


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def file_type_for(ext: str) -> str:
    if ext in PDF_EXT:
        return 'pdf'
    if ext in EXCEL_EXT:
        return 'excel'
    return 'other'


def temp_from_bytes(data: bytes, ext: str) -> str:
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    tf.write(data)
    tf.close()
    return tf.name


# ---------- Encryption detection / password ops (operate on local temp paths) ----------
def is_pdf_encrypted(path: str) -> bool:
    try:
        with pikepdf.open(path):
            return False
    except pikepdf.PasswordError:
        return True
    except Exception:
        return False


def is_excel_encrypted(path: str) -> bool:
    try:
        with open(path, 'rb') as f:
            return msoffcrypto.OfficeFile(f).is_encrypted()
    except Exception:
        return False


def detect_encrypted(path: str, ftype: str) -> bool:
    if ftype == 'pdf':
        return is_pdf_encrypted(path)
    if ftype == 'excel':
        return is_excel_encrypted(path)
    return False


def try_password(path: str, ftype: str, pw: str) -> bool:
    try:
        if ftype == 'pdf':
            with pikepdf.open(path, password=pw):
                return True
        if ftype == 'excel':
            with open(path, 'rb') as f:
                office = msoffcrypto.OfficeFile(f)
                office.load_key(password=pw)
                office.decrypt(io.BytesIO())
            return True
    except Exception:
        return False
    return False


def unlock_to_bytes(path: str, ftype: str, pw: str) -> bytes:
    if ftype == 'pdf':
        out = io.BytesIO()
        with pikepdf.open(path, password=pw) as pdf:
            pdf.save(out)
        return out.getvalue()
    if ftype == 'excel':
        out = io.BytesIO()
        with open(path, 'rb') as f:
            office = msoffcrypto.OfficeFile(f)
            office.load_key(password=pw)
            office.decrypt(out)
        return out.getvalue()
    return b""


# ---------- Models ----------
class FileDoc(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    original_name: str
    storage_path: str = ""
    ext: str
    file_type: str
    encrypted: bool = False
    status: str = "ready"
    matched_password: Optional[str] = None
    size: int = 0
    is_merged: bool = False
    created_at: str = Field(default_factory=now_iso)


def public_file(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "session_id": doc["session_id"],
        "original_name": doc["original_name"],
        "ext": doc["ext"],
        "file_type": doc["file_type"],
        "encrypted": doc["encrypted"],
        "status": doc["status"],
        "matched_password": doc.get("matched_password"),
        "size": doc.get("size", 0),
        "is_merged": doc.get("is_merged", False),
        "created_at": doc["created_at"],
    }


class MatchRequest(BaseModel):
    session_id: str
    passwords: List[str]


class UnlockRequest(BaseModel):
    session_id: str
    file_ids: List[str]


class MergeRequest(BaseModel):
    session_id: str
    file_ids: List[str]
    output_name: str = "merged.pdf"


# ---------- Routes ----------
@api_router.get("/")
async def root():
    return {"message": "Mass File Unlocker API"}


@api_router.post("/upload")
async def upload_files(session_id: str = Form(...), files: List[UploadFile] = File(...)):
    check_sid(session_id)
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files (max {MAX_FILES} per upload)")
    results = []
    for up in files:
        ext = Path(up.filename).suffix.lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")
        ftype = file_type_for(ext)
        content = await read_capped(up)
        tmp = temp_from_bytes(content, ext)
        try:
            encrypted = detect_encrypted(tmp, ftype)
        finally:
            os.unlink(tmp)
        fdoc = FileDoc(session_id=session_id, original_name=up.filename, ext=ext, file_type=ftype)
        storage_path = f"{APP_NAME}/{session_id}/{fdoc.id}{ext}"
        result = put_object(storage_path, content)
        fdoc.storage_path = result["path"]
        fdoc.size = len(content)
        fdoc.encrypted = encrypted
        fdoc.status = "locked" if encrypted else "ready"
        doc = fdoc.model_dump()
        await db.files.insert_one(doc)
        results.append(public_file(doc))
    return {"files": results}


@api_router.get("/files/{session_id}")
async def list_files(session_id: str):
    check_sid(session_id)
    docs = await db.files.find({"session_id": session_id}).sort("created_at", 1).to_list(1000)
    return {"files": [public_file(d) for d in docs]}


@api_router.post("/match-passwords")
async def match_passwords(req: MatchRequest):
    check_sid(req.session_id)
    pws = [p.strip() for p in req.passwords if p.strip()]
    docs = await db.files.find({"session_id": req.session_id}).to_list(1000)
    matched_count = 0
    for d in docs:
        if not d.get("encrypted") or d.get("status") == "unlocked":
            continue
        data = get_object(d["storage_path"])
        tmp = temp_from_bytes(data, d["ext"])
        try:
            found = None
            for pw in pws:
                if try_password(tmp, d["file_type"], pw):
                    found = pw
                    break
        finally:
            os.unlink(tmp)
        if found is not None:
            matched_count += 1
            await db.files.update_one({"id": d["id"]}, {"$set": {"status": "matched", "matched_password": found}})
        else:
            await db.files.update_one({"id": d["id"]}, {"$set": {"status": "locked", "matched_password": None}})
    docs = await db.files.find({"session_id": req.session_id}).sort("created_at", 1).to_list(1000)
    return {"matched_count": matched_count, "files": [public_file(d) for d in docs]}


@api_router.post("/unlock")
async def unlock(req: UnlockRequest):
    check_sid(req.session_id)
    unlocked = 0
    errors = []
    for fid in req.file_ids:
        d = await db.files.find_one({"id": fid, "session_id": req.session_id})
        if not d or d.get("status") != "matched" or not d.get("matched_password"):
            continue
        data = get_object(d["storage_path"])
        tmp = temp_from_bytes(data, d["ext"])
        try:
            out = unlock_to_bytes(tmp, d["file_type"], d["matched_password"])
            put_object(d["storage_path"], out)
            await db.files.update_one({"id": fid}, {"$set": {"status": "unlocked", "encrypted": False, "size": len(out)}})
            unlocked += 1
        except Exception as e:
            logging.exception("unlock failed")
            errors.append({"id": fid, "error": "Failed to unlock file"})
            await db.files.update_one({"id": fid}, {"$set": {"status": "error"}})
        finally:
            os.unlink(tmp)
    docs = await db.files.find({"session_id": req.session_id}).sort("created_at", 1).to_list(1000)
    return {"unlocked": unlocked, "errors": errors, "files": [public_file(d) for d in docs]}


@api_router.delete("/file/{session_id}/{file_id}")
async def delete_file(session_id: str, file_id: str):
    check_sid(session_id)
    d = await db.files.find_one({"id": file_id, "session_id": session_id})
    if not d:
        raise HTTPException(status_code=404, detail="File not found")
    await db.files.delete_one({"id": file_id})
    return {"deleted": True, "id": file_id}


@api_router.post("/delete-bulk")
async def delete_bulk(req: UnlockRequest):
    check_sid(req.session_id)
    res = await db.files.delete_many({"session_id": req.session_id, "id": {"$in": req.file_ids}})
    return {"deleted": res.deleted_count}


@api_router.post("/replace")
async def replace_file(session_id: str = Form(...), file_id: str = Form(...), file: UploadFile = File(...)):
    check_sid(session_id)
    d = await db.files.find_one({"id": file_id, "session_id": session_id})
    if not d:
        raise HTTPException(status_code=404, detail="File not found")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")
    ftype = file_type_for(ext)
    content = await read_capped(file)
    tmp = temp_from_bytes(content, ext)
    try:
        encrypted = detect_encrypted(tmp, ftype)
    finally:
        os.unlink(tmp)
    storage_path = f"{APP_NAME}/{session_id}/{file_id}{ext}"
    result = put_object(storage_path, content)
    await db.files.update_one({"id": file_id}, {"$set": {
        "original_name": file.filename,
        "storage_path": result["path"],
        "ext": ext,
        "file_type": ftype,
        "size": len(content),
        "encrypted": encrypted,
        "status": "locked" if encrypted else "ready",
        "matched_password": None,
    }})
    d = await db.files.find_one({"id": file_id})
    return {"file": public_file(d)}


@api_router.post("/merge-pdf")
async def merge_pdf(req: MergeRequest):
    check_sid(req.session_id)
    docs = []
    for fid in req.file_ids:
        d = await db.files.find_one({"id": fid, "session_id": req.session_id})
        if not d:
            continue
        if d["file_type"] != "pdf":
            raise HTTPException(status_code=400, detail=f"{d['original_name']} is not a PDF")
        if d.get("encrypted") and d.get("status") != "unlocked":
            raise HTTPException(status_code=400, detail=f"{d['original_name']} is still locked. Unlock it first.")
        docs.append(d)
    if len(docs) < 2:
        raise HTTPException(status_code=400, detail="Select at least 2 PDF files to merge")
    writer = PdfWriter()
    for d in docs:
        data = get_object(d["storage_path"])
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out_bytes = out.getvalue()
    out_name = req.output_name if req.output_name.lower().endswith('.pdf') else req.output_name + '.pdf'
    fdoc = FileDoc(
        session_id=req.session_id, original_name=out_name, ext='.pdf', file_type='pdf',
        encrypted=False, status='unlocked', is_merged=True, size=len(out_bytes),
    )
    storage_path = f"{APP_NAME}/{req.session_id}/{fdoc.id}.pdf"
    result = put_object(storage_path, out_bytes, "application/pdf")
    fdoc.storage_path = result["path"]
    doc = fdoc.model_dump()
    await db.files.insert_one(doc)
    return {"file": public_file(doc)}


@api_router.get("/download/{session_id}/{file_id}")
async def download_file(session_id: str, file_id: str):
    check_sid(session_id)
    d = await db.files.find_one({"id": file_id, "session_id": session_id})
    if not d:
        raise HTTPException(status_code=404, detail="File not found")
    data = get_object(d["storage_path"])
    fn = safe_filename(d["original_name"])
    headers = {"Content-Disposition": f"attachment; filename=\"{fn}\"; filename*=UTF-8''{quote(fn)}"}
    return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream", headers=headers)


@api_router.get("/download-zip/{session_id}")
async def download_zip(session_id: str, only: str = "unlocked"):
    check_sid(session_id)
    docs = await db.files.find({"session_id": session_id}).sort("created_at", 1).to_list(1000)
    if only == "unlocked":
        docs = [d for d in docs if d.get("status") in ("unlocked", "ready")]
    if not docs:
        raise HTTPException(status_code=404, detail="No files available to download")
    buf = io.BytesIO()
    used = {}
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for d in docs:
            data = get_object(d["storage_path"])
            base = d["original_name"]
            name = base
            if base in used:
                used[base] += 1
                name = f"{Path(base).stem} ({used[base]}){Path(base).suffix}"
            else:
                used[base] = 0
            zf.writestr(name, data)
    buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="unlocked_files.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@api_router.delete("/session/{session_id}")
async def clear_session(session_id: str):
    check_sid(session_id)
    await db.files.delete_many({"session_id": session_id})
    return {"cleared": True}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
