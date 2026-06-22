"""Domain models. Everything here is immutable on purpose."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from cdcs_mini.domain.diagnostics import Diagnostic

# Union of every shape a parameter can have across the supported host
# languages. The first three values come from Python; the last three from
# TypeScript / JavaScript. ``Parameter.kind`` is only ever written by a
# source parser and is informational — nothing downstream branches on it.
ParameterKind = Literal[
    "positional_or_keyword",
    "positional_only",
    "keyword_only",
    "required",
    "optional",
    "rest",
]


class BehaviorKind(StrEnum):
    OPERATION = "operation"
    REQUIRE = "require"
    RETURN = "return"


class ExampleKind(StrEnum):
    EQUALS = "equals"
    RAISES = "raises"


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    annotation: str | None
    kind: ParameterKind


@dataclass(frozen=True, slots=True)
class Signature:
    parameters: tuple[Parameter, ...]
    returns: str | None
    has_variadic: bool = False

    @property
    def parameter_names(self) -> frozenset[str]:
        return frozenset(p.name for p in self.parameters)


@dataclass(frozen=True, slots=True)
class BehaviorStep:
    kind: BehaviorKind
    raw: str
    line: int
    references: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class Example:
    kind: ExampleKind
    raw: str
    line: int
    call_target: str | None = None


@dataclass(frozen=True, slots=True)
class CallableSpec:
    """Declared callee available to the synthesizer.

    Acts as both:
      * prompt input — the LLM sees this entry and knows the callable
        exists with that signature and behavior;
      * AST allow-list — generated code may invoke this name; anything
        else triggers ``UndeclaredCalleeError``.

    ``qualified_name`` is the name as written in the contract:
    ``self.method`` for instance-method calls, ``module.func`` for
    module-qualified calls, plain ``name`` for unqualified imports.
    """

    qualified_name: str
    parameters: tuple[Parameter, ...]
    returns: str | None
    purpose: str
    line: int


@dataclass(frozen=True, slots=True)
class AttributeReadSpec:
    """Declared attribute access (typically ``self.x``).

    Read-only by default. Writes would be a separate ``Writes:`` section
    and counted as a side effect — out of POC scope.
    """

    qualified_name: str
    annotation: str | None
    purpose: str
    line: int


@dataclass(frozen=True, slots=True)
class Contract:
    behavior: tuple[BehaviorStep, ...]
    examples: tuple[Example, ...]
    constraints: tuple[str, ...]
    calls: tuple[CallableSpec, ...] = ()
    reads: tuple[AttributeReadSpec, ...] = ()
    # True when the docstring carried an "examples:" header, even if it was empty.
    # Lets us tell MissingSamplesError apart from an empty section
    has_examples_section: bool = False


@dataclass(frozen=True, slots=True)
class FunctionReport:
    name: str
    line: int
    signature: Signature
    contract: Contract | None
    diagnostics: tuple[Diagnostic, ...]

    @property
    def status(self) -> Literal["ok", "error"]:
        return "ok" if not self.diagnostics else "error"


@dataclass(frozen=True, slots=True)
class Report:
    functions: tuple[FunctionReport, ...]
    errors: tuple[Diagnostic, ...]
