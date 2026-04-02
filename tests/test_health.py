from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["shadow_mode"] is True


def test_generate_response_stub():
    r = client.post("/api/v1/generate-response", params={"conversation_id": 1, "interaction_id": 1})
    assert r.status_code == 200
    assert r.json()["status"] == "not_implemented"
