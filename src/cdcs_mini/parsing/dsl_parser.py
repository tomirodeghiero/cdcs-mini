"""Parses the ``@generate`` DSL.

Line-oriented because diagnostics need accurate line numbers and the
spec forbids regex over Python source. Sub-expressions go back through
``ast`` to pick up identifier references.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

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


class DSLParser:
    def parse(self, body: str, *, base_line: int) -> DSLParseResult:
        sections, section_diagnostics = _split_sections(body, base_line=base_line)

        behavior, behavior_diagnostics = _parse_behavior(sections.get("behavior", []))
        examples, example_diagnostics = _parse_examples(sections.get("examples", []))
        constraints = tuple(item.text for item in sections.get("constraints", []))

        return DSLParseResult(
            contract=Contract(
                behavior=behavior,
                examples=examples,
                constraints=constraints,
                has_examples_section="examples" in sections,
            ),
            diagnostics=(*section_diagnostics, *behavior_diagnostics, *example_diagnostics),
        )


def _split_sections(
    body: str, *, base_line: int
) -> tuple[dict[str, list[_Line]], tuple[Diagnostic, ...]]:
    sections: dict[str, list[_Line]] = {}
    diagnostics: list[Diagnostic] = []
    current: str | None = None

    for offset, raw_line in enumerate(body.splitlines()):
        absolute = base_line + offset
        stripped = raw_line.strip()
        if not stripped:
            continue

        header = _match_section_header(stripped)
        if header is not None:
            if header not in KNOWN_SECTIONS:
                diagnostics.append(_malformed(absolute, f"unknown section: {header}"))
                current = None
                continue
            sections.setdefault(header, [])
            current = header
            continue

        if current is None:
            diagnostics.append(
                _malformed(absolute, f"content outside any section: {stripped!r}")
            )
            continue

        sections[current].append(_Line(text=stripped, line=absolute))

    return sections, tuple(diagnostics)


def _match_section_header(stripped: str) -> str | None:
    if not stripped.endswith(":"):
        return None
    candidate = stripped[:-1].strip()
    if not candidate or any(ch.isspace() for ch in candidate):
        return None
    return candidate.lower()


def _parse_behavior(
    lines: list[_Line],
) -> tuple[tuple[BehaviorStep, ...], tuple[Diagnostic, ...]]:
    steps: list[BehaviorStep] = []
    diagnostics: list[Diagnostic] = []
    for line in lines:
        step, diagnostic = _parse_behavior_line(line)
        if step is not None:
            steps.append(step)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return tuple(steps), tuple(diagnostics)


def _parse_examples(
    lines: list[_Line],
) -> tuple[tuple[Example, ...], tuple[Diagnostic, ...]]:
    examples: list[Example] = []
    diagnostics: list[Diagnostic] = []
    for line in lines:
        example, diagnostic = _parse_example_line(line)
        if example is not None:
            examples.append(example)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
    return tuple(examples), tuple(diagnostics)


Matcher = Callable[[str], bool]
LineParser = Callable[[str, "_Line"], tuple[BehaviorStep | None, Diagnostic | None]]


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


def _parse_behavior_line(line: _Line) -> tuple[BehaviorStep | None, Diagnostic | None]:
    for rule in BEHAVIOR_RULES:
        if rule.matches(line.text):
            return rule.parse(line.text, line)
    raise AssertionError("unreachable: the last rule is a catch-all")


def _parse_require(text: str, line: _Line) -> tuple[BehaviorStep | None, Diagnostic | None]:
    payload = "" if text == "require" else text[len(REQUIRE_PREFIX) :].strip()
    if not payload:
        return None, _malformed(line.line, "empty require clause")
    references = _extract_require_references(payload)
    if references is None:
        return None, _malformed(line.line, f"unparseable require clause: {payload!r}")
    return _step(BehaviorKind.REQUIRE, text, line, references), None


def _parse_return(text: str, line: _Line) -> tuple[BehaviorStep | None, Diagnostic | None]:
    payload = "" if text == "return" else text[len(RETURN_PREFIX) :].strip()
    if not payload:
        return _step(BehaviorKind.RETURN, text, line, frozenset()), None
    references = _extract_names(payload)
    if references is None:
        return None, _malformed(line.line, f"unparseable return expression: {payload!r}")
    return _step(BehaviorKind.RETURN, text, line, references), None


def _parse_operation(text: str, line: _Line) -> tuple[BehaviorStep | None, Diagnostic | None]:
    references = _extract_names(text)
    if references is None:
        return None, _malformed(line.line, f"unparseable behavior expression: {text!r}")
    return _step(BehaviorKind.OPERATION, text, line, references), None


def _parse_example_line(line: _Line) -> tuple[Example | None, Diagnostic | None]:
    text = line.text
    if RAISES_KEYWORD in text:
        call_part, _ = text.split(RAISES_KEYWORD, 1)
        kind = ExampleKind.RAISES
    elif EQUALS_OP in text:
        call_part, _ = text.split(EQUALS_OP, 1)
        kind = ExampleKind.EQUALS
    else:
        return None, _invalid_example(line.line, f"example must use '==' or 'raises': {text!r}")

    call_target = _extract_call_target(call_part.strip())
    if call_target is None:
        return None, _invalid_example(
            line.line, f"example must call the target function: {text!r}"
        )
    return Example(kind=kind, raw=text, line=line.line, call_target=call_target), None


def _extract_require_references(payload: str) -> frozenset[str] | None:
    # Two shapes here: `<id> matches <id>` (custom matcher) or a plain Python expression
    parts = payload.split()
    if len(parts) >= 3 and parts[1] == "matches":
        return frozenset({parts[0]})
    return _extract_names(payload)


def _extract_names(expression: str) -> frozenset[str] | None:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None
    # Skip names that sit in Call.func — those are operations (strip, int, ...) not parameters
    call_func_ids = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return frozenset(
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and id(node) not in call_func_ids
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
