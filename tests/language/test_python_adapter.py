from __future__ import annotations

from cdcs_mini.language.python.adapter import PythonAdapter
from cdcs_mini.language.python.expression_parser import PythonExpressionParser


def test_python_adapter_exposes_expected_metadata() -> None:
    adapter = PythonAdapter()
    assert adapter.name == "python"
    assert ".py" in adapter.source_extensions
    assert adapter.impl_artifact_suffix == "_generated.py"
    assert adapter.test_artifact_suffix == "_generated.py"


def test_python_adapter_known_globals_include_builtins_and_dsl_constants() -> None:
    adapter = PythonAdapter()
    assert "len" in adapter.known_globals
    assert "int" in adapter.known_globals
    assert "None" in adapter.known_globals
    assert "True" in adapter.known_globals


def test_python_expression_parser_extracts_identifiers() -> None:
    parser = PythonExpressionParser()
    refs = parser.extract_identifiers("a + b * c")
    assert refs == frozenset({"a", "b", "c"})


def test_python_expression_parser_skips_callees() -> None:
    parser = PythonExpressionParser()
    refs = parser.extract_identifiers("strip(value)")
    # ``strip`` is the callee, not a parameter reference
    assert refs == frozenset({"value"})


def test_python_expression_parser_returns_none_on_syntax_error() -> None:
    parser = PythonExpressionParser()
    assert parser.extract_identifiers("if x else") is None
    assert parser.extract_call_target("if x else") is None


def test_python_expression_parser_extract_call_target() -> None:
    parser = PythonExpressionParser()
    assert parser.extract_call_target('parse_port("80")') == "parse_port"
    # Not a bare call → None
    assert parser.extract_call_target("a + b") is None
    assert parser.extract_call_target("obj.method(x)") is None


def test_python_expression_parser_validates_annotation() -> None:
    parser = PythonExpressionParser()
    assert parser.is_valid_annotation("int") is True
    assert parser.is_valid_annotation("dict[str, list[int]]") is True
    assert parser.is_valid_annotation("not a type at all !") is False


def test_python_expression_parser_parses_parameter_list() -> None:
    parser = PythonExpressionParser()
    params = parser.parse_parameter_list("name: str, count: int = 0")
    assert params is not None
    assert len(params) == 2
    assert params[0].name == "name"
    assert params[0].annotation == "str"
    assert params[1].name == "count"


def test_python_expression_parser_rejects_variadics() -> None:
    parser = PythonExpressionParser()
    # The DSL doesn't model *args/**kwargs in declared callable surfaces
    assert parser.parse_parameter_list("*args") is None
    assert parser.parse_parameter_list("**kwargs") is None
