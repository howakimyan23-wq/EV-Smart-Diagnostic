import os
os.environ["DEV"] = "1"; os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ["BOOTSTRAP_ADMIN_TOKEN"] = "test-bootstrap-token-that-is-long-enough"
from fastapi.testclient import TestClient
from app.main import app
from app.vin import vin_valid, vin_check_digit_valid
def test_vin():
    assert vin_valid("1M8GDM9AXKP042788")
    assert not vin_valid("1M8GDM9AXKP04278")
    assert not vin_check_digit_valid("1M8GDM9A1KP042788")
    assert not vin_valid("IOQ")
def test_flow():
    with TestClient(app) as c:
        assert c.post("/auth/register", json={"email": "a@b.com", "password": "longenough123"}).json()["role"] == "viewer"
        admin = c.post("/auth/bootstrap", json={"email": "admin@b.com", "password": "longenough123"}, headers={"X-Bootstrap-Token": os.environ["BOOTSTRAP_ADMIN_TOKEN"]})
        assert admin.json()["role"] == "admin"
        assert c.post("/auth/bootstrap", json={"email": "other@b.com", "password": "longenough123"}, headers={"X-Bootstrap-Token": os.environ["BOOTSTRAP_ADMIN_TOKEN"]}).status_code == 409
        viewer_token = c.post("/auth/login", json={"email": "a@b.com", "password": "longenough123"}).json()["token"]
        assert c.post("/vci/connect", headers={"Authorization": f"Bearer {viewer_token}"}).status_code == 403
        t = c.post("/auth/login", json={"email": "admin@b.com", "password": "longenough123"}).json()["token"]
        h = {"Authorization": f"Bearer {t}"}
        assert c.get("/vehicles").status_code in (401, 403)
        assert c.post("/vehicles", json={"vin": "BAD"}, headers=h).status_code == 400
        v = c.post("/vehicles", json={"make": "X", "vin": "1M8GDM9AXKP042788"}, headers=h).json()
        assert v["vin_source"] == "manual"
        assert c.get("/vci/status", headers=h).json()["connected"] is False
        assert c.post(f"/vehicles/{v['id']}/diagnostics/obd", headers=h).status_code == 503
        r = c.post(f"/vehicles/{v['id']}/records", json={"kind": "dtc", "is_simulated": True, "payload": {}}, headers=h).json()
        assert r["is_simulated"] is True
        a = c.get("/adapters", headers=h).json()
        assert a["pcan_socketcan"]["read_dtc"]["supported"] is True
        assert a["pcan_socketcan"]["read_dtc"]["verified"] is False
        assert a["pcan_socketcan"]["bms"]["supported"] is False
