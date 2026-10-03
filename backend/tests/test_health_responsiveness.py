"""Iteration 5: /health must remain responsive while heavy unlock/match runs."""
import os
import io
import uuid
import time
import threading
import statistics
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mass-file-vault.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PLAIN_PDF = "/tmp/plain.pdf"


def test_api_health_ok():
    r = requests.get(f"{API}/health", timeout=5)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_internal_health_ok():
    # /health at origin root - external ingress may not route non-/api to backend,
    # so hit backend directly via localhost
    try:
        r = requests.get("http://localhost:8001/health", timeout=5)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    except requests.exceptions.ConnectionError:
        pytest.skip("Backend not reachable on localhost:8001")


@pytest.fixture(scope="module")
def heavy_session():
    """Create a session with multiple locked PDFs for heavy workload."""
    import pikepdf
    from reportlab.pdfgen import canvas
    if not os.path.exists(PLAIN_PDF):
        c = canvas.Canvas(PLAIN_PDF); c.drawString(100, 750, "x"); c.save()

    passwords = [f"secret{i}" for i in range(6)]
    paths = []
    for i, pw in enumerate(passwords):
        p = f"/tmp/hv_lk{i}.pdf"
        with pikepdf.open(PLAIN_PDF) as pdf:
            pdf.save(p, encryption=pikepdf.Encryption(owner=pw, user=pw))
        paths.append(p)

    s = f"heavy-{uuid.uuid4().hex[:16]}"
    upload_files = []
    for i, p in enumerate(paths):
        with open(p, "rb") as f:
            upload_files.append(("files", (f"hv{i}.pdf", f.read(), "application/pdf")))
    r = requests.post(f"{API}/upload", data={"session_id": s}, files=upload_files, timeout=120)
    assert r.status_code == 200, r.text
    uploaded = r.json()["files"]
    yield s, passwords, uploaded
    try:
        requests.delete(f"{API}/session/{s}", timeout=30)
    except Exception:
        pass


def _hammer_health(stop_evt, latencies, errors, url):
    while not stop_evt.is_set():
        t0 = time.time()
        try:
            r = requests.get(url, timeout=2)
            dt = time.time() - t0
            if r.status_code == 200:
                latencies.append(dt)
            else:
                errors.append(("status", r.status_code, dt))
        except Exception as e:
            errors.append(("exc", str(e)[:80], time.time() - t0))
        time.sleep(0.05)


def test_health_responsive_during_match(heavy_session):
    sid, passwords, uploaded = heavy_session
    # Load with many decoys to make the match long and CPU-heavy
    decoys = [f"decoy_{i}" for i in range(80)]
    pw_list = decoys + passwords

    stop = threading.Event()
    latencies = []
    errors = []
    # Spawn 3 concurrent health hammerers
    threads = [
        threading.Thread(target=_hammer_health, args=(stop, latencies, errors, f"{API}/health"))
        for _ in range(3)
    ]
    for t in threads:
        t.start()

    t0 = time.time()
    r = requests.post(f"{API}/match-passwords", json={"session_id": sid, "passwords": pw_list}, timeout=180)
    elapsed = time.time() - t0
    stop.set()
    for t in threads:
        t.join(timeout=3)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched_count"] == 6

    print(f"match elapsed={elapsed:.2f}s, health probes={len(latencies)}, errors={len(errors)}")
    assert len(latencies) >= 10, f"Too few successful /health probes during heavy load ({len(latencies)}). errors={errors[:5]}"

    max_lat = max(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max_lat
    avg = statistics.mean(latencies)
    print(f"/health latency: avg={avg*1000:.0f}ms p95={p95*1000:.0f}ms max={max_lat*1000:.0f}ms")
    # If event loop were starved, we'd see timeouts (>2s -> request exception) or very high latencies
    assert max_lat < 2.0, f"/health max latency {max_lat:.2f}s exceeds 2s (event loop likely blocked). errors={errors[:5]}"
    assert p95 < 1.5, f"/health p95 latency {p95:.2f}s indicates event loop contention"
    assert len(errors) == 0, f"/health errors during heavy load: {errors[:5]}"


def test_health_responsive_during_unlock(heavy_session):
    sid, passwords, uploaded = heavy_session
    # Files are already matched from previous test
    r = requests.get(f"{API}/files/{sid}", timeout=30)
    matched_ids = [f["id"] for f in r.json()["files"] if f["status"] == "matched"]
    assert len(matched_ids) >= 1, "No matched files to unlock"

    stop = threading.Event()
    latencies = []
    errors = []
    threads = [
        threading.Thread(target=_hammer_health, args=(stop, latencies, errors, f"{API}/health"))
        for _ in range(3)
    ]
    for t in threads:
        t.start()

    t0 = time.time()
    r = requests.post(f"{API}/unlock", json={"session_id": sid, "file_ids": matched_ids}, timeout=180)
    elapsed = time.time() - t0
    stop.set()
    for t in threads:
        t.join(timeout=3)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unlocked"] == len(matched_ids)

    print(f"unlock elapsed={elapsed:.2f}s, health probes={len(latencies)}, errors={len(errors)}")
    assert len(latencies) >= 5, f"Too few successful /health probes during unlock ({len(latencies)})"
    max_lat = max(latencies)
    print(f"/health during unlock: max={max_lat*1000:.0f}ms")
    assert max_lat < 2.0, f"/health max latency {max_lat:.2f}s during unlock - event loop blocked. errors={errors[:5]}"
    assert len(errors) == 0, f"/health errors during unlock: {errors[:5]}"
