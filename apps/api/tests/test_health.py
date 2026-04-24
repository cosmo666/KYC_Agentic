from fastapi.testclient import TestClient
from app.main import app


def test_health_returns_status():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "ollama" in body  # "reachable" or "unreachable"
