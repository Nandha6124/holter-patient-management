import os

os.environ["DATABASE_URL"] = "sqlite:///./test_holter.db"
os.environ["ADMIN_EMAIL"] = "doc@example.com"
os.environ["ADMIN_PASSWORD"] = "correct-horse-1"

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if os.path.exists("test_holter.db"):
        os.remove("test_holter.db")


@pytest.fixture(scope="module")
def auth():
    r = client.post("/api/auth/login", json={"email": "doc@example.com", "password": "correct-horse-1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


PATIENT = {"full_name": "Test Patient", "age": 54, "sex": "F", "phone": "9000012345", "indication": "Palpitations"}
REC = {"recorded_on": "2025-03-01", "duration_hours": 24, "avg_hr": 72, "min_hr": 48, "max_hr": 131,
       "pvc_count": 120, "pause_count": 1, "af_detected": False, "summary": "Sinus rhythm", "status": "pending"}


def test_login_rules():
    assert client.post("/api/auth/login", json={"email": "doc@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code == 401


def test_all_api_routes_require_login():
    for method, path in [("get", "/api/patients"), ("post", "/api/patients"), ("get", "/api/dashboard"),
                         ("get", "/api/patients/1"), ("delete", "/api/recordings/1"), ("get", "/api/auth/me")]:
        assert getattr(client, method)(path).status_code == 401, path
    expired = jwt.encode({"sub": "1", "exp": 1}, settings.secret_key, algorithm="HS256")
    assert client.get("/api/patients", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_patient_crud_and_mrn(auth):
    r = client.post("/api/patients", json=PATIENT, headers=auth)
    assert r.status_code == 201
    p = r.json()
    assert p["mrn"] == f"HP-{p['id']:05d}"
    upd = client.put(f"/api/patients/{p['id']}", json={**PATIENT, "age": 55}, headers=auth)
    assert upd.json()["age"] == 55 and upd.json()["mrn"] == p["mrn"]
    assert client.get(f"/api/patients/{p['id']}", headers=auth).json()["full_name"] == "Test Patient"
    assert client.delete(f"/api/patients/{p['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/patients/{p['id']}", headers=auth).status_code == 404


def test_patient_validation(auth):
    assert client.post("/api/patients", json={**PATIENT, "age": 200}, headers=auth).status_code == 422
    assert client.post("/api/patients", json={**PATIENT, "sex": "X"}, headers=auth).status_code == 422
    assert client.post("/api/patients", json={**PATIENT, "full_name": "A"}, headers=auth).status_code == 422


def test_search(auth):
    a = client.post("/api/patients", json={**PATIENT, "full_name": "Zelda Quinn", "phone": "9111100000"}, headers=auth).json()
    client.post("/api/patients", json={**PATIENT, "full_name": "Other Person", "phone": "9222200000"}, headers=auth)
    names = lambda q: [p["full_name"] for p in client.get("/api/patients", params={"q": q}, headers=auth).json()]  # noqa: E731
    assert names("zelda") == ["Zelda Quinn"]
    assert names("91111") == ["Zelda Quinn"]
    assert names(a["mrn"]) == ["Zelda Quinn"]
    assert names("%") == []  # wildcard characters are escaped, not treated as match-all
    assert len(names("")) >= 2


def test_recordings_and_cascade(auth):
    pid = client.post("/api/patients", json=PATIENT, headers=auth).json()["id"]
    r = client.post(f"/api/patients/{pid}/recordings", json=REC, headers=auth)
    assert r.status_code == 201
    rid = r.json()["id"]
    upd = client.put(f"/api/recordings/{rid}", json={**REC, "status": "reviewed", "af_detected": True}, headers=auth)
    assert upd.json()["status"] == "reviewed" and upd.json()["af_detected"] is True
    assert len(client.get(f"/api/patients/{pid}/recordings", headers=auth).json()) == 1
    assert client.get(f"/api/patients/{pid}", headers=auth).json()["recording_count"] == 1
    client.delete(f"/api/patients/{pid}", headers=auth)
    assert client.put(f"/api/recordings/{rid}", json=REC, headers=auth).status_code == 404  # removed with patient


def test_recording_validation(auth):
    pid = client.post("/api/patients", json=PATIENT, headers=auth).json()["id"]
    bad_order = {**REC, "min_hr": 90, "avg_hr": 72}
    assert client.post(f"/api/patients/{pid}/recordings", json=bad_order, headers=auth).status_code == 422
    assert client.post(f"/api/patients/{pid}/recordings", json={**REC, "duration_hours": 0}, headers=auth).status_code == 422
    assert client.post("/api/patients/99999/recordings", json=REC, headers=auth).status_code == 404


def test_dashboard(auth):
    pid = client.post("/api/patients", json=PATIENT, headers=auth).json()["id"]
    client.post(f"/api/patients/{pid}/recordings", json={**REC, "af_detected": True}, headers=auth)
    d = client.get("/api/dashboard", headers=auth).json()
    assert d["total_patients"] >= 1 and d["total_recordings"] >= 1
    assert d["pending_review"] >= 1 and d["af_flagged"] >= 1
    assert d["recent"][0]["patient_name"] and d["avg_heart_rate"] is not None


def test_frontend_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "Holter PMS" in r.text
    assert client.get("/app.js").status_code == 200
