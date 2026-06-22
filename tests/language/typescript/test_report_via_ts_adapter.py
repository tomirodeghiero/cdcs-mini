"""End-to-end: TS source → ParsedSource → DSLParser (TS adapter) →
ReportService. The same pipeline the Python side uses, but every
language-specific call routes through the TypeScript adapter.

This is the test that proves Fase 3 actually wires together — if the
Protocols are right, the high-level service flows without branching on
language.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.domain.models import Report
from cdcs_mini.language.typescript.adapter import TypeScriptAdapter
from cdcs_mini.language.typescript.source_parser import TypeScriptSourceParser
from cdcs_mini.parsing.dsl_parser import DSLParser
from cdcs_mini.validation.validators import default_validators


def _ts_report(source: str, *, filename: str) -> Report:
    """Build the same ``Report`` the CLI would produce — for a TS source."""
    adapter = TypeScriptAdapter()
    service = ReportService(
        source_parser=TypeScriptSourceParser(),
        dsl_parser=DSLParser(expression_parser=adapter.expression_parser),
        validators=default_validators(adapter.known_globals),
    )
    return service.build_report(source, filename=filename)


def _read(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / name).read_text(encoding="utf-8")


def test_valid_ts_fixture_produces_clean_report(ts_fixtures_dir: Path) -> None:
    report = _ts_report(_read(ts_fixtures_dir, "valid_input.ts"), filename="valid_input.ts")
    assert report.errors == ()
    assert len(report.functions) == 1
    fn = report.functions[0]
    assert fn.name == "parsePort"
    assert fn.status == "ok"
    assert fn.contract is not None
    # Behaviour was extracted via the TS expression parser
    behavior_kinds = [step.kind.value for step in fn.contract.behavior]
    assert "require" in behavior_kinds
    assert "return" in behavior_kinds


def test_missing_examples_yields_missing_samples_diagnostic(ts_fixtures_dir: Path) -> None:
    report = _ts_report(
        _read(ts_fixtures_dir, "missing_examples.ts"),
        filename="missing_examples.ts",
    )
    fn = report.functions[0]
    codes = {d.code for d in fn.diagnostics}
    assert DiagnosticCode.MISSING_SAMPLES in codes


def test_no_generate_block_yields_missing_generate(ts_fixtures_dir: Path) -> None:
    report = _ts_report(_read(ts_fixtures_dir, "no_generate.ts"), filename="no_generate.ts")
    fn = report.functions[0]
    codes = {d.code for d in fn.diagnostics}
    assert DiagnosticCode.MISSING_GENERATE in codes


def test_unknown_parameter_in_behavior_flags_inconsistent_prompt(
    ts_fixtures_dir: Path,
) -> None:
    report = _ts_report(
        _read(ts_fixtures_dir, "unknown_parameter.ts"),
        filename="unknown_parameter.ts",
    )
    fn = report.functions[0]
    codes = {d.code for d in fn.diagnostics}
    assert DiagnosticCode.INCONSISTENT_PROMPT in codes


def test_unknown_dsl_section_flags_malformed_dsl(ts_fixtures_dir: Path) -> None:
    report = _ts_report(
        _read(ts_fixtures_dir, "malformed_dsl.ts"),
        filename="malformed_dsl.ts",
    )
    fn = report.functions[0]
    codes = {d.code for d in fn.diagnostics}
    assert DiagnosticCode.MALFORMED_DSL in codes


def test_variadic_signature_short_circuits_validators(ts_fixtures_dir: Path) -> None:
    report = _ts_report(_read(ts_fixtures_dir, "variadic.ts"), filename="variadic.ts")
    fn = report.functions[0]
    codes = {d.code for d in fn.diagnostics}
    assert DiagnosticCode.UNSUPPORTED_SIGNATURE in codes
    # ``has_variadic`` short-circuits the validator chain, so it should NOT
    # also raise the consistency / completeness diagnostics
    assert DiagnosticCode.INCONSISTENT_PROMPT not in codes


def test_syntax_error_in_source_aborts_report(ts_fixtures_dir: Path) -> None:
    report = _ts_report(_read(ts_fixtures_dir, "syntax_error.ts"), filename="syntax_error.ts")
    assert report.functions == ()
    assert len(report.errors) >= 1
    assert all(err.code == DiagnosticCode.SYNTAX_ERROR for err in report.errors)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "valid_input.ts",
        "missing_examples.ts",
        "no_generate.ts",
        "unknown_parameter.ts",
        "malformed_dsl.ts",
        "variadic.ts",
    ],
)
def test_every_fixture_processes_without_crashing(ts_fixtures_dir: Path, fixture_name: str) -> None:
    """Smoke check — the adapter should never throw on any fixture, even
    when the contract itself is broken. All errors must come back as
    diagnostics, not exceptions."""
    report = _ts_report(_read(ts_fixtures_dir, fixture_name), filename=fixture_name)
    # Either the source parsed cleanly (functions populated) or it
    # reported errors — but the call itself must not raise.
    assert report.errors != () or report.functions != ()
