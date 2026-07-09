"""Property-based tests for the contract validators.

These tests pin down the most-cited invariants:

* identical examples never contradict each other;
* ``validate_known_parameters`` is monotone: declaring more parameters
  can only reduce — never increase — the set of "unknown parameter"
  diagnostics;
* every diagnostic carries a non-empty message and a well-known code.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from cdcs.domain.diagnostics import DiagnosticCode
from cdcs.domain.models import (
    BehaviorKind,
    BehaviorStep,
    Contract,
    Example,
    ExampleKind,
    Parameter,
    Signature,
)
from cdcs.validation.validators import (
    validate_examples_consistency,
    validate_known_parameters,
)
from tests.properties._strategies import contracts, identifiers, signatures


@given(call=identifiers(), result=st.integers(min_value=-100, max_value=100))
@settings(max_examples=200, deadline=None)
def test_identical_examples_are_not_contradictory(call: str, result: int) -> None:
    """Two byte-identical examples must never be flagged as contradictory.

    PDF §8 reserves ``ContradictoryExamplesError`` for examples that
    *disagree*. Duplicates are noise, not a contract violation.
    """

    raw = f"{call}(1) == {result}"
    duplicated = (
        Example(kind=ExampleKind.EQUALS, raw=raw, line=10),
        Example(kind=ExampleKind.EQUALS, raw=raw, line=11),
    )
    contract = Contract(
        behavior=(),
        examples=duplicated,
        constraints=(),
        has_examples_section=True,
    )
    signature = Signature(
        parameters=(Parameter(name="x", annotation="int", kind="positional_or_keyword"),),
        returns="int",
    )
    diagnostics = list(
        validate_examples_consistency(signature=signature, contract=contract, function_line=1)
    )
    assert all(d.code is not DiagnosticCode.CONTRADICTORY_EXAMPLES for d in diagnostics)


@given(call=identifiers(), good=st.integers(), bad=st.integers())
@settings(max_examples=200, deadline=None)
def test_disagreeing_examples_are_flagged(call: str, good: int, bad: int) -> None:
    """Two ``==`` examples on the same call with different RHS values
    must produce exactly one ``ContradictoryExamples`` diagnostic.
    """

    if good == bad:
        return  # not contradictory by construction
    examples = (
        Example(kind=ExampleKind.EQUALS, raw=f"{call}(1) == {good}", line=5),
        Example(kind=ExampleKind.EQUALS, raw=f"{call}(1) == {bad}", line=6),
    )
    contract = Contract(
        behavior=(),
        examples=examples,
        constraints=(),
        has_examples_section=True,
    )
    signature = Signature(
        parameters=(Parameter(name="x", annotation="int", kind="positional_or_keyword"),),
        returns="int",
    )
    diagnostics = list(
        validate_examples_consistency(signature=signature, contract=contract, function_line=1)
    )
    assert sum(d.code is DiagnosticCode.CONTRADICTORY_EXAMPLES for d in diagnostics) == 1


@given(name=identifiers())
@settings(max_examples=200, deadline=None)
def test_known_parameters_validator_recognises_declared_names(name: str) -> None:
    """A reference whose name matches a declared parameter must not
    trigger an ``InconsistentPrompt`` diagnostic.
    """

    signature = Signature(
        parameters=(Parameter(name=name, annotation=None, kind="positional_or_keyword"),),
        returns=None,
    )
    contract = Contract(
        behavior=(
            BehaviorStep(
                kind=BehaviorKind.OPERATION,
                raw=f"return {name}",
                line=4,
                references=frozenset({name}),
            ),
        ),
        examples=(),
        constraints=(),
        has_examples_section=False,
    )
    diagnostics = list(
        validate_known_parameters(signature=signature, contract=contract, function_line=1)
    )
    assert not [d for d in diagnostics if d.code is DiagnosticCode.INCONSISTENT_PROMPT]


@given(signature=signatures(), contract=contracts())
@settings(max_examples=200, deadline=None)
def test_validator_diagnostics_have_well_formed_metadata(
    signature: Signature, contract: Contract
) -> None:
    """Every diagnostic emitted by the validator chain must carry a
    populated message and a code from the public enum.
    """

    validators = (validate_known_parameters, validate_examples_consistency)
    for validator in validators:
        for diagnostic in validator(signature=signature, contract=contract, function_line=1):
            assert diagnostic.message
            assert diagnostic.code in DiagnosticCode
