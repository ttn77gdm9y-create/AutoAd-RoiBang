from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_unhandled_exception_returns_json_500(tmp_path: Path):
    app = create_app(project_root=tmp_path)

    @app.get("/api/test-crash")
    def test_crash() -> dict:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/test-crash")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "detail": "本地服务异常，请查看后端日志",
        "error_code": "internal_server_error",
        "message": "本地服务异常，请查看后端日志",
    }


def test_http_exception_keeps_detail_and_returns_json(tmp_path: Path):
    app = create_app(project_root=tmp_path)

    @app.get("/api/test-http-error")
    def test_http_error() -> dict:
        raise HTTPException(status_code=418, detail="自定义错误")

    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/test-http-error")

    assert response.status_code == 418
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "detail": "自定义错误",
        "error_code": "http_error",
        "message": "自定义错误",
    }

