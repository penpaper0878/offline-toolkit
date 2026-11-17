"""Single-process mode: the API also serves the built web client (CLP_STATIC_DIR)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture()
def served(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>CivilLabPro OS</title>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log('app')")
    (tmp_path / "sw.js").write_text("// service worker")
    (tmp_path.parent / "secret.txt").write_text("outside the client folder")
    monkeypatch.setenv("CLP_STATIC_DIR", str(tmp_path))
    get_settings.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


def test_client_routes_fall_back_to_index(served):
    for path in ("/", "/projects", "/designs/8f1c2c1e-0000-4000-8000-000000000000", "/login"):
        r = served.get(path)
        assert r.status_code == 200 and "CivilLabPro OS" in r.text and r.headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_and_other_files_revalidated(served):
    r = served.get("/assets/index-abc123.js")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert served.get("/assets/missing.js").status_code == 404
    r = served.get("/sw.js")
    assert r.text == "// service worker" and r.headers["cache-control"] == "no-cache"


def test_api_keeps_its_own_errors_and_paths_cannot_escape(served):
    assert served.get("/api/v1/health").json()["status"] == "ok"
    r = served.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        assert "outside the client folder" not in served.get(path).text


def test_missing_build_is_reported_at_start(tmp_path, monkeypatch):
    monkeypatch.setenv("CLP_STATIC_DIR", str(tmp_path / "nowhere"))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="build the web client first"):
        create_app()
    get_settings.cache_clear()
