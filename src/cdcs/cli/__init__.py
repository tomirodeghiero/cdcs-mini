"""``cdcs`` CLI public surface.

The implementation lives in :mod:`cdcs.cli.driver` (control flow),
:mod:`cdcs.cli.parsers` (argparse) and :mod:`cdcs.cli.ui`
(rich rendering). Importing from :mod:`cdcs.cli` gives the
stable, backwards-compatible API that the ``[project.scripts]`` entry
point and external callers rely on.
"""

from __future__ import annotations

from cdcs.cli._version import __version__
from cdcs.cli.driver import main, select_adapter
from cdcs.cli.parsers import build_parser

__all__ = ["__version__", "build_parser", "main", "select_adapter"]
