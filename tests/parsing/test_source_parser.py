from __future__ import annotations

from collections.abc import Callable

from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.parsing.source_parser import SourceParser


def test_extracts_signature_and_generate_body(read_fixture: Callable[[str], str]) -> None:
    parsed = SourceParser().parse(read_fixture("valid_input.py"))

    assert parsed.errors == ()
    assert len(parsed.functions) == 1

    fn = parsed.functions[0]
    assert fn.name == "parse_port"
    assert tuple((p.name, p.annotation) for p in fn.signature.parameters) == (
        ("value", "str"),
    )
    assert fn.signature.returns == "int"
    assert fn.signature.has_variadic is False
    assert fn.docstring is not None
    assert "behavior:" in fn.docstring
    assert fn.docstring.lstrip().startswith("behavior:")


def test_function_without_generate_marker_has_no_docstring(
    read_fixture: Callable[[str], str],
) -> None:
    parsed = SourceParser().parse(read_fixture("no_generate.py"))

    assert parsed.errors == ()
    assert [fn.docstring for fn in parsed.functions] == [None, None]


def test_variadic_signature_emits_unsupported_diagnostic(
    read_fixture: Callable[[str], str],
) -> None:
    parsed = SourceParser().parse(read_fixture("variadic.py"))

    assert parsed.errors == ()
    fn = parsed.functions[0]
    assert fn.signature.has_variadic is True
    codes = {d.code for d in fn.diagnostics}
    assert DiagnosticCode.UNSUPPORTED_SIGNATURE in codes


def test_python_syntax_error_is_reported_as_file_error(
    read_fixture: Callable[[str], str],
) -> None:
    parsed = SourceParser().parse(read_fixture("syntax_error.py"))

    assert parsed.functions == ()
    assert len(parsed.errors) == 1
    assert parsed.errors[0].code == DiagnosticCode.SYNTAX_ERROR
