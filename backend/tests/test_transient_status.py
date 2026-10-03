"""Iteration 4: transient scanning/unlocking status observability tests."""
import os
import io
import uuid
import time
import threading
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mass-file-vault.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PLAIN_PDF = "/tmp/plain.pdf"


@pytest.fixture(scope="module")
def sid_locked_files():
    """Create a session with 6 locked PDFs and distinct passwords."""
    import pikepdf
    from reportlab.pdfgen import canvas
    if not os.path.exists(PLAIN_PDF):
        c = canvas.Canvas(PLAIN_PDF); c.drawString(100, 750, "x"); c.save()

    passwords = [f"secret{i}" for i in range(6)]
    paths = []
    for i, pw in enumerate(passwords):
        p = f"/tmp/tr_locked_{i}.pdf"
        with pikepdf.open(PLAIN_PDF) as pdf:
            pdf.save(p, encryption=pikepdf.Encryption(owner=pw, user=pw))
        paths.append(p)

    s = f"trans-{uuid.uuid4().hex[:16]}"
    upload_files = []
    for i, p in enumerate(paths):
        with open(p, "rb") as f:
            upload_files.append(("files", (f"lk{i}.pdf", f.read(), "application/pdf")))
    r = requests.post(f"{API}/upload", data={"session_id": s}, files=upload_files, timeout=120)
    assert r.status_code == 200, r.text
    uploaded = r.json()["files"]

    yield s, passwords, uploaded

    try:
        requests.delete(f"{API}/session/{s}", timeout=30)
    except Exception:
        pass


def _poll_statuses(sid, until_event, observed, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline and not until_event.is_set():
        try:
            r = requests.get(f"{API}/files/{sid}", timeout=5)
            if r.status_code == 200:
                for f in r.json()["files"]:
                    observed.setdefault(f["id"], set()).add(f["status"])
        except Exception:
            pass
        time.sleep(0.08)


def test_match_passwords_sets_scanning_status(sid_locked_files):
    sid, passwords, uploaded = sid_locked_files

    # Many decoys to lengthen the scan so we can observe "scanning"
    decoys = [f"decoy_{i}" for i in range(60)]
    pw_list = decoys + passwords

    observed = {}
    done = threading.Event()
    poller = threading.Thread(target=_poll_statuses, args=(sid, done, observed), kwargs={"timeout": 30})
    poller.start()

    r = requests.post(f"{API}/match-passwords", json={"session_id": sid, "passwords": pw_list}, timeout=120)
    done.set()
    poller.join(timeout=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched_count"] == 6

    # Verify that at least some target files were observed in 'scanning' state
    scanning_seen = sum(1 for st in observed.values() if "scanning" in st)
    assert scanning_seen >= 1, f"No scanning status ever observed. Observed: {observed}"

    # Final state should be 'matched'
    for f in body["files"]:
        assert f["status"] == "matched", f


def test_unlock_sets_unlocking_status(sid_locked_files):
    sid, passwords, uploaded = sid_locked_files
    # By now files are 'matched' from previous test
    r = requests.get(f"{API}/files/{sid}", timeout=30)
    matched_ids = [f["id"] for f in r.json()["files"] if f["status"] == "matched"]
    assert len(matched_ids) >= 1

    observed = {}
    done = threading.Event()
    poller = threading.Thread(target=_poll_statuses, args=(sid, done, observed), kwargs={"timeout": 30})
    poller.start()

    r = requests.post(f"{API}/unlock", json={"session_id": sid, "file_ids": matched_ids}, timeout=120)
    done.set()
    poller.join(timeout=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unlocked"] == len(matched_ids)

    unlocking_seen = sum(1 for st in observed.values() if "unlocking" in st)
    assert unlocking_seen >= 1, f"No unlocking status ever observed. Observed: {observed}"

    for f in body["files"]:
        if f["id"] in matched_ids:
            assert f["status"] == "unlocked"
            assert f["encrypted"] is False
