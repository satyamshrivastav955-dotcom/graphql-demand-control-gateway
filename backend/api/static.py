"""Serve the built dashboard (landing page + /app) from the gateway itself.

Makes `python scripts/dev.py` show the product at http://127.0.0.1:8000 without a separate web server. In production the
nginx container serves the same files; this is a convenience for local use and small deployments. API routes always win:
paths under /api, /graphql-proxy and /metrics are never answered with the SPA.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from ..core.config import ROOT, Settings

# Same policy as docker/nginx.conf: same-origin only, no inline scripts, no third-party requests.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
RESERVED = ("api/", "graphql-proxy", "metrics", "docs", "openapi.json", "redoc")

HELP_PAGE = """<!doctype html><meta charset="utf-8"><title>GraphQL Sentinel</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:12vh auto;padding:0 1.25rem;color:#1b1b1b}
code,pre{background:#f1efe9;padding:.15em .4em;border-radius:4px}pre{padding:1em;overflow:auto}</style>
<h1>GraphQL Sentinel gateway is running</h1>
<p>The dashboard and landing page have not been built yet, so there is nothing to show here. Build them once:</p>
<pre>cd dashboard
npm ci
npm run build</pre>
<p>then reload this page. For live-reload development use <code>npm run dev</code> (http://localhost:3000).</p>
<p>API: <code>POST /graphql-proxy</code>, <code>GET /api/health</code>.</p>"""


def dashboard_dir(settings: Settings) -> Optional[Path]:
    configured = settings.app.dashboard_dir
    path = Path(configured) if configured else ROOT / "dashboard" / "dist"
    if not path.is_absolute():
        path = ROOT / path
    return path if (path / "index.html").is_file() else None


def mount_dashboard(app: FastAPI, settings: Settings) -> None:
    if not settings.app.serve_dashboard:
        return
    dist = dashboard_dir(settings)
    root = dist.resolve() if dist else None

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request) -> Response:
        if full_path.startswith(RESERVED):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if root is None:
            return HTMLResponse(HELP_PAGE, status_code=200 if full_path in ("", "app") else 404,
                                headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})
        candidate = (root / full_path).resolve() if full_path else root / "index.html"
        if candidate.is_file() and candidate.is_relative_to(root):
            target, is_asset = candidate, full_path.startswith("assets/")
        elif "." in Path(full_path).name:  # a missing file (not a client-side route)
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        else:
            target, is_asset = root / "index.html", False  # client-side route: let the SPA render it
        headers = {"Content-Security-Policy": CSP, "Cache-Control": "public, max-age=31536000, immutable" if is_asset
                   else "no-cache"}
        media = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return FileResponse(target, media_type=media, headers=headers)
