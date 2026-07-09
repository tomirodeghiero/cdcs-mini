"""Single source of truth for the CLI version string.

Kept in its own leaf module so the cli submodules can pull it without
risking a circular import via the package ``__init__``.
"""

from __future__ import annotations

__version__ = "0.1.0"
