"""Parses the ``@generate`` DSL.

Line-oriented because diagnostics need accurate line numbers and the
spec forbids regex over Python source. Sub-expressions go back through
``ast`` to pick up identifier references.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, NamedTuple

from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import (
    BehaviorKind,
    BehaviorStep,
    Contract,
    Example,
    ExampleKind,
)

KNOWN_SECTIONS: Final[frozenset[str]] = frozenset({"behavior", "examples", "constraints"})
REQUIRE_PREFIX: Final[str] = "require "
RETURN_PREFIX: Final[str] = "return "
RAISES_KEYWORD: Final[str] = " raises "
EQUALS_OP: Final[str] = "=="


@dataclass(frozen=True, slots=True)
class DSLParseResult:
    contract: Contract
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    line: int

Diagnostics = tuple[Diagnostic, ...]
SectionLines = dict[str, list[_Line]]


class _SplitResult(NamedTuple):
    sections: SectionLines
    diagnostics: Diagnostics


class _BehaviorLineResult(NamedTuple):
    step: BehaviorStep | None
    diagnostic: Diagnostic | None


class _ExampleLineResult(NamedTuple):
    example: Example | None
    diagnostic: Diagnostic | None


class _BehaviorBatch(NamedTuple):
    steps: tuple[BehaviorStep, ...]
    diagnostics: Diagnostics


class _ExampleBatch(NamedTuple):
    examples: tuple[Example, ...]
    diagnostics: Diagnostics


class DSLParser:
    def parse(self, body: str, *, base_line: int) -> DSLParseResult:
        split = _split_sections(body, base_line=base_line)
        behavior = _parse_behavior(split.sections.get("behavior", []))
        examples = _parse_examples(split.sections.get("examples", []))
        constraints = tuple(item.text for item in split.sections.get("constraints", []))

        return DSLParseResult(
            contract=Contract(
                behavior=behavior.steps,
                examples=examples.examples,
                constraints=constraints,
                has_examples_section="examples" in split.sections,
            ),
            diagnostics=(*split.diagnostics, *behavior.diagnostics, *examples.diagnostics),
        )


def _split_sections(body: str, *, base_line: int) -> _SplitResult:
    sections: SectionLines = {}
    diagnostics: list[Diagnostic] = []
    current: str | None = None
    for offset, raw_line in enumerate(body.splitlines()):
        stripped = raw_line.strip()
        if not stripped:
            continue
        absolute = base_line + offset
        header = _match_section_header(stripped)
        if header is not None:
            current = _enter_section(header, absolute, sections, diagnostics)
        else:
            _record_line(stripped, absolute, current, sections, diagnostics)
    return _SplitResult(sections=sections, diagnostics=tuple(diagnostics))


def _enter_section(
    header: str,
    absolute: int,
    sections: SectionLines,
    diagnostics: list[Diagnostic],
) -> str | None:
    if header not in KNOWN_SECTIONS:
        diagnostics.append(_malformed(absolute, f"unknown section: {header}"))
        return None
    sections.setdefault(header, [])
    return header


def _record_line(
    stripped: str,
    absolute: int,
    current: str | None,
    sections: SectionLines,
    diagnostics: list[Diagnostic],
) -> None:
    if current is None:
        diagnostics.append(
            _malformed(absolute, f"content outside any section: {stripped!r}")
        )
        return
    sections[current].append(_Line(text=stripped, line=absolute))


def _match_section_header(stripped: str) -> str | None:
    if not stripped.endswith(":"):
        return None
    candidate = stripped[:-1].strip()
    if not _is_valid_section_name(candidate):
        return None
    return candidate.lower()


def _is_valid_section_name(candidate: str) -> bool:
    return bool(candidate) and not any(ch.isspace() for ch in candidate)


def _parse_behavior(lines: list[_Line]) -> _BehaviorBatch:
    steps: list[BehaviorStep] = []
    diagnostics: list[Diagnostic] = []
    for line in lines:
        result = _parse_behavior_line(line)
        if result.step is not None:
            steps.append(result.step)
        if result.diagnostic is not None:
            diagnostics.append(result.diagnostic)
    return _BehaviorBatch(steps=tuple(steps), diagnostics=tuple(diagnostics))


def _parse_examples(lines: list[_Line]) -> _ExampleBatch:
    examples: list[Example] = []
    diagnostics: list[Diagnostic] = []
    for line in lines:
        result = _parse_example_line(line)
        if result.example is not None:
            examples.append(result.example)
        if result.diagnostic is not None:
            diagnostics.append(result.diagnostic)
    return _ExampleBatch(examples=tuple(examples), diagnostics=tuple(diagnostics))


Matcher = Callable[[str], bool]
LineParser = Callable[[str, "_Line"], _BehaviorLineResult]


@dataclass(frozen=True, slots=True)
class _BehaviorRule:
    # One row of the dispatch table: predicate + handler
    matches: Matcher
    parse: LineParser


def _is_require(text: str) -> bool:
    return text == "require" or text.startswith(REQUIRE_PREFIX)


def _is_return(text: str) -> bool:
    return text == "return" or text.startswith(RETURN_PREFIX)


def _always(_text: str) -> bool:
    return True


# Tried top-to-bottom. Last row matches anything so the loop always finds a hit.
# Add a new behavior kind by inserting a row above the catch-all
BEHAVIOR_RULES: Final[tuple[_BehaviorRule, ...]] = (
    _BehaviorRule(matches=_is_require, parse=lambda t, line: _parse_require(t, line)),
    _BehaviorRule(matches=_is_return, parse=lambda t, line: _parse_return(t, line)),
    _BehaviorRule(matches=_always, parse=lambda t, line: _parse_operation(t, line)),
)


def _parse_behavior_line(line: _Line) -> _BehaviorLineResult:
    for rule in BEHAVIOR_RULES:
        if rule.matches(line.text):
            return rule.parse(line.text, line)
    raise AssertionError("unreachable: the last rule is a catch-all")


def _parse_require(text: str, line: _Line) -> _BehaviorLineResult:
    payload = "" if text == "require" else text[len(REQUIRE_PREFIX) :].strip()
    if not payload:
        return _behavior_error(line, "empty require clause")
    references = _extract_require_references(payload)
    if references is None:
        return _behavior_error(line, f"unparseable require clause: {payload!r}")
    return _behavior_ok(BehaviorKind.REQUIRE, text, line, references)


def _parse_return(text: str, line: _Line) -> _BehaviorLineResult:
    payload = "" if text == "return" else text[len(RETURN_PREFIX) :].strip()
    if not payload:
        return _behavior_ok(BehaviorKind.RETURN, text, line, frozenset())
    references = _extract_names(payload)
    if references is None:
        return _behavior_error(line, f"unparseable return expression: {payload!r}")
    return _behavior_ok(BehaviorKind.RETURN, text, line, references)


def _parse_operation(text: str, line: _Line) -> _BehaviorLineResult:
    references = _extract_names(text)
    if references is None:
        return _behavior_error(line, f"unparseable behavior expression: {text!r}")
    return _behavior_ok(BehaviorKind.OPERATION, text, line, references)


def _parse_example_line(line: _Line) -> _ExampleLineResult:
    text = line.text
    if RAISES_KEYWORD in text:
        call_part, _ = text.split(RAISES_KEYWORD, 1)
        kind = ExampleKind.RAISES
    elif EQUALS_OP in text:
        call_part, _ = text.split(EQUALS_OP, 1)
        kind = ExampleKind.EQUALS
    else:
        return _example_error(line, f"example must use '==' or 'raises': {text!r}")

    call_target = _extract_call_target(call_part.strip())
    if call_target is None:
        return _example_error(line, f"example must call the target function: {text!r}")
    return _ExampleLineResult(
        example=Example(kind=kind, raw=text, line=line.line, call_target=call_target),
        diagnostic=None,
    )


def _behavior_ok(
    kind: BehaviorKind, text: str, line: _Line, references: frozenset[str]
) -> _BehaviorLineResult:
    return _BehaviorLineResult(step=_step(kind, text, line, references), diagnostic=None)


def _behavior_error(line: _Line, message: str) -> _BehaviorLineResult:
    return _BehaviorLineResult(step=None, diagnostic=_malformed(line.line, message))


def _example_error(line: _Line, message: str) -> _ExampleLineResult:
    return _ExampleLineResult(example=None, diagnostic=_invalid_example(line.line, message))


def _extract_require_references(payload: str) -> frozenset[str] | None:
    # Two shapes here: `<id> matches <id>` (custom matcher) or a plain Python expression
    parts = payload.split()
    if len(parts) >= 3 and parts[1] == "matches":
        return frozenset({parts[0]})
    return _extract_names(payload)


def _extract_names(expression: str) -> frozenset[str] | None:
    tree = _try_parse_eval(expression)
    if tree is None:
        return None
    # Skip names that sit in Call.func — those are operations (strip, int, ...) not parameters
    return _names_excluding(tree, _call_func_node_ids(tree))


def _try_parse_eval(expression: str) -> ast.Expression | None:
    try:
        return ast.parse(expression, mode="eval")
    except SyntaxError:
        return None


def _call_func_node_ids(tree: ast.AST) -> set[int]:
    return {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _names_excluding(tree: ast.AST, exclude_ids: set[int]) -> frozenset[str]:
    return frozenset(
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and id(node) not in exclude_ids
    )


def _extract_call_target(call_expression: str) -> str | None:
    try:
        tree = ast.parse(call_expression, mode="eval")
    except SyntaxError:
        return None
    call = tree.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    return call.func.id


def _step(
    kind: BehaviorKind, text: str, line: _Line, references: frozenset[str]
) -> BehaviorStep:
    return BehaviorStep(kind=kind, raw=text, line=line.line, references=references)


def _malformed(line: int, message: str) -> Diagnostic:
    return Diagnostic(line=line, code=DiagnosticCode.MALFORMED_DSL, message=message)


def _invalid_example(line: int, message: str) -> Diagnostic:
    return Diagnostic(line=line, code=DiagnosticCode.INVALID_EXAMPLE, message=message)
