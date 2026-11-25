from fastapi.testclient import TestClient
from src.main import app


def test_liveness_ok():
    client = TestClient(app)
    resp = client.get("/health/liveness")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "title": "Estado da aplicação",
        "description": "Utilizado pela esteira para validar o estado da aplicação",
        "version": "v1.0",
        "status": "OK",
    }


def test_readiness_ok():
    client = TestClient(app)
    resp = client.get("/health/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {
        "title": "Status da prontidão",
        "description": "Utilizado pela esteira para validar a prontidão da aplicação",
        "version": "v1.0",
        "status": "OK",
    }
