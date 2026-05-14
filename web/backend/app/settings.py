"""Configuration for the HTTP layer.

All the knobs sit here so swapping to env-backed settings
(``pydantic-settings``, dotenv, whatever) is a small change later.
"""

from __future__ import annotations

from typing import Final

# Hard upload cap. Anything bigger and we say "too large" instead of
# eating memory and stalling the analyzer
MAX_UPLOAD_BYTES: Final[int] = 1_000_000

# CORS origins for local frontend dev
CORS_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

API_TITLE: Final[str] = "cdcs-mini API"
API_VERSION: Final[str] = "0.1.0"
API_SUMMARY: Final[str] = "Deterministic @generate contract reporter."

API_DESCRIPTION: Final[str] = """
HTTP wrapper around **cdcs-mini** — a deterministic parser, validator and
JSON reporter for behavioral contracts (`@generate`) embedded in Python
source code.

The same `ReportService` powers the CLI
(`cdcs-mini input.py --out report.json`) and these endpoints, so the JSON
returned here is byte-for-byte identical to what the CLI writes.

### Quick reference

| Endpoint                     | Purpose                                  |
| ---------------------------- | ---------------------------------------- |
| `GET /health`                | liveness probe                           |
| `POST /reports/from-source`  | analyze inline Python source             |
| `POST /reports/from-file`    | analyze an uploaded `.py` file (≤ 1 MB)  |

### Determinism guarantee

For a given input, the response is stable across runs:
key ordering is fixed in the encoder, parameter declaration order is
preserved, and diagnostics are pre-sorted by `(line, code, message)`.
"""

TAGS_METADATA: Final[list[dict[str, str]]] = [
    {
        "name": "Health",
        "description": "Liveness probe used by load balancers and the frontend.",
    },
    {
        "name": "Reports",
        "description": (
            "Generate a deterministic JSON report from `@generate` "
            "contracts embedded in Python source."
        ),
    },
]

SWAGGER_UI_PARAMETERS: Final[dict[str, object]] = {
    "docExpansion": "list",
    "defaultModelsExpandDepth": 1,
    "displayRequestDuration": True,
    "filter": True,
    "persistAuthorization": True,
    "syntaxHighlight.theme": "monokai",
    "tryItOutEnabled": True,
}
