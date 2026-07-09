"""Validate that LLM-emitted TypeScript parses.

Used by :class:`SynthesisOrchestrator` to detect malformed output and
trigger the repair loop. Returns ``(token, None)`` on success — the
``token`` is a sentinel; downstream gates check it with ``isinstance``
and short-circuit when they don't recognise the type. On failure
returns ``(None, message)`` so the orchestrator surfaces the parse
error to the LLM in the next repair prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from cdcs.language.typescript._runtime import (
    TypeScriptRuntimeError,
    call_parse_source,
)
from cdcs.synthesis.gates import GateFailure
from cdcs.synthesis.prompt import PromptTarget


@dataclass(frozen=True, slots=True)
class TypeScriptParseSentinel:
    """Marker placed in ``Candidate.tree`` when LLM output parsed cleanly.

    Carries the function names we found so a future TS-aware gate can
    use them without re-parsing.
    """

    function_names: tuple[str, ...]


def try_parse_typescript(code: str) -> tuple[TypeScriptParseSentinel | None, str | None]:
    """Run the LLM output through the ts-runtime source parser.

    Treats a clean parse as success and surfaces TS syntax errors as
    parse failures. Top-level function presence is **not** enforced here
    because the same code parser is shared between the impl loop and
    the test loop — and test modules legitimately consist of ``test(...)``
    call expressions with no top-level ``function`` at all.

    The impl loop wires a separate ``test_sanity_checker`` /
    ``StructureGate`` that decides whether the discovered functions are
    enough for its purpose.
    """
    try:
        payload = call_parse_source(code, "__llm_output__.ts")
    except TypeScriptRuntimeError as exc:
        return None, f"ts-runtime unavailable: {exc}"
    errors = payload.get("errors", [])
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            line = first.get("line")
            message = first.get("message", "syntax error")
            location = f" at line {line}" if isinstance(line, int) else ""
            return None, f"{message}{location}"
    functions = payload.get("functions", [])
    names: tuple[str, ...] = ()
    if isinstance(functions, list):
        names = tuple(
            fn["name"]
            for fn in functions
            if isinstance(fn, dict) and isinstance(fn.get("name"), str)
        )
    return TypeScriptParseSentinel(function_names=names), None


def typescript_test_sanity_failures(raw: str, target: PromptTarget) -> tuple[GateFailure, ...]:
    """Cheap structural check on a TS test module.

    Catches the common LLM failure mode where the test prompt is misread
    as another implementation prompt. We look for the vitest import
    (``import { ... } from "vitest"``) and at least one ``test(`` or
    ``it(`` call. Anything more rigorous (running vitest) is an external
    gate.
    """
    failures: list[GateFailure] = []
    has_vitest_import = 'from "vitest"' in raw or "from 'vitest'" in raw
    if not has_vitest_import:
        failures.append(
            GateFailure(
                gate="test-structure",
                message=(
                    f'generated tests must import from "vitest" and call {target.function_name!r}'
                ),
            )
        )
    has_test_call = ("test(" in raw) or ("it(" in raw) or ("describe(" in raw)
    if not has_test_call:
        failures.append(
            GateFailure(
                gate="test-structure",
                message=(
                    "generated tests must define at least one vitest `test(...)` / `it(...)` case"
                ),
            )
        )
    if target.function_name not in raw:
        failures.append(
            GateFailure(
                gate="test-structure",
                message=(f"generated tests never reference {target.function_name!r}"),
            )
        )
    return tuple(failures)
