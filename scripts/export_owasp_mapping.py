"""Generate docs/owasp-mapping.md from sentinel_core.catalog (the single source of truth).

    python scripts/export_owasp_mapping.py          # rewrite the file
    python scripts/export_owasp_mapping.py --check  # exit 1 if it is out of date
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sentinel_core.catalog import CATALOG, OWASP_API_2023  # noqa: E402

OUT = ROOT / "docs" / "owasp-mapping.md"


def render() -> str:
    lines = [
        "# OWASP API Security Top 10 (2023) mapping",
        "",
        "Generated from `sentinel_core/catalog.py` by `scripts/export_owasp_mapping.py`; a test fails if this file is stale.",
        "Every explanation in an API response and in the audit log carries the `owasp` categories and `attack_class` below.",
        "",
        "Sentinel inspects the GraphQL *operation*, so it addresses API4 (resource consumption), API8/API9 (reconnaissance and",
        "unregistered operations) and the parts of API1-API3 and API6 that are visible in the request shape (enumeration",
        "across aliases, credential guessing, sensitive-field harvesting). It does not do authorization (API1, API3, API5",
        "proper), SSRF (API7) or outbound-call safety (API10); those stay in the application.",
        "",
        "## By OWASP category",
        "",
        "| Category | Name | Rules and controls |",
        "|---|---|---|",
    ]
    for cat, name in OWASP_API_2023.items():
        ids = [r.id for r in CATALOG.values() if cat in r.owasp]
        lines.append(f"| {cat}:2023 | {name} | " + (", ".join(f"`{i}`" for i in ids) if ids else "not addressed (out of scope)") + " |")
    lines += ["", "## By rule", "", "| Rule | Kind | OWASP | GraphQL attack class | What it does |", "|---|---|---|---|---|"]
    for r in CATALOG.values():
        lines.append(f"| `{r.id}` | {r.kind} | {', '.join(r.owasp)} | {r.attack_class} | {r.summary} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        sys.exit(0 if OUT.exists() and OUT.read_text(encoding="utf-8") == text else 1)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
