"""Run the demo upstream and the gateway locally (no Docker) and show the product in your browser.

    python scripts/dev.py                      # builds the dashboard if needed, serves everything on http://127.0.0.1:8000
    python scripts/dev.py --port 8010          # pick another port if 8000 is taken
    cd dashboard && npm run dev                # optional: live-reload dashboard on :3000, proxying /api to the gateway
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sources_newer_than(dash: Path, stamp: float) -> bool:
    """True if any dashboard source file changed after the last build."""
    roots = [dash / "src", dash / "public", dash / "index.html", dash / "package.json", dash / "vite.config.mts"]
    for r in roots:
        files = [r] if r.is_file() else list(r.rglob("*")) if r.is_dir() else []
        if any(f.is_file() and f.stat().st_mtime > stamp for f in files):
            return True
    return False


def ensure_dashboard_built() -> bool:
    """Build dashboard/dist (first run, or when sources changed) so the gateway can serve the landing page."""
    dash = ROOT / "dashboard"
    built = dash / "dist" / "index.html"
    if built.is_file() and not _sources_newer_than(dash, built.stat().st_mtime):
        return True
    npm = shutil.which("npm")
    if not npm:
        print("npm not found: install Node 20+ to build the dashboard (the gateway still runs).")
        return False
    print("Building the dashboard (first run, or sources changed)...")
    try:
        if not (dash / "node_modules").is_dir():
            subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=dash, check=True)
        subprocess.run([npm, "run", "build"], cwd=dash, check=True)
    except subprocess.CalledProcessError:
        print("Dashboard build failed; the gateway will still run. Try: cd dashboard && npm ci && npm run build")
        return False
    return True


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the demo upstream and the gateway locally.")
    ap.add_argument("--port", type=int, default=8000, help="gateway port (default 8000)")
    ap.add_argument("--upstream-port", type=int, default=8001, help="demo upstream port (default 8001)")
    args = ap.parse_args()

    busy = [p for p in (args.port, args.upstream_port) if port_in_use(p)]
    if busy:
        print(f"Port(s) {', '.join(map(str, busy))} already in use (probably an earlier run still going).\n"
              f"Stop it, or choose free ports:  python scripts/dev.py --port {args.port + 10} "
              f"--upstream-port {args.upstream_port + 10}")
        return 1

    built = ensure_dashboard_built()
    token = os.environ.get("SENTINEL_API_TOKEN") or secrets.token_urlsafe(24)
    env = {**os.environ, "SENTINEL_UPSTREAM_URL": f"http://127.0.0.1:{args.upstream_port}/graphql",
           "SENTINEL_API_TOKEN": token, "PYTHONPATH": str(ROOT)}
    uvicorn = [sys.executable, "-m", "uvicorn"]
    procs = [
        subprocess.Popen([*uvicorn, "demo.upstream.app:app", "--port", str(args.upstream_port), "--log-level", "warning"],
                         cwd=ROOT, env=env),
        subprocess.Popen([*uvicorn, "backend.main:app", "--port", str(args.port)], cwd=ROOT, env=env),
    ]
    url = f"http://127.0.0.1:{args.port}"
    print(f"upstream http://127.0.0.1:{args.upstream_port}/graphql | gateway {url} (Ctrl+C to stop)")
    print(f"dashboard access token (this session only): {token}")
    print(f"\nOpen {url}  (landing page; the dashboard is at /app)" if built else
          f"\nDashboard not built; see the message above. API: {url}/api/health")
    if built and not os.environ.get("SENTINEL_NO_BROWSER"):
        time.sleep(4)
        webbrowser.open(url)
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        print("A server exited unexpectedly; stopping the other one.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
