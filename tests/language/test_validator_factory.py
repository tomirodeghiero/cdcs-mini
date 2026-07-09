from __future__ import annotations

from cdcs.domain.models import (
    BehaviorKind,
    BehaviorStep,
    Contract,
    Parameter,
    Signature,
)
from cdcs.validation.validators import (
    DSL_MATCHERS,
    make_known_parameters_validator,
)


def _sig(*names: str) -> Signature:
    parameters = tuple(
        Parameter(name=name, annotation=None, kind="positional_or_keyword") for name in names
    )
    return Signature(parameters=parameters, returns=None)


def _contract(*references: str) -> Contract:
    return Contract(
        behavior=(
            BehaviorStep(
                kind=BehaviorKind.RETURN,
                raw="return ...",
                line=2,
                references=frozenset(references),
            ),
        ),
        examples=(),
        constraints=(),
        has_examples_section=True,
    )


def test_known_parameters_validator_treats_injected_globals_as_known() -> None:
    fake_globals = frozenset({"PI", "TAU"})
    validate = make_known_parameters_validator(fake_globals)
    diagnostics = list(
        validate(signature=_sig("x"), contract=_contract("PI", "x"), function_line=1)
    )
    assert diagnostics == []


def test_known_parameters_validator_flags_identifier_not_in_globals_or_params() -> None:
    validate = make_known_parameters_validator(frozenset())
    diagnostics = list(validate(signature=_sig("x"), contract=_contract("y"), function_line=1))
    assert len(diagnostics) == 1
    assert "unknown parameter: y" in diagnostics[0].message


def test_known_parameters_validator_always_accepts_dsl_matchers() -> None:
    # ``digits`` etc. are DSL-level — known regardless of host language
    validate = make_known_parameters_validator(frozenset())
    diagnostics = list(
        validate(
            signature=_sig("value"),
            contract=_contract("digits", "value"),
            function_line=1,
        )
    )
    assert diagnostics == []
    assert "digits" in DSL_MATCHERS
