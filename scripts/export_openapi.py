"""Write the gateway's OpenAPI document to docs/openapi.json (interactive docs are disabled in production).

    python scripts/export_openapi.py
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.core.config import ROOT, Settings
from backend.main import create_app


def main() -> None:
    app = create_app(Settings.model_validate({"app": {"debug": True}}))
    spec = app.openapi()
    spec["info"]["description"] = (
        "Management endpoints require `Authorization: Bearer <SENTINEL_API_TOKEN>`. `/graphql-proxy` is public unless "
        "`SENTINEL_GATEWAY_KEYS` is set, in which case it requires `X-API-Key`. See docs/api.md.")
    target = Path(ROOT) / "docs" / "openapi.json"
    target.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {target} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
