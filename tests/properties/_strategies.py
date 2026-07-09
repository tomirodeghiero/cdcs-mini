"""Hypothesis strategies shared by the property-based suite.

The strategies favour realism over exhaustiveness: identifiers look like
identifiers, parameters carry plausible annotations, and the diagnostic
line numbers stay positive — what we want from these tests is to find
genuine logic holes, not to stress-test the type system. Shrinking is
fast because each leaf strategy is small.
"""

from __future__ import annotations

from typing import get_args

import hypothesis.strategies as st

from cdcs.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs.domain.models import (
    AttributeReadSpec,
    BehaviorKind,
    BehaviorStep,
    CallableSpec,
    Contract,
    Example,
    ExampleKind,
    FunctionReport,
    Parameter,
    ParameterKind,
    Report,
    Signature,
)

_IDENTIFIER_FIRST = "abcdefghijklmnopqrstuvwxyz_"
_IDENTIFIER_REST = _IDENTIFIER_FIRST + "0123456789"

_PARAMETER_KINDS: tuple[ParameterKind, ...] = get_args(ParameterKind)


def identifiers() -> st.SearchStrategy[str]:
    """ASCII Python-style identifiers, length 1 to 8."""

    return st.builds(
        lambda head, tail: head + tail,
        st.sampled_from(_IDENTIFIER_FIRST),
        st.text(alphabet=_IDENTIFIER_REST, min_size=0, max_size=7),
    )


def type_annotations() -> st.SearchStrategy[str | None]:
    return st.one_of(
        st.none(),
        st.sampled_from(["int", "str", "bool", "float", "list[int]", "dict[str, int]"]),
    )


def parameters() -> st.SearchStrategy[Parameter]:
    return st.builds(
        Parameter,
        name=identifiers(),
        annotation=type_annotations(),
        kind=st.sampled_from(_PARAMETER_KINDS),
    )


def signatures() -> st.SearchStrategy[Signature]:
    return st.builds(
        Signature,
        parameters=_unique_parameter_tuples(),
        returns=type_annotations(),
        has_variadic=st.booleans(),
    )


def behavior_steps() -> st.SearchStrategy[BehaviorStep]:
    return st.builds(
        BehaviorStep,
        kind=st.sampled_from(list(BehaviorKind)),
        raw=st.text(min_size=0, max_size=40),
        line=st.integers(min_value=1, max_value=1000),
        references=st.frozensets(identifiers(), max_size=4),
    )


def examples() -> st.SearchStrategy[Example]:
    return st.builds(
        Example,
        kind=st.sampled_from(list(ExampleKind)),
        raw=st.text(min_size=0, max_size=40),
        line=st.integers(min_value=1, max_value=1000),
        call_target=st.one_of(st.none(), identifiers()),
    )


def callable_specs() -> st.SearchStrategy[CallableSpec]:
    return st.builds(
        CallableSpec,
        qualified_name=identifiers(),
        parameters=st.lists(parameters(), max_size=3).map(tuple),
        returns=type_annotations(),
        purpose=st.text(min_size=0, max_size=30),
        line=st.integers(min_value=1, max_value=1000),
    )


def attribute_reads() -> st.SearchStrategy[AttributeReadSpec]:
    return st.builds(
        AttributeReadSpec,
        qualified_name=identifiers(),
        annotation=type_annotations(),
        purpose=st.text(min_size=0, max_size=30),
        line=st.integers(min_value=1, max_value=1000),
    )


def contracts() -> st.SearchStrategy[Contract]:
    return st.builds(
        Contract,
        behavior=st.lists(behavior_steps(), max_size=4).map(tuple),
        examples=st.lists(examples(), max_size=4).map(tuple),
        constraints=st.lists(st.text(max_size=20), max_size=3).map(tuple),
        calls=_unique_callable_specs(),
        reads=_unique_attribute_reads(),
        has_examples_section=st.booleans(),
    )


def diagnostics() -> st.SearchStrategy[Diagnostic]:
    return st.builds(
        Diagnostic,
        line=st.one_of(st.none(), st.integers(min_value=1, max_value=1000)),
        code=st.sampled_from(list(DiagnosticCode)),
        message=st.text(min_size=0, max_size=40),
    )


def function_reports() -> st.SearchStrategy[FunctionReport]:
    return st.builds(
        FunctionReport,
        name=identifiers(),
        line=st.integers(min_value=1, max_value=1000),
        signature=signatures(),
        contract=st.one_of(st.none(), contracts()),
        diagnostics=st.lists(diagnostics(), max_size=4).map(tuple),
    )


def reports() -> st.SearchStrategy[Report]:
    return st.builds(
        Report,
        functions=st.lists(function_reports(), max_size=3).map(tuple),
        errors=st.lists(diagnostics(), max_size=3).map(tuple),
    )


# --- helpers ---------------------------------------------------------


def _unique_parameter_tuples() -> st.SearchStrategy[tuple[Parameter, ...]]:
    """Parameter names must be unique inside a signature."""

    return st.lists(parameters(), max_size=4, unique_by=lambda p: p.name).map(tuple)


def _unique_callable_specs() -> st.SearchStrategy[tuple[CallableSpec, ...]]:
    return st.lists(callable_specs(), max_size=3, unique_by=lambda c: c.qualified_name).map(tuple)


def _unique_attribute_reads() -> st.SearchStrategy[tuple[AttributeReadSpec, ...]]:
    return st.lists(attribute_reads(), max_size=3, unique_by=lambda r: r.qualified_name).map(tuple)
