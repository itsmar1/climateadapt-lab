"""Export the FastAPI OpenAPI contract to docs/openapi.json (P11).

Deterministic: same app, same file (sorted keys, fixed indent). The React
frontend consumes this file as its typed-client contract (see README).
Run after any route or schema change:

    uv run python scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path

from climateadapt.api.main import create_app

OUT = Path("docs/openapi.json")


def main() -> int:
    spec = create_app().openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    paths = sorted(spec["paths"])
    print(f"wrote {OUT} ({len(paths)} paths)")
    for path in paths:
        print(f"  {path}: {sorted(spec['paths'][path])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
