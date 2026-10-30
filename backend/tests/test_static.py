"""The gateway serves the built dashboard/landing page; API routes always win."""
import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app

from .conftest import AUTH


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>Sentinel</title><div id=root></div>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (tmp_path.parent / "secret.txt").write_text("outside the dist folder")
    return tmp_path


def client(dist=None, **app):
    cfg = {"api": {"token": "t" * 20}, "storage": {"db_path": ":memory:"}, "app": {**app}}
    if dist is not None:
        cfg["app"]["dashboard_dir"] = str(dist)
    return TestClient(create_app(Settings.model_validate(cfg)))


def test_root_serves_the_landing_page_with_a_strict_csp(dist):
    with client(dist) as c:
        r = c.get("/")
        assert r.status_code == 200 and "<title>Sentinel</title>" in r.text
        assert r.headers["content-type"].startswith("text/html")
        csp = r.headers["content-security-policy"]
        assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert r.headers["cache-control"] == "no-cache"


def test_client_side_routes_fall_back_to_index(dist):
    with client(dist) as c:
        for path in ("/app", "/app/events", "/app/events/123e4567"):
            r = c.get(path)
            assert r.status_code == 200 and "<div id=root>" in r.text


def test_assets_are_served_and_cached_immutably(dist):
    with client(dist) as c:
        r = c.get("/assets/app-abc123.js")
        assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
        assert c.get("/favicon.svg").status_code == 200
        assert c.get("/assets/missing.js").status_code == 404  # a missing file is a 404, not the SPA


def test_path_traversal_cannot_escape_the_dashboard_folder(dist):
    with client(dist) as c:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/../../secret.txt"):
            r = c.get(path)
            assert "outside the dist folder" not in r.text, path


def test_api_routes_always_win_and_unknown_api_paths_are_json_404(dist):
    with client(dist) as c:
        assert c.get("/api/health").json() == {"status": "ok"}
        assert c.get("/api/events", headers=AUTH).status_code in (200, 401)
        r = c.get("/api/does-not-exist")
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")
        assert c.get("/metrics").status_code == 401  # not swallowed by the SPA
        assert c.get("/docs").status_code == 404 and "<div id=root>" not in c.get("/docs").text


def test_without_a_build_the_root_explains_how_to_build_it(tmp_path):
    with client(tmp_path / "nothing-here") as c:
        r = c.get("/")
        assert r.status_code == 200 and "npm run build" in r.text
        assert c.get("/some/other/path").status_code == 404
        assert c.get("/api/health").status_code == 200


def test_serving_can_be_disabled(dist):
    with client(dist, serve_dashboard=False) as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/health").status_code == 200
