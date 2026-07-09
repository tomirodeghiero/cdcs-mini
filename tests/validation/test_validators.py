from __future__ import annotations

from cdcs.domain.diagnostics import DiagnosticCode
from cdcs.domain.models import (
    AttributeReadSpec,
    BehaviorKind,
    BehaviorStep,
    CallableSpec,
    Contract,
    Example,
    ExampleKind,
    Parameter,
    Signature,
)
from cdcs.validation.validators import (
    validate_callable_surface,
    validate_completeness,
    validate_examples_consistency,
    validate_examples_present,
    validate_known_parameters,
)


def _signature(*names: str, annotations: dict[str, str] | None = None) -> Signature:
    annotations = annotations or {}
    parameters = tuple(
        Parameter(name=n, annotation=annotations.get(n), kind="positional_or_keyword")
        for n in names
    )
    return Signature(parameters=parameters, returns=None)


def _contract(
    *,
    behavior: tuple[BehaviorStep, ...] = (),
    examples: tuple[Example, ...] = (),
    calls: tuple[CallableSpec, ...] = (),
    reads: tuple[AttributeReadSpec, ...] = (),
    has_examples: bool = True,
) -> Contract:
    return Contract(
        behavior=behavior,
        examples=examples,
        constraints=(),
        calls=calls,
        reads=reads,
        has_examples_section=has_examples,
    )


def _equals(raw: str, line: int = 1) -> Example:
    return Example(kind=ExampleKind.EQUALS, raw=raw, line=line, call_target="f")


def _raises(raw: str, line: int = 1) -> Example:
    return Example(kind=ExampleKind.RAISES, raw=raw, line=line, call_target="f")


def test_missing_examples_section_is_reported() -> None:
    contract = _contract(has_examples=False)
    diagnostics = list(
        validate_examples_present(
            signature=_signature("value"),
            contract=contract,
            function_line=1,
        )
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.MISSING_SAMPLES


def test_empty_examples_section_is_reported() -> None:
    contract = _contract(has_examples=True)
    diagnostics = list(
        validate_examples_present(
            signature=_signature("value"),
            contract=contract,
            function_line=1,
        )
    )
    assert len(diagnostics) == 1


def test_unknown_parameter_is_flagged() -> None:
    behavior = (
        BehaviorStep(
            kind=BehaviorKind.OPERATION,
            raw="strip(nums)",
            line=4,
            references=frozenset({"nums"}),
        ),
    )
    diagnostics = list(
        validate_known_parameters(
            signature=_signature("value"),
            contract=_contract(behavior=behavior),
            function_line=1,
        )
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.INCONSISTENT_PROMPT
    assert "nums" in diagnostics[0].message


def test_known_parameters_and_builtins_pass() -> None:
    behavior = (
        BehaviorStep(
            kind=BehaviorKind.RETURN,
            raw="return int(value)",
            line=4,
            references=frozenset({"value"}),
        ),
    )
    diagnostics = list(
        validate_known_parameters(
            signature=_signature("value"),
            contract=_contract(behavior=behavior),
            function_line=1,
        )
    )
    assert diagnostics == []


# --- examples consistency --------------------------------------------


def test_contradictory_equals_examples_are_flagged() -> None:
    contract = _contract(examples=(_equals("f(2) == 4", 1), _equals("f(2) == 5", 2)))
    diagnostics = list(
        validate_examples_consistency(signature=_signature("x"), contract=contract, function_line=0)
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.CONTRADICTORY_EXAMPLES
    assert diagnostics[0].line == 2


def test_duplicate_equals_examples_are_not_flagged() -> None:
    contract = _contract(examples=(_equals("f(2) == 4", 1), _equals("f(2) == 4", 2)))
    diagnostics = list(
        validate_examples_consistency(signature=_signature("x"), contract=contract, function_line=0)
    )
    assert diagnostics == []


def test_equals_and_raises_on_same_args_is_flagged() -> None:
    contract = _contract(examples=(_equals("f(2) == 4", 1), _raises("f(2) raises ValueError", 2)))
    diagnostics = list(
        validate_examples_consistency(signature=_signature("x"), contract=contract, function_line=0)
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.CONTRADICTORY_EXAMPLES


# --- callable surface ------------------------------------------------


def test_self_qualified_callee_without_self_param_is_inconsistent() -> None:
    spec = CallableSpec(
        qualified_name="self._sign",
        parameters=(Parameter(name="p", annotation="str", kind="positional_or_keyword"),),
        returns="str",
        purpose="HMAC",
        line=5,
    )
    diagnostics = list(
        validate_callable_surface(
            signature=_signature("value"),
            contract=_contract(calls=(spec,)),
            function_line=1,
        )
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.INCONSISTENT_CALLABLE_SURFACE


def test_self_qualified_callee_with_self_param_is_ok() -> None:
    spec = CallableSpec(
        qualified_name="self._sign",
        parameters=(Parameter(name="p", annotation="str", kind="positional_or_keyword"),),
        returns="str",
        purpose="HMAC",
        line=5,
    )
    diagnostics = list(
        validate_callable_surface(
            signature=_signature("self", "value"),
            contract=_contract(calls=(spec,)),
            function_line=1,
        )
    )
    assert diagnostics == []


def test_duplicate_callee_declarations_are_flagged() -> None:
    p = Parameter(name="p", annotation="str", kind="positional_or_keyword")
    specs = (
        CallableSpec(
            qualified_name="hash_password",
            parameters=(p,),
            returns="str",
            purpose="bcrypt",
            line=5,
        ),
        CallableSpec(
            qualified_name="hash_password",
            parameters=(p,),
            returns="str",
            purpose="bcrypt",
            line=6,
        ),
    )
    diagnostics = list(
        validate_callable_surface(
            signature=_signature("value"),
            contract=_contract(calls=specs),
            function_line=1,
        )
    )
    assert len(diagnostics) == 1
    assert "duplicate" in diagnostics[0].message


def test_self_attribute_without_self_param_is_inconsistent() -> None:
    attr = AttributeReadSpec(qualified_name="self.secret", annotation="bytes", purpose="", line=5)
    diagnostics = list(
        validate_callable_surface(
            signature=_signature("value"),
            contract=_contract(reads=(attr,)),
            function_line=1,
        )
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.INCONSISTENT_CALLABLE_SURFACE


# --- completeness heuristic ------------------------------------------


def test_list_parameter_without_empty_example_is_incomplete() -> None:
    contract = _contract(examples=(_equals("first([3, 4]) == 3", 5),))
    diagnostics = list(
        validate_completeness(
            signature=_signature("values", annotations={"values": "list[int]"}),
            contract=contract,
            function_line=1,
        )
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].code == DiagnosticCode.INCOMPLETE_PROMPT
    assert "values" in diagnostics[0].message


def test_list_parameter_with_empty_example_is_complete() -> None:
    contract = _contract(
        examples=(_equals("first([3, 4]) == 3", 5), _raises("first([]) raises ValueError", 6))
    )
    diagnostics = list(
        validate_completeness(
            signature=_signature("values", annotations={"values": "list[int]"}),
            contract=contract,
            function_line=1,
        )
    )
    assert diagnostics == []


def test_str_parameter_does_not_trigger_completeness_diagnostic() -> None:
    contract = _contract(examples=(_equals('parse("80") == 80', 5),))
    diagnostics = list(
        validate_completeness(
            signature=_signature("value", annotations={"value": "str"}),
            contract=contract,
            function_line=1,
        )
    )
    assert diagnostics == []
