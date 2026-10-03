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



# ---- Iteration 3: Concurrency correctness ----
class TestConcurrency:
    """Each file must get its own correct password; no cross-contamination."""

    @pytest.fixture(scope="class")
    def multi_locked(self):
        import pikepdf
        from reportlab.pdfgen import canvas
        if not os.path.exists(PLAIN_PDF):
            c = canvas.Canvas(PLAIN_PDF); c.drawString(100, 750, "secret"); c.save()
        paths = []
        passwords = []
        for i in range(6):
            pw = f"secret{i}"
            p = f"/tmp/locked_{i}.pdf"
            with pikepdf.open(PLAIN_PDF) as pdf:
                pdf.save(p, encryption=pikepdf.Encryption(owner=pw, user=pw))
            paths.append(p)
            passwords.append(pw)
        return paths, passwords

    @pytest.fixture(scope="class")
    def csid(self):
        s = f"conc-{uuid.uuid4().hex[:16]}"
        yield s
        try:
            requests.delete(f"{API}/session/{s}", timeout=30)
        except Exception:
            pass

    def test_concurrent_match_each_file_own_password(self, csid, multi_locked):
        paths, passwords = multi_locked
        # Upload all locked files
        upload_files = []
        for i, p in enumerate(paths):
            with open(p, "rb") as f:
                upload_files.append(("files", (f"locked_{i}.pdf", f.read(), "application/pdf")))
        # Also upload one that will NOT match
        with open(paths[0], "rb") as f:
            upload_files.append(("files", ("locked_nomatch.pdf", f.read(), "application/pdf")))
        # Re-encrypt the nomatch with a unique password
        import pikepdf
        nomatch_path = "/tmp/locked_nomatch.pdf"
        with pikepdf.open(PLAIN_PDF) as pdf:
            pdf.save(nomatch_path, encryption=pikepdf.Encryption(owner="zzz_unique_999", user="zzz_unique_999"))
        with open(nomatch_path, "rb") as f:
            upload_files[-1] = ("files", ("locked_nomatch.pdf", f.read(), "application/pdf"))

        r = requests.post(f"{API}/upload", data={"session_id": csid}, files=upload_files, timeout=120)
        assert r.status_code == 200, r.text
        uploaded = r.json()["files"]
        assert len(uploaded) == 7
        # Map filename -> id
        name_to_id = {f["original_name"]: f["id"] for f in uploaded}

        # Shuffle passwords + decoys
        import time
        pw_list = ["decoy1", "x", "wrong"] + passwords + ["decoy2", "nope"]
        t0 = time.time()
        r = requests.post(f"{API}/match-passwords", json={"session_id": csid, "passwords": pw_list}, timeout=120)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        body = r.json()
        print(f"match elapsed={elapsed:.2f}s matched_count={body['matched_count']}")
        assert body["matched_count"] == 6, body

        # Verify EACH locked_i.pdf got secret{i} and no cross-contamination
        for i, pw in enumerate(passwords):
            fid = name_to_id[f"locked_{i}.pdf"]
            file_entry = next(f for f in body["files"] if f["id"] == fid)
            assert file_entry["status"] == "matched", file_entry
            assert file_entry["matched_password"] == pw, (
                f"File locked_{i}.pdf expected password {pw!r} got {file_entry.get('matched_password')!r}"
            )

        # Non-matching file stays locked
        nm_id = name_to_id["locked_nomatch.pdf"]
        nm = next(f for f in body["files"] if f["id"] == nm_id)
        assert nm["status"] == "locked"
        assert not nm.get("matched_password")

    def test_concurrent_unlock_all_matched(self, csid):
        # List current files
        r = requests.get(f"{API}/files/{csid}", timeout=30)
        assert r.status_code == 200
        files = r.json()["files"]
        matched_ids = [f["id"] for f in files if f["status"] == "matched"]
        all_ids = [f["id"] for f in files]
        assert len(matched_ids) == 6

        r = requests.post(f"{API}/unlock", json={"session_id": csid, "file_ids": all_ids}, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["unlocked"] == 6, body

        # Every previously-matched file is now unlocked and encrypted=False
        for f in body["files"]:
            if f["id"] in matched_ids:
                assert f["status"] == "unlocked", f
                assert f["encrypted"] is False, f

        # Download each and verify opens without password
        import pikepdf
        for fid in matched_ids:
            dr = requests.get(f"{API}/download/{csid}/{fid}", timeout=60)
            assert dr.status_code == 200
            with pikepdf.open(io.BytesIO(dr.content)) as pdf:
                assert len(pdf.pages) >= 1
