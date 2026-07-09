"""Property-based tests for the ``@generate`` DSL parser.

Maps to the spec's claim that the parser is "stateless and reusable"
(see ``DSLParser`` docstring): given the same input, two independent
invocations — and the same instance reused — must yield equal results.
Hypothesis explores arbitrary text bodies to keep us honest about
whitespace, partial sections, and ill-formed lines.
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from cdcs.parsing.dsl_parser import DSLParser

# Restrict to printable text without control characters; the DSL is
# whitespace-significant and we want the property tests to focus on
# parser logic, not Unicode handling (covered by the explicit suite).
_BODY_ALPHABET = st.characters(
    min_codepoint=0x20,
    max_codepoint=0x7E,
    blacklist_characters="\x00",
)
bodies = st.text(alphabet=_BODY_ALPHABET, max_size=200)


@given(body=bodies)
@settings(max_examples=200, deadline=None)
def test_parsing_is_deterministic_across_calls(body: str) -> None:
    """Same input → same DSLParseResult, twice in a row."""

    parser = DSLParser()
    first = parser.parse(body, base_line=1)
    second = parser.parse(body, base_line=1)
    assert first == second


@given(body=bodies)
@settings(max_examples=200, deadline=None)
def test_parsing_is_deterministic_across_instances(body: str) -> None:
    """Two fresh parsers must agree on the same input."""

    a = DSLParser().parse(body, base_line=1)
    b = DSLParser().parse(body, base_line=1)
    assert a == b


@given(body=bodies, offset=st.integers(min_value=0, max_value=10_000))
@settings(max_examples=200, deadline=None)
def test_base_line_shifts_line_numbers_uniformly(body: str, offset: int) -> None:
    """A larger ``base_line`` shifts every emitted line number by the
    same delta. The set of diagnostic codes and the contract shape must
    not change.
    """

    parser = DSLParser()
    baseline = parser.parse(body, base_line=1)
    shifted = parser.parse(body, base_line=1 + offset)

    # Same diagnostic codes, same order
    assert [d.code for d in baseline.diagnostics] == [d.code for d in shifted.diagnostics]

    # Line deltas are uniform
    for a, b in zip(baseline.diagnostics, shifted.diagnostics, strict=True):
        if a.line is None:
            assert b.line is None
        else:
            assert b.line is not None
            assert b.line - a.line == offset

    # Contract shape is identical apart from line numbers
    assert len(baseline.contract.behavior) == len(shifted.contract.behavior)
    assert len(baseline.contract.examples) == len(shifted.contract.examples)
    assert baseline.contract.constraints == shifted.contract.constraints
