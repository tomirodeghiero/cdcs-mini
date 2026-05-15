"""Parses the ``@generate`` DSL.

Line-oriented because diagnostics need accurate line numbers and the
spec forbids regex over Python source. Sub-expressions go back through
``ast`` to pick up identifier references.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import ClassVar, NamedTuple

from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import (
    BehaviorKind,
    BehaviorStep,
    Contract,
    Example,
    ExampleKind,
)


@dataclass(frozen=True, slots=True)
class DSLParseResult:
    """Public result type returned by ``DSLParser.parse()``."""

    contract: Contract
    diagnostics: tuple[Diagnostic, ...]


class DSLParser:
    """Stateless and reusable. ``parse()`` carries no state between calls —
    the splitting pass runs inside a transient ``_Splitter`` that lives only
    for that call. Instances are safe to share across calls and threads;
    there is no "ready vs spent" state to mismanage.

    Everything else the parser needs (DSL syntax constants, internal DTOs,
    helpers) lives under this class. Nothing leaks to module scope.
    """

    # --- DSL syntax ----------------------------------------------------

    KNOWN_SECTIONS: ClassVar[frozenset[str]] = frozenset(
        {"behavior", "examples", "constraints"}
    )
    REQUIRE_PREFIX: ClassVar[str] = "require "
    RETURN_PREFIX: ClassVar[str] = "return "
    RAISES_KEYWORD: ClassVar[str] = " raises "
    EQUALS_OP: ClassVar[str] = "=="

    # --- internal types ------------------------------------------------

    @dataclass(frozen=True, slots=True)
    class _Line:
        text: str
        line: int

    class _SplitResult(NamedTuple):
        sections: dict[str, list[DSLParser._Line]]
        diagnostics: tuple[Diagnostic, ...]

    class _BehaviorLineResult(NamedTuple):
        step: BehaviorStep | None
        diagnostic: Diagnostic | None

    class _ExampleLineResult(NamedTuple):
        example: Example | None
        diagnostic: Diagnostic | None

    class _BehaviorBatch(NamedTuple):
        steps: tuple[BehaviorStep, ...]
        diagnostics: tuple[Diagnostic, ...]

    class _ExampleBatch(NamedTuple):
        examples: tuple[Example, ...]
        diagnostics: tuple[Diagnostic, ...]

    # --- section splitting (stateful, one-shot) -----------------------

    class _Splitter:
        """Owns the mutable state for the splitting pass. Created fresh
        per ``parse()`` call and discarded — callers never see it, so the
        instance never reaches a half-consumed state.

        Self-contained: builds its own diagnostics, holds its own
        section-header parsing. Does not call back into ``DSLParser``.
        """

        def __init__(self, body: str, base_line: int) -> None:
            self._body = body
            self._base_line = base_line
            self._sections: dict[str, list[DSLParser._Line]] = {}
            self._diagnostics: list[Diagnostic] = []
            self._current: str | None = None

        def run(self) -> DSLParser._SplitResult:
            for offset, raw_line in enumerate(self._body.splitlines()):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                self._process(stripped, self._base_line + offset)
            return DSLParser._SplitResult(
                sections=self._sections,
                diagnostics=tuple(self._diagnostics),
            )

        def _process(self, stripped: str, absolute: int) -> None:
            header = DSLParser._Splitter._match_section_header(stripped)
            if header is not None:
                self._enter_section(header, absolute)
            else:
                self._record_line(stripped, absolute)

        def _enter_section(self, header: str, absolute: int) -> None:
            if header not in DSLParser.KNOWN_SECTIONS:
                self._diagnostics.append(
                    Diagnostic(
                        line=absolute,
                        code=DiagnosticCode.MALFORMED_DSL,
                        message=f"unknown section: {header}",
                    )
                )
                self._current = None
                return
            self._sections.setdefault(header, [])
            self._current = header

        def _record_line(self, stripped: str, absolute: int) -> None:
            if self._current is None:
                self._diagnostics.append(
                    Diagnostic(
                        line=absolute,
                        code=DiagnosticCode.MALFORMED_DSL,
                        message=f"content outside any section: {stripped!r}",
                    )
                )
                return
            self._sections[self._current].append(
                DSLParser._Line(text=stripped, line=absolute)
            )

        @staticmethod
        def _match_section_header(stripped: str) -> str | None:
            if not stripped.endswith(":"):
                return None
            candidate = stripped[:-1].strip()
            if not DSLParser._Splitter._is_valid_section_name(candidate):
                return None
            return candidate.lower()

        @staticmethod
        def _is_valid_section_name(candidate: str) -> bool:
            return bool(candidate) and not any(ch.isspace() for ch in candidate)

    # --- main entry ----------------------------------------------------

    def parse(self, body: str, *, base_line: int) -> DSLParseResult:
        split = DSLParser._Splitter(body, base_line).run()
        behavior = DSLParser._parse_behavior(split.sections.get("behavior", []))
        examples = DSLParser._parse_examples(split.sections.get("examples", []))
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

    # --- behavior ------------------------------------------------------

    @staticmethod
    def _parse_behavior(lines: list[DSLParser._Line]) -> DSLParser._BehaviorBatch:
        steps: list[BehaviorStep] = []
        diagnostics: list[Diagnostic] = []
        for line in lines:
            result = DSLParser._parse_behavior_line(line)
            if result.step is not None:
                steps.append(result.step)
            if result.diagnostic is not None:
                diagnostics.append(result.diagnostic)
        return DSLParser._BehaviorBatch(
            steps=tuple(steps), diagnostics=tuple(diagnostics)
        )

    @staticmethod
    def _parse_behavior_line(line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        text = line.text
        if DSLParser._is_require(text):
            return DSLParser._parse_require(text, line)
        if DSLParser._is_return(text):
            return DSLParser._parse_return(text, line)
        return DSLParser._parse_operation(text, line)

    @staticmethod
    def _is_require(text: str) -> bool:
        return text == "require" or text.startswith(DSLParser.REQUIRE_PREFIX)

    @staticmethod
    def _is_return(text: str) -> bool:
        return text == "return" or text.startswith(DSLParser.RETURN_PREFIX)

    @staticmethod
    def _parse_require(text: str, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        payload = (
            "" if text == "require" else text[len(DSLParser.REQUIRE_PREFIX):].strip()
        )
        if not payload:
            return DSLParser._behavior_error(line, "empty require clause")
        references = DSLParser._extract_require_references(payload)
        if references is None:
            return DSLParser._behavior_error(
                line, f"unparseable require clause: {payload!r}"
            )
        return DSLParser._behavior_ok(BehaviorKind.REQUIRE, text, line, references)

    @staticmethod
    def _parse_return(text: str, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        payload = (
            "" if text == "return" else text[len(DSLParser.RETURN_PREFIX):].strip()
        )
        if not payload:
            return DSLParser._behavior_ok(BehaviorKind.RETURN, text, line, frozenset())
        references = DSLParser._extract_names(payload)
        if references is None:
            return DSLParser._behavior_error(
                line, f"unparseable return expression: {payload!r}"
            )
        return DSLParser._behavior_ok(BehaviorKind.RETURN, text, line, references)

    @staticmethod
    def _parse_operation(text: str, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        references = DSLParser._extract_names(text)
        if references is None:
            return DSLParser._behavior_error(
                line, f"unparseable behavior expression: {text!r}"
            )
        return DSLParser._behavior_ok(BehaviorKind.OPERATION, text, line, references)

    # --- examples ------------------------------------------------------

    @staticmethod
    def _parse_examples(lines: list[DSLParser._Line]) -> DSLParser._ExampleBatch:
        examples: list[Example] = []
        diagnostics: list[Diagnostic] = []
        for line in lines:
            result = DSLParser._parse_example_line(line)
            if result.example is not None:
                examples.append(result.example)
            if result.diagnostic is not None:
                diagnostics.append(result.diagnostic)
        return DSLParser._ExampleBatch(
            examples=tuple(examples), diagnostics=tuple(diagnostics)
        )

    @staticmethod
    def _parse_example_line(line: DSLParser._Line) -> DSLParser._ExampleLineResult:
        text = line.text
        if DSLParser.RAISES_KEYWORD in text:
            call_part, _ = text.split(DSLParser.RAISES_KEYWORD, 1)
            kind = ExampleKind.RAISES
        elif DSLParser.EQUALS_OP in text:
            call_part, _ = text.split(DSLParser.EQUALS_OP, 1)
            kind = ExampleKind.EQUALS
        else:
            return DSLParser._example_error(
                line, f"example must use '==' or 'raises': {text!r}"
            )
        call_target = DSLParser._extract_call_target(call_part.strip())
        if call_target is None:
            return DSLParser._example_error(
                line, f"example must call the target function: {text!r}"
            )
        return DSLParser._ExampleLineResult(
            example=Example(kind=kind, raw=text, line=line.line, call_target=call_target),
            diagnostic=None,
        )

    # --- result constructors ------------------------------------------

    @staticmethod
    def _behavior_ok(
        kind: BehaviorKind,
        text: str,
        line: DSLParser._Line,
        references: frozenset[str],
    ) -> DSLParser._BehaviorLineResult:
        return DSLParser._BehaviorLineResult(
            step=BehaviorStep(kind=kind, raw=text, line=line.line, references=references),
            diagnostic=None,
        )

    @staticmethod
    def _behavior_error(line: DSLParser._Line, message: str) -> DSLParser._BehaviorLineResult:
        return DSLParser._BehaviorLineResult(
            step=None, diagnostic=DSLParser._malformed(line.line, message)
        )

    @staticmethod
    def _example_error(line: DSLParser._Line, message: str) -> DSLParser._ExampleLineResult:
        return DSLParser._ExampleLineResult(
            example=None, diagnostic=DSLParser._invalid_example(line.line, message)
        )

    # --- reference extraction -----------------------------------------

    @staticmethod
    def _extract_require_references(payload: str) -> frozenset[str] | None:
        # Two shapes: `<id> matches <id>` (custom matcher) or plain Python expression
        parts = payload.split()
        if len(parts) >= 3 and parts[1] == "matches":
            return frozenset({parts[0]})
        return DSLParser._extract_names(payload)

    @staticmethod
    def _extract_names(expression: str) -> frozenset[str] | None:
        tree = DSLParser._try_parse_eval(expression)
        if tree is None:
            return None
        # Skip names in Call.func — operations (strip, int, ...) not parameters
        return DSLParser._names_excluding(tree, DSLParser._call_func_node_ids(tree))

    @staticmethod
    def _try_parse_eval(expression: str) -> ast.Expression | None:
        try:
            return ast.parse(expression, mode="eval")
        except SyntaxError:
            return None

    @staticmethod
    def _call_func_node_ids(tree: ast.AST) -> set[int]:
        return {
            id(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

    @staticmethod
    def _names_excluding(tree: ast.AST, exclude_ids: set[int]) -> frozenset[str]:
        return frozenset(
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and id(node) not in exclude_ids
        )

    @staticmethod
    def _extract_call_target(call_expression: str) -> str | None:
        try:
            tree = ast.parse(call_expression, mode="eval")
        except SyntaxError:
            return None
        call = tree.body
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            return None
        return call.func.id

    # --- diagnostic constructors --------------------------------------

    @staticmethod
    def _malformed(line: int, message: str) -> Diagnostic:
        return Diagnostic(line=line, code=DiagnosticCode.MALFORMED_DSL, message=message)

    @staticmethod
    def _invalid_example(line: int, message: str) -> Diagnostic:
        return Diagnostic(line=line, code=DiagnosticCode.INVALID_EXAMPLE, message=message)
