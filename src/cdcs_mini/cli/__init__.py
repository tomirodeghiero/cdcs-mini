"""``cdcs-mini`` CLI public surface.

The implementation lives in :mod:`cdcs_mini.cli.driver` (control flow),
:mod:`cdcs_mini.cli.parsers` (argparse) and :mod:`cdcs_mini.cli.ui`
(rich rendering). Importing from :mod:`cdcs_mini.cli` gives the
stable, backwards-compatible API that the ``[project.scripts]`` entry
point and external callers rely on.
"""

from __future__ import annotations

from cdcs_mini.cli._version import __version__
from cdcs_mini.cli.driver import main, select_adapter
from cdcs_mini.cli.parsers import build_parser

__all__ = ["__version__", "build_parser", "main", "select_adapter"]
