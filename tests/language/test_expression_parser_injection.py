"""The Fase 1 deliverable: prove the DSL parser delegates expression
parsing through the injected ``ExpressionParser`` Protocol instead of
calling ``ast`` directly. A fake parser stands in for what the future
TypeScript adapter will plug in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cdcs.domain.models import BehaviorKind, Parameter
from cdcs.parsing.dsl_parser import DSLParser


@dataclass
class _RecordingExpressionParser:
    """Fake parser that records every call and returns canned answers.

    Implements the ``ExpressionParser`` Protocol structurally — no
    explicit ``ExpressionParser`` base class needed because Python
    Protocols are structural.
    """

    identifier_calls: list[str] = field(default_factory=list)
    call_target_calls: list[str] = field(default_factory=list)
    annotation_calls: list[str] = field(default_factory=list)
    parameter_calls: list[str] = field(default_factory=list)

    def extract_identifiers(self, expression: str) -> frozenset[str] | None:
        self.identifier_calls.append(expression)
        # Treat every "word" as an identifier; useful enough for the test
        return frozenset(token for token in expression.split() if token.isidentifier())

    def extract_call_target(self, expression: str) -> str | None:
        self.call_target_calls.append(expression)
        # Pretend everything is a call to "fakeCall"
        return "fakeCall"

    def is_valid_annotation(self, annotation: str) -> bool:
        self.annotation_calls.append(annotation)
        return annotation != "invalid"

    def parse_parameter_list(self, params_text: str) -> tuple[Parameter, ...] | None:
        self.parameter_calls.append(params_text)
        if not params_text:
            return ()
        return (Parameter(name="x", annotation="number", kind="positional_or_keyword"),)


_DSL_BODY = """
behavior:
  require a > 0
  return foo

examples:
  doStuff(1) == 2

calls:
  helper(x: number) -> number

reads:
  self.state: number
""".strip()


def test_dsl_parser_routes_all_expression_work_through_injected_parser() -> None:
    fake = _RecordingExpressionParser()
    parser = DSLParser(expression_parser=fake)
    result = parser.parse(_DSL_BODY, base_line=10)

    # No diagnostics expected — the fake parser approves everything
    assert result.diagnostics == ()

    # behavior: one require, one return → 2 identifier extractions
    assert fake.identifier_calls == ["a > 0", "foo"]

    # examples: one example call_target lookup
    assert fake.call_target_calls == ["doStuff(1)"]

    # calls: one annotation (return type "number") + one parameter list
    assert "number" in fake.annotation_calls
    assert fake.parameter_calls == ["x: number"]

    # The behavior and examples shaped correctly
    assert len(result.contract.behavior) == 2
    assert result.contract.behavior[0].kind == BehaviorKind.REQUIRE
    assert result.contract.behavior[1].kind == BehaviorKind.RETURN
    assert len(result.contract.examples) == 1
    assert result.contract.examples[0].call_target == "fakeCall"


def test_dsl_parser_emits_diagnostic_when_injected_parser_rejects_expression() -> None:
    class _RejectingParser:
        def extract_identifiers(self, expression: str) -> frozenset[str] | None:
            _ = expression
            return None  # everything is unparseable

        def extract_call_target(self, expression: str) -> str | None:
            _ = expression
            return None

        def is_valid_annotation(self, annotation: str) -> bool:
            _ = annotation
            return True

        def parse_parameter_list(self, params_text: str) -> tuple[Parameter, ...] | None:
            _ = params_text
            return ()

    parser = DSLParser(expression_parser=_RejectingParser())
    result = parser.parse(
        "behavior:\n  return whatever\n",
        base_line=1,
    )
    assert any("unparseable return expression" in d.message for d in result.diagnostics)
