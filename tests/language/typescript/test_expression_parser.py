from __future__ import annotations

from cdcs.language.typescript.expression_parser import TypeScriptExpressionParser


def test_extract_identifiers_skips_callees_and_returns_args() -> None:
    parser = TypeScriptExpressionParser()
    refs = parser.extract_identifiers("strip(value)")
    # ``strip`` is the callee, only ``value`` is a parameter reference
    assert refs == frozenset({"value"})


def test_extract_identifiers_handles_comparison_expressions() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.extract_identifiers("ttl > 0") == frozenset({"ttl"})
    assert parser.extract_identifiers("board[position] === ''") == frozenset({"board", "position"})


def test_extract_identifiers_returns_none_for_garbage() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.extract_identifiers("@@@ not valid @@@") is None


def test_extract_call_target_returns_callee_name() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.extract_call_target('parsePort("80")') == "parsePort"


def test_extract_call_target_rejects_method_calls_and_non_calls() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.extract_call_target("obj.method(x)") is None
    assert parser.extract_call_target("a + b") is None


def test_is_valid_annotation_accepts_ts_types() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.is_valid_annotation("string")
    assert parser.is_valid_annotation("Array<number>")
    assert parser.is_valid_annotation("string | null")
    assert parser.is_valid_annotation("{ x: number }")


def test_is_valid_annotation_rejects_garbage() -> None:
    parser = TypeScriptExpressionParser()
    assert not parser.is_valid_annotation("")
    assert not parser.is_valid_annotation("not a type at all !")


def test_parse_parameter_list_required_and_optional_and_rest() -> None:
    parser = TypeScriptExpressionParser()
    params = parser.parse_parameter_list("name?: string, count: number = 0, ...rest: string[]")
    assert params is not None
    assert [(p.name, p.annotation, p.kind) for p in params] == [
        ("name", "string", "optional"),
        ("count", "number", "optional"),
        ("rest", "string[]", "rest"),
    ]


def test_parse_parameter_list_empty_yields_empty_tuple() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.parse_parameter_list("") == ()


def test_parse_parameter_list_returns_none_on_invalid_input() -> None:
    parser = TypeScriptExpressionParser()
    assert parser.parse_parameter_list("name string,") is None


def test_expression_parser_caches_repeat_queries() -> None:
    parser = TypeScriptExpressionParser()
    first = parser.extract_identifiers("a + b * c")
    second = parser.extract_identifiers("a + b * c")
    assert first == second
    # Repeat hit should not spawn a second subprocess — best signal we have
    # without monkey-patching is that the cache populated.
    assert ("identifiers", "a + b * c") in parser._cache
