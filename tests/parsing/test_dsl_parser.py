from __future__ import annotations

from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.domain.models import BehaviorKind, ExampleKind
from cdcs_mini.parsing.dsl_parser import DSLParser, DSLParseResult


def _parse(body: str, *, base_line: int = 1) -> DSLParseResult:
    return DSLParser().parse(body, base_line=base_line)


def test_parses_behavior_steps_with_kinds() -> None:
    body = (
        "behavior:\n"
        "  strip(value)\n"
        "  require value matches digits\n"
        "  require 1 <= int(value) <= 65535\n"
        "  return int(value)\n"
        "\n"
        "examples:\n"
        "  parse_port(\"80\") == 80\n"
    )
    result = _parse(body)

    assert result.diagnostics == ()
    kinds = [step.kind for step in result.contract.behavior]
    assert kinds == [
        BehaviorKind.OPERATION,
        BehaviorKind.REQUIRE,
        BehaviorKind.REQUIRE,
        BehaviorKind.RETURN,
    ]


def test_collects_parameter_references_excluding_call_targets() -> None:
    body = (
        "behavior:\n"
        "  strip(value)\n"
        "  return int(value)\n"
        "\n"
        "examples:\n"
        "  f(\"x\") == \"x\"\n"
    )
    result = _parse(body)

    refs = [sorted(step.references) for step in result.contract.behavior]
    assert refs == [["value"], ["value"]]


def test_examples_classified_as_equals_or_raises() -> None:
    body = (
        "behavior:\n"
        "  return value\n"
        "examples:\n"
        '  f("1") == 1\n'
        '  f("x") raises ValueError\n'
    )
    result = _parse(body)

    assert [e.kind for e in result.contract.examples] == [
        ExampleKind.EQUALS,
        ExampleKind.RAISES,
    ]
    assert [e.call_target for e in result.contract.examples] == ["f", "f"]


def test_unknown_section_emits_malformed_diagnostic() -> None:
    body = "behavior:\n  return value\n\nweirdsection:\n  hi\n"
    result = _parse(body)
    codes = {d.code for d in result.diagnostics}
    assert DiagnosticCode.MALFORMED_DSL in codes


def test_orphan_line_before_any_section_is_malformed() -> None:
    body = "stray content\nbehavior:\n  return value\n"
    result = _parse(body)
    codes = {d.code for d in result.diagnostics}
    assert DiagnosticCode.MALFORMED_DSL in codes


def test_empty_require_is_malformed() -> None:
    body = "behavior:\n  require\n"
    result = _parse(body)
    codes = {d.code for d in result.diagnostics}
    assert DiagnosticCode.MALFORMED_DSL in codes


def test_has_examples_section_flag_tracks_presence() -> None:
    body_with_section = "behavior:\n  return value\n\nexamples:\n"
    body_without = "behavior:\n  return value\n"

    with_section = _parse(body_with_section)
    without = _parse(body_without)

    assert with_section.contract.has_examples_section is True
    assert without.contract.has_examples_section is False


def test_constraints_preserve_order() -> None:
    body = (
        "behavior:\n"
        "  return value\n"
        "examples:\n"
        '  f("x") == "x"\n'
        "constraints:\n"
        "  no_network\n"
        "  no_imports\n"
        "  no_filesystem\n"
    )
    result = _parse(body)
    assert result.contract.constraints == (
        "no_network",
        "no_imports",
        "no_filesystem",
    )


def test_base_line_offsets_diagnostics() -> None:
    body = "behavior:\n  weirdsection:\nweirdsection:\n  x\n"
    result = _parse(body, base_line=10)

    # Every diagnostic should be anchored at line 10 or beyond (base_line offset)
    lines = [d.line for d in result.diagnostics if d.line is not None]
    assert lines and all(line >= 10 for line in lines)
