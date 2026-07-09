"""Subprocess bridge between the Python side and ``ts-runtime/``.

Every call here spawns a short-lived Node process that reads JSON on
stdin and writes JSON on stdout. The protocol is defined in
``ts-runtime/src/types.ts`` — keep them in sync.

We prefer the compiled ``ts-runtime/dist/bin/*.js`` artefacts when they
exist (faster: ~50 ms warm start). Otherwise we fall back to running the
TS source directly through ``tsx`` (slower but no build step needed in
dev). The fallback keeps ``cdcs`` usable right after ``make
ts-install`` without an explicit build.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final


class TypeScriptRuntimeError(RuntimeError):
    """Raised when the Node subprocess fails or returns malformed JSON."""


# Walk up from this module until we find the repo root (the parent of
# ``src/cdcs``). That keeps the lookup robust against editable
# installs and from anywhere in the test suite.
_THIS_FILE: Final[Path] = Path(__file__).resolve()


def _repo_root() -> Path:
    for candidate in _THIS_FILE.parents:
        if (candidate / "ts-runtime").is_dir() and (candidate / "pyproject.toml").is_file():
            return candidate
    raise TypeScriptRuntimeError(
        "could not locate the repository root containing ts-runtime/. "
        "Are you running cdcs outside the source tree?"
    )


@dataclass(frozen=True, slots=True)
class _Invocation:
    argv: tuple[str, ...]


def _resolve_invocation(bin_name: str) -> _Invocation:
    """Pick the cheapest available way to run a ts-runtime CLI script.

    Order of preference:

    1. ``CDCS_TS_RUNTIME`` env var (absolute path to a built ``.js``).
       Lets advanced users / CI point at a custom build location.
    2. ``ts-runtime/dist/bin/{bin_name}.js`` — the compiled artefact
       produced by ``npm run build``.
    3. ``ts-runtime/node_modules/.bin/tsx`` + the ``.ts`` source —
       no build step required, but adds ~200 ms of startup.
    """
    override = os.environ.get("CDCS_TS_RUNTIME", "").strip()
    if override:
        return _Invocation(argv=("node", override))
    root = _repo_root()
    dist_js = root / "ts-runtime" / "dist" / "bin" / f"{bin_name}.js"
    if dist_js.is_file():
        return _Invocation(argv=("node", str(dist_js)))
    tsx_bin = root / "ts-runtime" / "node_modules" / ".bin" / "tsx"
    ts_src = root / "ts-runtime" / "src" / "bin" / f"{bin_name}.ts"
    if tsx_bin.is_file() and ts_src.is_file():
        return _Invocation(argv=(str(tsx_bin), str(ts_src)))
    raise TypeScriptRuntimeError(
        f"ts-runtime is not available: neither {dist_js} nor {tsx_bin} exist. "
        "Run `make ts-install` (and optionally `make ts-build`) first."
    )


def _run_bin(bin_name: str, payload: object, *, timeout: float = 60.0) -> Any:
    invocation = _resolve_invocation(bin_name)
    serialized = json.dumps(payload).encode("utf-8")
    try:
        completed = subprocess.run(
            invocation.argv,
            input=serialized,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise TypeScriptRuntimeError(
            f"ts-runtime binary not found: {invocation.argv[0]}. Is Node installed?"
        ) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise TypeScriptRuntimeError(
            f"ts-runtime/{bin_name} exited {completed.returncode}: {stderr or '<no stderr>'}"
        )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise TypeScriptRuntimeError(
            f"ts-runtime/{bin_name} returned non-JSON output: {stdout[:200]!r}"
        ) from exc


# --- typed wrappers -------------------------------------------------


def call_parse_expressions(operations: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    """Run one batched expression-parsing request through the Node runtime."""
    response = _run_bin("parse-expressions", {"operations": list(operations)})
    if not isinstance(response, dict) or "results" not in response:
        raise TypeScriptRuntimeError(
            f"parse-expressions returned an unexpected payload: {response!r}"
        )
    results = response["results"]
    if not isinstance(results, list):
        raise TypeScriptRuntimeError(f"parse-expressions returned non-list results: {results!r}")
    return results


def call_parse_source(source: str, filename: str) -> dict[str, Any]:
    """Run one source-parse request through the Node runtime."""
    response = _run_bin("parse-source", {"source": source, "filename": filename})
    if not isinstance(response, dict):
        raise TypeScriptRuntimeError(f"parse-source returned non-dict: {response!r}")
    return response


def ts_runtime_available() -> bool:
    """True when the runtime can be invoked without raising.

    Used by the test suite to ``pytest.skip`` cleanly on machines where
    Node + the ts-runtime workspace haven't been installed.
    """
    try:
        _resolve_invocation("parse-expressions")
        return True
    except TypeScriptRuntimeError:
        return False
