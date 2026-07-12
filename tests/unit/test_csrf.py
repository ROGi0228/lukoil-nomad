from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from src.admin_panel.csrf import csrf_protect, get_csrf_token
from starlette.middleware.sessions import SessionMiddleware


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    @app.get("/token")
    async def get_token(request: Request) -> dict[str, str]:
        return {"csrf_token": get_csrf_token(request)}

    @app.post("/protected")
    async def protected(_: None = Depends(csrf_protect)) -> dict[str, bool]:
        return {"ok": True}

    return app


def test_csrf_protect_rejects_missing_token() -> None:
    client = TestClient(_build_test_app())
    client.get("/token")

    response = client.post("/protected", data={})
    assert response.status_code == 422  # Form(...) required field missing


def test_csrf_protect_rejects_wrong_token() -> None:
    client = TestClient(_build_test_app())
    client.get("/token")

    response = client.post("/protected", data={"csrf_token": "wrong-token"})
    assert response.status_code == 403


def test_csrf_protect_accepts_matching_token() -> None:
    client = TestClient(_build_test_app())
    token = client.get("/token").json()["csrf_token"]

    response = client.post("/protected", data={"csrf_token": token})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_csrf_protect_rejects_token_from_different_session() -> None:
    client_a = TestClient(_build_test_app())
    token_a = client_a.get("/token").json()["csrf_token"]

    client_b = TestClient(_build_test_app())
    client_b.get("/token")

    response = client_b.post("/protected", data={"csrf_token": token_a})
    assert response.status_code == 403
