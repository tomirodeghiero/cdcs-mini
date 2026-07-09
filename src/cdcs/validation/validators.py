"""Validators that run after the contract is parsed.

Each one is pure: signature + contract + line in, diagnostics out.
That keeps them trivial to test and free to compose.

Validation phases (mapped to PDF §7):
  * signature consistency  -> ``validate_known_parameters``
  * completeness           -> ``validate_completeness``
  * missing samples        -> ``validate_examples_present``
  * examples consistency   -> ``validate_examples_consistency``
  * callable-surface       -> ``validate_callable_surface``

Each validator is independent and order does not matter for correctness.
The orchestrator just concatenates the diagnostic streams.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Iterable
from typing import Final, Protocol

from cdcs.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs.domain.models import (
    AttributeReadSpec,
    BehaviorStep,
    CallableSpec,
    Contract,
    Example,
    ExampleKind,
    Parameter,
    Signature,
)

# DSL-level matcher keywords. Always known, regardless of host language —
# they belong to the contract grammar (``require X matches digits``).
DSL_MATCHERS: Final[frozenset[str]] = frozenset({"digits", "alpha", "alnum", "whitespace", "ascii"})

# Backwards-compatible Python-default. New code paths inject the host
# language's globals via :func:`make_known_parameters_validator`.
_PYTHON_DSL_LITERALS: Final[frozenset[str]] = frozenset({"True", "False", "None"})
KNOWN_NON_PARAMETER_NAMES: Final[frozenset[str]] = (
    frozenset(dir(builtins)) | _PYTHON_DSL_LITERALS | DSL_MATCHERS
)


class ContractValidator(Protocol):
    def __call__(
        self, *, signature: Signature, contract: Contract, function_line: int
    ) -> Iterable[Diagnostic]: ...


def make_known_parameters_validator(
    known_globals: frozenset[str],
) -> ContractValidator:
    """Bind ``validate_known_parameters`` to a host-language ``known_globals``.

    The returned closure satisfies :class:`ContractValidator` and can be
    dropped into a validator chain. Use this when assembling a chain via
    a :class:`~cdcs.language.base.LanguageAdapter`; the bare
    :func:`validate_known_parameters` keeps the Python default for
    legacy callers and tests.
    """
    known = known_globals | DSL_MATCHERS

    def _validate(
        *, signature: Signature, contract: Contract, function_line: int
    ) -> Iterable[Diagnostic]:
        _ = function_line
        full_known = signature.parameter_names | known
        diagnostics: list[Diagnostic] = []
        seen: set[tuple[int, str]] = set()
        for step in contract.behavior:
            diagnostics.extend(_unknown_parameter_diagnostics(step, full_known, seen))
        return diagnostics

    return _validate


# --- examples presence ------------------------------------------------


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


# --- signature ↔ behavior consistency ---------------------------------


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


# --- examples consistency (no contradictions) -------------------------


def validate_examples_consistency(
    *, signature: Signature, contract: Contract, function_line: int
) -> Iterable[Diagnostic]:
    """Flag examples that share an LHS call but disagree on the result.

    Two ``==`` examples with identical normalized calls but different
    expected values, or mixing ``==`` and ``raises`` on the same call,
    map to PDF §8 ``PromptCannotSatisfyTestsError``/``ContradictoryExamplesError``.
    """
    _ = signature, function_line
    diagnostics: list[Diagnostic] = []
    seen: dict[str, tuple[str, int]] = {}  # call_key -> (result_key, line)
    for example in contract.examples:
        key = _example_key(example)
        if key is None:
            continue
        call_key, result_key = key
        prior = seen.get(call_key)
        if prior is None:
            seen[call_key] = (result_key, example.line)
            continue
        if prior[0] == result_key:
            continue  # exact duplicate, not contradictory
        diagnostics.append(
            Diagnostic(
                line=example.line,
                code=DiagnosticCode.CONTRADICTORY_EXAMPLES,
                message=(f"example contradicts prior at line {prior[1]}: {example.raw!r}"),
            )
        )
    return diagnostics


def _example_key(example: Example) -> tuple[str, str] | None:
    """Normalize an example into ``(call_key, result_key)`` strings.

    Returns ``None`` when the example is unparseable — the malformed-DSL
    pass will have flagged it already and we don't want to double up.
    """
    if example.kind is ExampleKind.EQUALS:
        return _equals_example_key(example.raw)
    return _raises_example_key(example.raw)


def _equals_example_key(raw: str) -> tuple[str, str] | None:
    try:
        tree = ast.parse(raw, mode="eval")
    except SyntaxError:
        return None
    body = tree.body
    if not isinstance(body, ast.Compare):
        return None
    if len(body.ops) != 1 or not isinstance(body.ops[0], ast.Eq):
        return None
    if len(body.comparators) != 1:
        return None
    return ast.unparse(body.left), f"equals:{ast.unparse(body.comparators[0])}"


def _raises_example_key(raw: str) -> tuple[str, str] | None:
    if " raises " not in raw:
        return None
    call_part, exc_part = raw.split(" raises ", 1)
    try:
        call_tree = ast.parse(call_part.strip(), mode="eval")
    except SyntaxError:
        return None
    return ast.unparse(call_tree.body), f"raises:{exc_part.strip()}"


# --- callable surface (Calls/Reads consistency) -----------------------


# The DSL always uses ``self.`` as the receiver-prefix in calls/reads
# (PDF §4). The actual parameter name on the host function varies per
# language — Python uses ``self``, TypeScript uses ``this``. The
# validator translates the DSL keyword to the host receiver via the
# adapter's ``receiver_parameter_name``.
DSL_RECEIVER_PREFIX: Final[str] = "self."


def make_callable_surface_validator(receiver_name: str) -> ContractValidator:
    """Bind ``validate_callable_surface`` to a host receiver name.

    Returns a :class:`ContractValidator` closure that enforces the
    Calls/Reads consistency rules — the DSL keyword ``self.X`` resolves
    to ``receiver_name`` when checking the function's first parameter.
    """

    def _validate(
        *, signature: Signature, contract: Contract, function_line: int
    ) -> Iterable[Diagnostic]:
        _ = function_line
        diagnostics: list[Diagnostic] = []
        has_receiver = _has_receiver_parameter(signature, receiver_name)
        seen: dict[str, int] = {}
        for spec in contract.calls:
            diagnostics.extend(_check_callable_spec(spec, has_receiver, seen, receiver_name))
        diagnostics.extend(_check_attribute_specs(contract.reads, has_receiver, receiver_name))
        return diagnostics

    return _validate


def validate_callable_surface(
    *, signature: Signature, contract: Contract, function_line: int
) -> Iterable[Diagnostic]:
    """Backwards-compatible Python-default callable-surface validator.

    New language adapters should use :func:`make_callable_surface_validator`
    via :func:`default_validators` so the receiver name is host-aware.

    Rules enforced here (the syntactic well-formedness happens earlier
    in the DSL parser):

    * No duplicate ``qualified_name`` in ``Calls:``.
    * ``self.X`` only allowed if the function declares a receiver.
    * Same rule for ``Reads:``.
    """
    return make_callable_surface_validator("self")(
        signature=signature, contract=contract, function_line=function_line
    )


def _has_receiver_parameter(signature: Signature, receiver_name: str) -> bool:
    return bool(signature.parameters) and signature.parameters[0].name == receiver_name


def _check_callable_spec(
    spec: CallableSpec,
    has_receiver: bool,
    seen: dict[str, int],
    receiver_name: str,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if spec.qualified_name in seen:
        diagnostics.append(
            Diagnostic(
                line=spec.line,
                code=DiagnosticCode.INCONSISTENT_CALLABLE_SURFACE,
                message=(
                    f"duplicate callable declaration: {spec.qualified_name!r} "
                    f"(first at line {seen[spec.qualified_name]})"
                ),
            )
        )
    else:
        seen[spec.qualified_name] = spec.line
    if spec.qualified_name.startswith(DSL_RECEIVER_PREFIX) and not has_receiver:
        diagnostics.append(
            Diagnostic(
                line=spec.line,
                code=DiagnosticCode.INCONSISTENT_CALLABLE_SURFACE,
                message=(
                    f"self-qualified callee {spec.qualified_name!r} "
                    f"but function has no {receiver_name!r} parameter"
                ),
            )
        )
    return diagnostics


def _check_attribute_specs(
    reads: tuple[AttributeReadSpec, ...],
    has_receiver: bool,
    receiver_name: str,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    seen: dict[str, int] = {}
    for spec in reads:
        if spec.qualified_name in seen:
            diagnostics.append(
                Diagnostic(
                    line=spec.line,
                    code=DiagnosticCode.INCONSISTENT_CALLABLE_SURFACE,
                    message=(
                        f"duplicate attribute declaration: {spec.qualified_name!r} "
                        f"(first at line {seen[spec.qualified_name]})"
                    ),
                )
            )
        else:
            seen[spec.qualified_name] = spec.line
        if spec.qualified_name.startswith(DSL_RECEIVER_PREFIX) and not has_receiver:
            diagnostics.append(
                Diagnostic(
                    line=spec.line,
                    code=DiagnosticCode.INCONSISTENT_CALLABLE_SURFACE,
                    message=(
                        f"self-qualified attribute {spec.qualified_name!r} "
                        f"but function has no {receiver_name!r} parameter"
                    ),
                )
            )
    return diagnostics


# --- completeness heuristic -------------------------------------------


# Container types where "empty" is a meaningful, often-forgotten edge case.
# Strings are *not* in this list: too many real functions precondition a
# non-empty string via `require`, so flagging them produces too much noise.
_CONTAINER_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("list", "[]"),
    ("List", "[]"),
    ("Sequence", "[]"),
    ("Iterable", "[]"),
    ("tuple", "()"),
    ("Tuple", "()"),
    ("set", "set()"),
    ("frozenset", "frozenset()"),
    ("dict", "{}"),
    ("Dict", "{}"),
    ("Mapping", "{}"),
)


def validate_completeness(
    *, signature: Signature, contract: Contract, function_line: int
) -> Iterable[Diagnostic]:
    """Heuristic: flag container parameters whose empty case isn't exemplified.

    Maps to PDF §8 ``IncompletePromptError``. The check is intentionally
    conservative: only emits when the *type* hints at a container and
    *no* example uses an empty literal of that flavor. Misses are
    acceptable — false positives are not — because the synthesizer will
    still fail loudly downstream if behavior is genuinely under-specified.
    """
    if not contract.examples:
        # MISSING_SAMPLES already covers the empty case
        return ()
    diagnostics: list[Diagnostic] = []
    examples_text = " ".join(example.raw for example in contract.examples)
    for parameter in signature.parameters:
        diagnostic = _completeness_diagnostic(parameter, examples_text, function_line)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return diagnostics


def _completeness_diagnostic(
    parameter: Parameter, examples_text: str, function_line: int
) -> Diagnostic | None:
    annotation = parameter.annotation
    if annotation is None:
        return None
    for type_hint, empty_literal in _CONTAINER_HINTS:
        if not _annotation_mentions(annotation, type_hint):
            continue
        if empty_literal in examples_text:
            return None
        return Diagnostic(
            line=function_line,
            code=DiagnosticCode.INCOMPLETE_PROMPT,
            message=(f"behavior for empty {type_hint} parameter {parameter.name!r} is unspecified"),
        )
    return None


def _annotation_mentions(annotation: str, type_hint: str) -> bool:
    # Token-aware match: avoid catching "List" inside "ListResponse"
    try:
        tree = ast.parse(annotation, mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == type_hint:
            return True
        if isinstance(node, ast.Attribute) and node.attr == type_hint:
            return True
    return False


# --- ordered chain -----------------------------------------------------


DEFAULT_VALIDATORS: Final[tuple[ContractValidator, ...]] = (
    validate_examples_present,
    validate_known_parameters,
    validate_examples_consistency,
    validate_callable_surface,
    validate_completeness,
)


def default_validators(
    known_globals: frozenset[str],
    *,
    receiver_name: str = "self",
) -> tuple[ContractValidator, ...]:
    """Assemble the default validator chain bound to a language's globals.

    The shape and order of the chain stays identical to
    :data:`DEFAULT_VALIDATORS`. Two validators are bound to host-language
    facts: ``validate_known_parameters`` swaps its Python-builtin set
    for the adapter's globals, and ``validate_callable_surface`` swaps
    its ``self`` receiver for the adapter's
    :attr:`~cdcs.language.base.LanguageAdapter.receiver_parameter_name`
    (``"this"`` for TypeScript). Callers that don't care about language
    can keep using ``DEFAULT_VALIDATORS``.
    """
    return (
        validate_examples_present,
        make_known_parameters_validator(known_globals),
        validate_examples_consistency,
        make_callable_surface_validator(receiver_name),
        validate_completeness,
    )
