"""Parses the ``@generate`` DSL.

Line-oriented because diagnostics need accurate line numbers and the
spec forbids regex over Python source. Expression validation (the inside
of ``require``, ``return``, examples and ``calls:`` signatures) is
delegated to an :class:`~cdcs.language.base.ExpressionParser` —
that's the seam through which a non-Python language plugs into the same
DSL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, NamedTuple

from cdcs.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs.domain.models import (
    AttributeReadSpec,
    BehaviorKind,
    BehaviorStep,
    CallableSpec,
    Contract,
    Example,
    ExampleKind,
)
from cdcs.language.base import ExpressionParser
from cdcs.language.python.expression_parser import PythonExpressionParser


@dataclass(frozen=True, slots=True)
class DSLParseResult:
    """Public result type returned by ``DSLParser.parse()``."""

    contract: Contract
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class DSLParser:
    """Stateless and reusable.

    The DSL skeleton (section headers, ``require``/``return`` keywords,
    ``==`` / ``raises``) is identical across languages. The bits that
    are language-specific — "is this string a valid expression?", "what
    identifiers does it reference?" — live behind ``expression_parser``.

    Instances are safe to share across calls and threads; there is no
    "ready vs spent" state to mismanage.
    """

    expression_parser: ExpressionParser = field(default_factory=PythonExpressionParser)

    # --- DSL syntax ----------------------------------------------------

    KNOWN_SECTIONS: ClassVar[frozenset[str]] = frozenset(
        {"behavior", "examples", "constraints", "calls", "reads"}
    )
    REQUIRE_PREFIX: ClassVar[str] = "require "
    RETURN_PREFIX: ClassVar[str] = "return "
    RAISES_KEYWORD: ClassVar[str] = " raises "
    EQUALS_OP: ClassVar[str] = "=="
    RETURN_ARROW: ClassVar[str] = "->"

    # Sentinel for "return annotation present but invalid" so we can
    # distinguish it from "no return annotation" (None).
    _RETURN_PARSE_FAILED: ClassVar[str] = "\x00__return_parse_failed__\x00"

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

    class _CallableLineResult(NamedTuple):
        spec: CallableSpec | None
        diagnostic: Diagnostic | None

    class _AttributeLineResult(NamedTuple):
        spec: AttributeReadSpec | None
        diagnostic: Diagnostic | None

    class _CallsBatch(NamedTuple):
        specs: tuple[CallableSpec, ...]
        diagnostics: tuple[Diagnostic, ...]

    class _ReadsBatch(NamedTuple):
        specs: tuple[AttributeReadSpec, ...]
        diagnostics: tuple[Diagnostic, ...]

    # --- section splitting (stateful, one-shot) -----------------------

    class _Splitter:
        """Owns the mutable state for the splitting pass. Created fresh
        per ``parse()`` call and discarded — callers never see it, so the
        instance never reaches a half-consumed state.
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
            self._sections[self._current].append(DSLParser._Line(text=stripped, line=absolute))

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
        behavior = self._parse_behavior(split.sections.get("behavior", []))
        examples = self._parse_examples(split.sections.get("examples", []))
        calls = self._parse_calls(split.sections.get("calls", []))
        reads = self._parse_reads(split.sections.get("reads", []))
        constraints = tuple(item.text for item in split.sections.get("constraints", []))
        return DSLParseResult(
            contract=Contract(
                behavior=behavior.steps,
                examples=examples.examples,
                constraints=constraints,
                calls=calls.specs,
                reads=reads.specs,
                has_examples_section="examples" in split.sections,
            ),
            diagnostics=(
                *split.diagnostics,
                *behavior.diagnostics,
                *examples.diagnostics,
                *calls.diagnostics,
                *reads.diagnostics,
            ),
        )

    # --- behavior ------------------------------------------------------

    def _parse_behavior(self, lines: list[DSLParser._Line]) -> DSLParser._BehaviorBatch:
        steps: list[BehaviorStep] = []
        diagnostics: list[Diagnostic] = []
        for line in lines:
            result = self._parse_behavior_line(line)
            if result.step is not None:
                steps.append(result.step)
            if result.diagnostic is not None:
                diagnostics.append(result.diagnostic)
        return DSLParser._BehaviorBatch(steps=tuple(steps), diagnostics=tuple(diagnostics))

    def _parse_behavior_line(self, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        text = line.text
        if DSLParser._is_require(text):
            return self._parse_require(text, line)
        if DSLParser._is_return(text):
            return self._parse_return(text, line)
        return self._parse_operation(text, line)

    @staticmethod
    def _is_require(text: str) -> bool:
        return text == "require" or text.startswith(DSLParser.REQUIRE_PREFIX)

    @staticmethod
    def _is_return(text: str) -> bool:
        return text == "return" or text.startswith(DSLParser.RETURN_PREFIX)

    def _parse_require(self, text: str, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        payload = "" if text == "require" else text[len(DSLParser.REQUIRE_PREFIX) :].strip()
        if not payload:
            return DSLParser._behavior_error(line, "empty require clause")
        references = self._extract_require_references(payload)
        if references is None:
            return DSLParser._behavior_error(line, f"unparseable require clause: {payload!r}")
        return DSLParser._behavior_ok(BehaviorKind.REQUIRE, text, line, references)

    def _parse_return(self, text: str, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        payload = "" if text == "return" else text[len(DSLParser.RETURN_PREFIX) :].strip()
        if not payload:
            return DSLParser._behavior_ok(BehaviorKind.RETURN, text, line, frozenset())
        references = self.expression_parser.extract_identifiers(payload)
        if references is None:
            return DSLParser._behavior_error(line, f"unparseable return expression: {payload!r}")
        return DSLParser._behavior_ok(BehaviorKind.RETURN, text, line, references)

    def _parse_operation(self, text: str, line: DSLParser._Line) -> DSLParser._BehaviorLineResult:
        references = self.expression_parser.extract_identifiers(text)
        if references is None:
            return DSLParser._behavior_error(line, f"unparseable behavior expression: {text!r}")
        return DSLParser._behavior_ok(BehaviorKind.OPERATION, text, line, references)

    # --- examples ------------------------------------------------------

    def _parse_examples(self, lines: list[DSLParser._Line]) -> DSLParser._ExampleBatch:
        examples: list[Example] = []
        diagnostics: list[Diagnostic] = []
        for line in lines:
            result = self._parse_example_line(line)
            if result.example is not None:
                examples.append(result.example)
            if result.diagnostic is not None:
                diagnostics.append(result.diagnostic)
        return DSLParser._ExampleBatch(examples=tuple(examples), diagnostics=tuple(diagnostics))

    def _parse_example_line(self, line: DSLParser._Line) -> DSLParser._ExampleLineResult:
        text = line.text
        if DSLParser.RAISES_KEYWORD in text:
            call_part, _ = text.split(DSLParser.RAISES_KEYWORD, 1)
            kind = ExampleKind.RAISES
        elif DSLParser.EQUALS_OP in text:
            call_part, _ = text.split(DSLParser.EQUALS_OP, 1)
            kind = ExampleKind.EQUALS
        else:
            return DSLParser._example_error(line, f"example must use '==' or 'raises': {text!r}")
        call_target = self.expression_parser.extract_call_target(call_part.strip())
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

    # --- reference extraction (DSL-level glue) ------------------------

    def _extract_require_references(self, payload: str) -> frozenset[str] | None:
        # Two shapes: `<id> matches <id>` (custom matcher) or plain
        # host-language expression. The ``matches`` form is DSL-level
        # syntax; everything else delegates to the expression parser.
        parts = payload.split()
        if len(parts) >= 3 and parts[1] == "matches":
            return frozenset({parts[0]})
        return self.expression_parser.extract_identifiers(payload)

    # --- calls --------------------------------------------------------

    def _parse_calls(self, lines: list[DSLParser._Line]) -> DSLParser._CallsBatch:
        specs: list[CallableSpec] = []
        diagnostics: list[Diagnostic] = []
        for line in lines:
            result = self._parse_callable_line(line)
            if result.spec is not None:
                specs.append(result.spec)
            if result.diagnostic is not None:
                diagnostics.append(result.diagnostic)
        return DSLParser._CallsBatch(specs=tuple(specs), diagnostics=tuple(diagnostics))

    def _parse_callable_line(self, line: DSLParser._Line) -> DSLParser._CallableLineResult:
        signature_part, purpose = DSLParser._split_inline_purpose(line.text)
        paren_open = signature_part.find("(")
        if paren_open == -1:
            return DSLParser._callable_error(
                line, f"callable entry must contain '(': {line.text!r}"
            )
        qualified_name = signature_part[:paren_open].strip()
        if not DSLParser._is_qualified_identifier(qualified_name):
            return DSLParser._callable_error(line, f"invalid callable name: {qualified_name!r}")
        paren_close = DSLParser._matching_paren(signature_part, paren_open)
        if paren_close == -1:
            return DSLParser._callable_error(
                line, f"unbalanced parentheses in callable entry: {line.text!r}"
            )
        params_text = signature_part[paren_open + 1 : paren_close]
        tail = signature_part[paren_close + 1 :].strip()
        returns = self._extract_return_annotation(tail)
        if returns is DSLParser._RETURN_PARSE_FAILED:
            return DSLParser._callable_error(line, f"unparseable return annotation: {tail!r}")
        parsed_params = self.expression_parser.parse_parameter_list(params_text)
        if parsed_params is None:
            return DSLParser._callable_error(line, f"unparseable parameter list: {params_text!r}")
        return DSLParser._CallableLineResult(
            spec=CallableSpec(
                qualified_name=qualified_name,
                parameters=parsed_params,
                returns=returns,
                purpose=purpose,
                line=line.line,
            ),
            diagnostic=None,
        )

    def _extract_return_annotation(self, tail: str) -> str | None:
        if not tail:
            return None
        if not tail.startswith(DSLParser.RETURN_ARROW):
            return DSLParser._RETURN_PARSE_FAILED
        candidate = tail[len(DSLParser.RETURN_ARROW) :].strip()
        if not candidate:
            return DSLParser._RETURN_PARSE_FAILED
        if not self.expression_parser.is_valid_annotation(candidate):
            return DSLParser._RETURN_PARSE_FAILED
        return candidate

    # --- reads --------------------------------------------------------

    def _parse_reads(self, lines: list[DSLParser._Line]) -> DSLParser._ReadsBatch:
        specs: list[AttributeReadSpec] = []
        diagnostics: list[Diagnostic] = []
        for line in lines:
            result = self._parse_attribute_line(line)
            if result.spec is not None:
                specs.append(result.spec)
            if result.diagnostic is not None:
                diagnostics.append(result.diagnostic)
        return DSLParser._ReadsBatch(specs=tuple(specs), diagnostics=tuple(diagnostics))

    def _parse_attribute_line(self, line: DSLParser._Line) -> DSLParser._AttributeLineResult:
        text_part, purpose = DSLParser._split_inline_purpose(line.text)
        if ":" in text_part:
            name_part, annot_part = text_part.split(":", 1)
            qualified_name = name_part.strip()
            annotation_text = annot_part.strip() or None
        else:
            qualified_name = text_part.strip()
            annotation_text = None
        if not DSLParser._is_qualified_identifier(qualified_name):
            return DSLParser._attribute_error(line, f"invalid attribute name: {qualified_name!r}")
        if annotation_text is not None and not self.expression_parser.is_valid_annotation(
            annotation_text
        ):
            return DSLParser._attribute_error(
                line, f"unparseable attribute annotation: {annotation_text!r}"
            )
        return DSLParser._AttributeLineResult(
            spec=AttributeReadSpec(
                qualified_name=qualified_name,
                annotation=annotation_text,
                purpose=purpose,
                line=line.line,
            ),
            diagnostic=None,
        )

    # --- shared callee helpers (DSL-level, language-agnostic) ---------

    @staticmethod
    def _split_inline_purpose(text: str) -> tuple[str, str]:
        """Split a callable/attribute line into (signature, purpose) using ``#``.

        The ``#`` marker is the inline-comment convention. We scan ignoring
        ``#`` that sits inside parens, brackets, braces, or string literals
        so a type annotation like ``dict[str, list[int]]`` stays intact.
        """
        depth = 0
        in_str: str | None = None
        prev = ""
        for i, ch in enumerate(text):
            if in_str is not None:
                if ch == in_str and prev != "\\":
                    in_str = None
            elif ch in ("'", '"'):
                in_str = ch
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "#" and depth == 0:
                return text[:i].rstrip(), text[i + 1 :].strip()
            prev = ch
        return text.rstrip(), ""

    @staticmethod
    def _matching_paren(text: str, open_idx: int) -> int:
        depth = 0
        in_str: str | None = None
        prev = ""
        for i in range(open_idx, len(text)):
            ch = text[i]
            if in_str is not None:
                if ch == in_str and prev != "\\":
                    in_str = None
            elif ch in ("'", '"'):
                in_str = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i
            prev = ch
        return -1

    @staticmethod
    def _is_qualified_identifier(name: str) -> bool:
        if not name:
            return False
        return all(segment.isidentifier() for segment in name.split("."))

    @staticmethod
    def _callable_error(line: DSLParser._Line, message: str) -> DSLParser._CallableLineResult:
        return DSLParser._CallableLineResult(
            spec=None, diagnostic=DSLParser._malformed(line.line, message)
        )

    @staticmethod
    def _attribute_error(line: DSLParser._Line, message: str) -> DSLParser._AttributeLineResult:
        return DSLParser._AttributeLineResult(
            spec=None, diagnostic=DSLParser._malformed(line.line, message)
        )

    # --- diagnostic constructors --------------------------------------

    @staticmethod
    def _malformed(line: int, message: str) -> Diagnostic:
        return Diagnostic(line=line, code=DiagnosticCode.MALFORMED_DSL, message=message)

    @staticmethod
    def _invalid_example(line: int, message: str) -> Diagnostic:
        return Diagnostic(line=line, code=DiagnosticCode.INVALID_EXAMPLE, message=message)
