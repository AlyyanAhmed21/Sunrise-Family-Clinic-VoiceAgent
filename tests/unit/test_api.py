from fastapi.testclient import TestClient

from clinic.api.main import app


def test_health_is_available() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
