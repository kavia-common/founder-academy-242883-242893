"""
Generate OpenAPI schema JSON into `fouguide_backend/interfaces/openapi.json`.

This script is used by CI and by developers to refresh the OpenAPI file consumed
by the frontend container.
"""

import json
import sys
from pathlib import Path

# Ensure imports work when invoked from repo root or container root.
_THIS_FILE = Path(__file__).resolve()
_BACKEND_ROOT = _THIS_FILE.parents[2]  # fouguide_backend/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from src.api.main import app  # noqa: E402  (import after sys.path adjustment)

openapi_schema = app.openapi()

output_dir = _BACKEND_ROOT / "interfaces"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "openapi.json"

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
    f.write("\n")

print(f"Wrote OpenAPI schema to: {output_path}")
