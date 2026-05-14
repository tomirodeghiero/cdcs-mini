"""Shape of the JSON report, expressed as ``TypedDict``s.

This is the output contract — the same dict the CLI dumps to JSON and
the HTTP layer returns. Defined once so both sides stay typed without
falling back to ``Any``. Matches the example in the challenge PDF and
adds the behavior breakdown requested in the errata.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict

Status = Literal["ok", "error"]
BehaviorKindName = Literal["operation", "require", "return"]


class DiagnosticDict(TypedDict):
    code: str
    message: str
    line: int | None


class BehaviorStepDict(TypedDict):
    kind: BehaviorKindName
    raw: str
    line: int
    references: list[str]


class FunctionDict(TypedDict):
    name: str
    status: Status
    parameters: dict[str, str | None]
    returns: str | None
    behavior: list[BehaviorStepDict]
    examples: int
    constraints: list[str]
    diagnostics: NotRequired[list[DiagnosticDict]]


class ReportDict(TypedDict):
    functions: list[FunctionDict]
    errors: list[DiagnosticDict]
