"""UnlockVault backend tests - iteration 2: security hardening + regressions."""
import os
import io
import re
import uuid
import zipfile
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mass-file-vault.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

LOCKED_PDF = "/tmp/locked.pdf"
PLAIN_PDF = "/tmp/plain.pdf"
PW = "pw123"


@pytest.fixture(scope="module")
def sid():
    s = f"test-{uuid.uuid4().hex[:16]}"
    yield s
    try:
        requests.delete(f"{API}/session/{s}", timeout=30)
    except Exception:
        pass


@pytest.fixture(scope="module")
def ensure_files():
    # Regenerate if missing
    if not os.path.exists(LOCKED_PDF) or not os.path.exists(PLAIN_PDF):
        import pikepdf
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(PLAIN_PDF); c.drawString(100, 750, "secret"); c.save()
        pdf = pikepdf.open(PLAIN_PDF)
        pdf.save(LOCKED_PDF, encryption=pikepdf.Encryption(owner=PW, user=PW))
    assert os.path.exists(LOCKED_PDF) and os.path.exists(PLAIN_PDF)


# ---- Security hardening ----
class TestSecurity:
    def test_invalid_sid_match_passwords(self):
        r = requests.post(f"{API}/match-passwords", json={"session_id": "../../x", "passwords": ["a"]}, timeout=30)
        assert r.status_code == 400
        assert "Invalid session id" in r.text

    def test_invalid_sid_unlock(self):
        r = requests.post(f"{API}/unlock", json={"session_id": "../../x", "file_ids": []}, timeout=30)
        assert r.status_code == 400

    def test_invalid_sid_delete_bulk(self):
        r = requests.post(f"{API}/delete-bulk", json={"session_id": "../bad", "file_ids": []}, timeout=30)
        assert r.status_code == 400

    def test_invalid_sid_merge(self):
        r = requests.post(f"{API}/merge-pdf", json={"session_id": "bad!!", "file_ids": []}, timeout=30)
        assert r.status_code == 400

    def test_invalid_sid_too_short(self):
        r = requests.post(f"{API}/match-passwords", json={"session_id": "abc", "passwords": []}, timeout=30)
        assert r.status_code == 400

    def test_valid_sid_accepted(self, sid):
        r = requests.post(f"{API}/match-passwords", json={"session_id": sid, "passwords": []}, timeout=30)
        assert r.status_code == 200

    def test_upload_rejects_txt(self, sid):
        files = [("files", ("bad.txt", b"hello", "text/plain"))]
        r = requests.post(f"{API}/upload", data={"session_id": sid}, files=files, timeout=30)
        assert r.status_code == 400
        assert "Unsupported" in r.text

    def test_upload_rejects_exe(self, sid):
        files = [("files", ("bad.exe", b"MZ\x00", "application/octet-stream"))]
        r = requests.post(f"{API}/upload", data={"session_id": sid}, files=files, timeout=30)
        assert r.status_code == 400


# ---- Regression: full flow ----
class TestFullFlow:
    uploaded_locked_id = None
    uploaded_plain_id = None

    def test_01_upload_locked_pdf(self, sid, ensure_files):
        with open(LOCKED_PDF, "rb") as f:
            files = [("files", ("locked.pdf", f.read(), "application/pdf"))]
        r = requests.post(f"{API}/upload", data={"session_id": sid}, files=files, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()["files"]
        assert len(data) == 1
        assert data[0]["status"] == "locked"
        assert data[0]["encrypted"] is True
        TestFullFlow.uploaded_locked_id = data[0]["id"]

    def test_02_upload_plain_pdf(self, sid, ensure_files):
        with open(PLAIN_PDF, "rb") as f:
            files = [("files", ("plain.pdf", f.read(), "application/pdf"))]
        r = requests.post(f"{API}/upload", data={"session_id": sid}, files=files, timeout=60)
        assert r.status_code == 200
        d = r.json()["files"][0]
        assert d["status"] == "ready"
        TestFullFlow.uploaded_plain_id = d["id"]

    def test_03_match_passwords(self, sid):
        r = requests.post(f"{API}/match-passwords", json={"session_id": sid, "passwords": ["wrong", PW]}, timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["matched_count"] == 1
        locked = next(f for f in body["files"] if f["id"] == TestFullFlow.uploaded_locked_id)
        assert locked["status"] == "matched"
        assert locked["matched_password"] == PW

    def test_04_unlock(self, sid):
        r = requests.post(f"{API}/unlock", json={"session_id": sid, "file_ids": [TestFullFlow.uploaded_locked_id]}, timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert body["unlocked"] == 1
        unlocked = next(f for f in body["files"] if f["id"] == TestFullFlow.uploaded_locked_id)
        assert unlocked["status"] == "unlocked"
        assert unlocked["encrypted"] is False

    def test_05_download_unlocked_opens_without_password(self, sid):
        r = requests.get(f"{API}/download/{sid}/{TestFullFlow.uploaded_locked_id}", timeout=60)
        assert r.status_code == 200
        cd = r.headers.get("Content-Disposition", "")
        assert "filename=" in cd
        assert "filename*=UTF-8''" in cd
        # Verify PDF opens without password
        import pikepdf
        with pikepdf.open(io.BytesIO(r.content)) as pdf:
            assert len(pdf.pages) >= 1

    def test_06_download_zip(self, sid):
        r = requests.get(f"{API}/download-zip/{sid}", timeout=60)
        assert r.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = zf.namelist()
        assert "locked.pdf" in names
        assert "plain.pdf" in names

    def test_07_merge_too_few(self, sid):
        r = requests.post(f"{API}/merge-pdf", json={"session_id": sid, "file_ids": [TestFullFlow.uploaded_plain_id]}, timeout=30)
        assert r.status_code == 400

    def test_08_merge_ok(self, sid):
        r = requests.post(f"{API}/merge-pdf", json={
            "session_id": sid,
            "file_ids": [TestFullFlow.uploaded_locked_id, TestFullFlow.uploaded_plain_id],
            "output_name": "combined"
        }, timeout=60)
        assert r.status_code == 200
        f = r.json()["file"]
        assert f["original_name"].endswith(".pdf")
        assert f["is_merged"] is True

    def test_09_replace(self, sid):
        with open(PLAIN_PDF, "rb") as f:
            files = [("file", ("replaced.pdf", f.read(), "application/pdf"))]
        r = requests.post(f"{API}/replace", data={"session_id": sid, "file_id": TestFullFlow.uploaded_locked_id}, files=files, timeout=60)
        assert r.status_code == 200
        d = r.json()["file"]
        assert d["original_name"] == "replaced.pdf"
        assert d["encrypted"] is False

    def test_10_replace_rejects_txt(self, sid):
        files = [("file", ("x.txt", b"hi", "text/plain"))]
        r = requests.post(f"{API}/replace", data={"session_id": sid, "file_id": TestFullFlow.uploaded_plain_id}, files=files, timeout=30)
        assert r.status_code == 400

    def test_11_delete_single(self, sid):
        r = requests.delete(f"{API}/file/{sid}/{TestFullFlow.uploaded_plain_id}", timeout=30)
        assert r.status_code == 200
        # Verify gone via list
        r2 = requests.get(f"{API}/files/{sid}", timeout=30)
        ids = [f["id"] for f in r2.json()["files"]]
        assert TestFullFlow.uploaded_plain_id not in ids

    def test_12_delete_bulk(self, sid):
        # Upload two more then bulk delete
        with open(PLAIN_PDF, "rb") as f:
            data = f.read()
        files = [("files", ("a.pdf", data, "application/pdf")), ("files", ("b.pdf", data, "application/pdf"))]
        r = requests.post(f"{API}/upload", data={"session_id": sid}, files=files, timeout=60)
        ids = [f["id"] for f in r.json()["files"]]
        r2 = requests.post(f"{API}/delete-bulk", json={"session_id": sid, "file_ids": ids}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["deleted"] == 2


# ---- Hardening extras ----
class TestExtras:
    def test_unlock_generic_error(self, sid):
        # Create a session, upload locked, don't match -> unlock on non-matched is skipped (unlocked=0, errors=[])
        s = f"gen-{uuid.uuid4().hex[:12]}"
        r = requests.post(f"{API}/unlock", json={"session_id": s, "file_ids": ["nonexistent"]}, timeout=30)
        assert r.status_code == 200
        # No raw tracebacks
        assert "Traceback" not in r.text

    def test_too_many_files(self):
        # Simulate 101 tiny pdfs - the server should reject
        s = f"many-{uuid.uuid4().hex[:12]}"
        with open(PLAIN_PDF, "rb") as f:
            data = f.read()
        files = [("files", (f"x{i}.pdf", data, "application/pdf")) for i in range(101)]
        r = requests.post(f"{API}/upload", data={"session_id": s}, files=files, timeout=120)
        assert r.status_code == 400
        assert "Too many" in r.text or "max" in r.text.lower()
        try:
            requests.delete(f"{API}/session/{s}", timeout=30)
        except Exception:
            pass
