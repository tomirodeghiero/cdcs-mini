"""Vercel serverless entry. Re-exports the FastAPI app so the Vercel Python
runtime can detect it. All routing logic stays in ``web/backend/app/``."""

from __future__ import annotations

import sys
from pathlib import Path

# Vercel ships our whole repo into the function bundle, but only the installed
# wheel ends up on sys.path. Add the project root and src/ so the existing
# ``web.backend.app.main`` and ``cdcs_mini.*`` imports resolve.
_root = Path(__file__).resolve().parent.parent
for extra in (_root, _root / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from fastapi import FastAPI  # noqa: E402,F401  (Vercel's framework detector looks for this import)
from web.backend.app.main import app  # noqa: E402

__all__ = ["app"]
