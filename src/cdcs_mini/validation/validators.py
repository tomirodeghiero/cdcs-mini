"""Validators that run after the contract is parsed.

Each one is pure: signature + contract + line in, diagnostics out.
That keeps them trivial to test and free to compose.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable
from typing import Final, Protocol

from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import BehaviorStep, Contract, Signature

# Names that can show up inside DSL expressions and aren't function parameters:
# every Python builtin plus a small set of matcher keywords (digits, alpha, ...)
_DSL_CONSTANTS: Final[frozenset[str]] = frozenset(
    {"digits", "alpha", "alnum", "whitespace", "ascii", "True", "False", "None"}
)
KNOWN_NON_PARAMETER_NAMES: Final[frozenset[str]] = frozenset(dir(builtins)) | _DSL_CONSTANTS


class ContractValidator(Protocol):
    def __call__(
        self, *, signature: Signature, contract: Contract, function_line: int
    ) -> Iterable[Diagnostic]: ...


def validate_examples_present(
    *, signature: Signature, contract: Contract, function_line: int
) -> Iterable[Diagnostic]:
    _ = signature
    if contract.has_examples_section and contract.examples:
        return ()
    return (
        Diagnostic(
            line=function_line,
            code=DiagnosticCode.MISSING_SAMPLES,
            message="examples section not found",
        ),
    )


def validate_known_parameters(
    *, signature: Signature, contract: Contract, function_line: int
) -> Iterable[Diagnostic]:
    _ = function_line
    known = signature.parameter_names | KNOWN_NON_PARAMETER_NAMES
    diagnostics: list[Diagnostic] = []
    seen: set[tuple[int, str]] = set()
    for step in contract.behavior:
        diagnostics.extend(_unknown_parameter_diagnostics(step, known, seen))
    return diagnostics


def _unknown_parameter_diagnostics(
    step: BehaviorStep,
    known: frozenset[str],
    seen: set[tuple[int, str]],
) -> list[Diagnostic]:
    found: list[Diagnostic] = []
    for ref in sorted(step.references):
        if ref in known or (step.line, ref) in seen:
            continue
        seen.add((step.line, ref))
        found.append(
            Diagnostic(
                line=step.line,
                code=DiagnosticCode.INCONSISTENT_PROMPT,
                message=f"unknown parameter: {ref}",
            )
        )
    return found


DEFAULT_VALIDATORS: Final[tuple[ContractValidator, ...]] = (
    validate_examples_present,
    validate_known_parameters,
)
