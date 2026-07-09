from __future__ import annotations

from pathlib import Path

from cdcs.domain.diagnostics import DiagnosticCode
from cdcs.language.typescript.source_parser import TypeScriptSourceParser


def _read(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / name).read_text(encoding="utf-8")


def test_source_parser_extracts_top_level_function(ts_fixtures_dir: Path) -> None:
    parser = TypeScriptSourceParser()
    result = parser.parse(_read(ts_fixtures_dir, "valid_input.ts"), filename="valid_input.ts")
    assert result.errors == ()
    assert len(result.functions) == 1
    fn = result.functions[0]
    assert fn.name == "parsePort"
    assert fn.signature.returns == "number"
    assert tuple((p.name, p.annotation, p.kind) for p in fn.signature.parameters) == (
        ("value", "string", "required"),
    )
    assert fn.docstring is not None
    assert "behavior:" in fn.docstring
    assert fn.docstring_line is not None


def test_source_parser_returns_none_docstring_when_no_generate_block(
    ts_fixtures_dir: Path,
) -> None:
    parser = TypeScriptSourceParser()
    result = parser.parse(_read(ts_fixtures_dir, "no_generate.ts"), filename="no_generate.ts")
    assert result.errors == ()
    assert len(result.functions) == 1
    assert result.functions[0].docstring is None


def test_source_parser_flags_variadic_signature(ts_fixtures_dir: Path) -> None:
    parser = TypeScriptSourceParser()
    result = parser.parse(_read(ts_fixtures_dir, "variadic.ts"), filename="variadic.ts")
    assert len(result.functions) == 1
    fn = result.functions[0]
    assert fn.signature.has_variadic is True
    assert fn.signature.parameters[0].kind == "rest"
    assert any(d.code == DiagnosticCode.UNSUPPORTED_SIGNATURE for d in fn.diagnostics)


def test_source_parser_reports_syntax_error_as_source_diagnostic(
    ts_fixtures_dir: Path,
) -> None:
    parser = TypeScriptSourceParser()
    result = parser.parse(_read(ts_fixtures_dir, "syntax_error.ts"), filename="syntax_error.ts")
    assert result.functions == ()
    assert len(result.errors) >= 1
    assert any(err.code == DiagnosticCode.SYNTAX_ERROR for err in result.errors)
