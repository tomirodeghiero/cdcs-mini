"""Domain models. Everything here is immutable on purpose."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from cdcs_mini.domain.diagnostics import Diagnostic

ParameterKind = Literal["positional_or_keyword", "positional_only", "keyword_only"]


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
class Contract:
    behavior: tuple[BehaviorStep, ...]
    examples: tuple[Example, ...]
    constraints: tuple[str, ...]
    # True when the docstring carried an "examples:" header, even if it was empty.
    # Lets us tell MissingSamplesError apart from an empty section
    has_examples_section: bool


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
