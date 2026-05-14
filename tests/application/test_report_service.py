from __future__ import annotations

import json
from collections.abc import Callable

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.domain.models import Report
from cdcs_mini.reporting.json_reporter import JsonReporter


def _build(source: str) -> Report:
    return ReportService.default().build_report(source)


def test_valid_input_matches_spec_shape(read_fixture: Callable[[str], str]) -> None:
    report = _build(read_fixture("valid_input.py"))
    payload = JsonReporter().to_dict(report)

    fn = payload["functions"][0]
    assert payload["errors"] == []
    assert fn["name"] == "parse_port"
    assert fn["status"] == "ok"
    assert fn["parameters"] == {"value": "str"}
    assert fn["returns"] == "int"
    assert fn["examples"] == 3
    assert fn["constraints"] == ["no_imports", "no_network", "no_filesystem"]

    # Behavior breakdown — the enrichment requested in the challenge errata
    assert [step["kind"] for step in fn["behavior"]] == [
        "operation",
        "require",
        "require",
        "return",
    ]
    assert [step["raw"] for step in fn["behavior"]] == [
        "strip(value)",
        "require value matches digits",
        "require 1 <= int(value) <= 65535",
        "return int(value)",
    ]
    # Every step references only the single parameter; call targets like `strip`/`int` get dropped
    assert all(step["references"] == ["value"] for step in fn["behavior"])


def test_unknown_parameter_produces_inconsistent_prompt_error(
    read_fixture: Callable[[str], str],
) -> None:
    report = _build(read_fixture("unknown_parameter.py"))
    codes = [d.code for fn in report.functions for d in fn.diagnostics]
    assert DiagnosticCode.INCONSISTENT_PROMPT in codes
    assert report.functions[0].status == "error"


def test_missing_examples_produces_missing_samples_error(
    read_fixture: Callable[[str], str],
) -> None:
    report = _build(read_fixture("missing_examples.py"))
    codes = [d.code for fn in report.functions for d in fn.diagnostics]
    assert DiagnosticCode.MISSING_SAMPLES in codes


def test_variadic_signature_emits_unsupported_signature(
    read_fixture: Callable[[str], str],
) -> None:
    report = _build(read_fixture("variadic.py"))
    codes = [d.code for fn in report.functions for d in fn.diagnostics]
    assert DiagnosticCode.UNSUPPORTED_SIGNATURE in codes
    # A variadic signature is already an error — piling on "unknown parameter" would be noise
    assert DiagnosticCode.INCONSISTENT_PROMPT not in codes


def test_malformed_dsl_produces_diagnostics(read_fixture: Callable[[str], str]) -> None:
    report = _build(read_fixture("malformed_dsl.py"))
    codes = [d.code for fn in report.functions for d in fn.diagnostics]
    assert DiagnosticCode.MALFORMED_DSL in codes


def test_python_syntax_error_short_circuits_with_errors_array(
    read_fixture: Callable[[str], str],
) -> None:
    report = _build(read_fixture("syntax_error.py"))
    assert report.functions == ()
    assert len(report.errors) == 1
    assert report.errors[0].code == DiagnosticCode.SYNTAX_ERROR


def test_function_without_generate_is_flagged_but_not_fatal(
    read_fixture: Callable[[str], str],
) -> None:
    report = _build(read_fixture("no_generate.py"))
    assert len(report.functions) == 2
    for fn in report.functions:
        codes = [d.code for d in fn.diagnostics]
        assert DiagnosticCode.MISSING_GENERATE in codes


def test_json_output_is_deterministic(read_fixture: Callable[[str], str]) -> None:
    source = read_fixture("valid_input.py")
    reporter = JsonReporter()
    a = reporter.render(_build(source))
    b = reporter.render(_build(source))
    assert a == b
    # Sanity check: the string actually round-trips as JSON
    json.loads(a)


def test_no_external_keys_appear_in_baseline_output(
    read_fixture: Callable[[str], str],
) -> None:
    # Guard against schema drift: the spec pins these exact top-level keys
    # and per-function keys, anything else is a regression
    payload = JsonReporter().to_dict(_build(read_fixture("valid_input.py")))
    assert set(payload.keys()) == {"functions", "errors"}
    assert set(payload["functions"][0].keys()) == {
        "name",
        "status",
        "parameters",
        "returns",
        "behavior",
        "examples",
        "constraints",
    }
