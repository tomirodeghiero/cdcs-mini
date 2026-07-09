"""Argparse parsers for the three top-level CLI modes.

Kept in their own module so the driver focuses on control flow and the
tests can validate the parser surface independently of the rich
rendering layer.
"""

from __future__ import annotations

import argparse
from pathlib import Path

SUBCOMMANDS: frozenset[str] = frozenset({"compile", "check"})


def build_parser() -> argparse.ArgumentParser:
    """Default mode: analyzer / reporter.

    ``cdcs input.py [--out report.json]`` — same behavior as the
    original POC: parses, validates, emits JSON.
    """
    parser = argparse.ArgumentParser(
        prog="cdcs",
        description=(
            "Generate a deterministic JSON report from @generate contracts "
            "embedded in a Python source file."
        ),
    )
    parser.add_argument("input", type=Path, help="path to the Python source file")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="destination JSON file (writes to stdout if omitted)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress decorative output on stderr",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable colored output on stderr",
    )
    return parser


def build_compile_parser() -> argparse.ArgumentParser:
    """``cdcs compile`` — full synthesis.

    Invokes the LLM, emits ``input.generated.py`` /
    ``test_input.generated.py``, updates ``cdcs.lock``.
    """
    parser = argparse.ArgumentParser(
        prog="cdcs compile",
        description=(
            "Synthesize and verify implementation and tests for every "
            "@generate function in the source file."
        ),
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="output directory (defaults to the input file's directory)",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=None,
        help="path to cdcs.lock (defaults to <dest>/cdcs.lock)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="override the LLM model id (default: claude-opus-4-7)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress decorative output on stderr")
    parser.add_argument("--no-color", action="store_true", help="disable colored output on stderr")
    return parser


def build_check_parser() -> argparse.ArgumentParser:
    """``cdcs check`` — CI mode.

    No LLM call; validates that lock + generated files are in sync with
    the current contracts.
    """
    parser = argparse.ArgumentParser(
        prog="cdcs check",
        description=(
            "Verify that generated artifacts match the current @generate contracts (CI mode)."
        ),
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    return parser


__all__ = [
    "SUBCOMMANDS",
    "build_check_parser",
    "build_compile_parser",
    "build_parser",
]
