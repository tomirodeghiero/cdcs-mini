from __future__ import annotations

from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.domain.models import (
    BehaviorKind,
    BehaviorStep,
    Contract,
    Parameter,
    Signature,
)
from cdcs_mini.validation.validators import (
    validate_examples_present,
    validate_known_parameters,
)


def _signature(*names: str) -> Signature:
    parameters = tuple(
        Parameter(name=n, annotation=None, kind="positional_or_keyword") for n in names
    )
    return Signature(parameters=parameters, returns=None)


def _contract(*, behavior: tuple[BehaviorStep, ...] = (), has_examples: bool = True) -> Contract:
    return Contract(
        behavior=behavior,
        examples=(),
        constraints=(),
        has_examples_section=has_examples,
    )


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
