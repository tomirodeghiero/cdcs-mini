"""JSON reporter — the default ``Reporter``.

A few choices add up to a deterministic output:

* parameters keep their declaration order (Python dicts are insertion-ordered);
* constraints keep declaration order too;
* diagnostics arrive already sorted by ``(line, code, message)``;
* ``sort_keys=False`` leaves key order to this file, not to the encoder.

The dict shape is pinned by ``ReportDict`` so nothing leaks as ``Any``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import NamedTuple

from cdcs_mini.domain.diagnostics import Diagnostic
from cdcs_mini.domain.models import (
    AttributeReadSpec,
    BehaviorStep,
    CallableSpec,
    Contract,
    FunctionReport,
    Report,
)
from cdcs_mini.reporting.schema import (
    AttributeReadSpecDict,
    BehaviorStepDict,
    CallableSpecDict,
    DiagnosticDict,
    FunctionDict,
    ReportDict,
)


class _ContractFields(NamedTuple):
    behavior: list[BehaviorStepDict]
    examples_count: int
    constraints: list[str]
    calls: list[CallableSpecDict]
    reads: list[AttributeReadSpecDict]


@dataclass(frozen=True, slots=True)
class JsonReporter:
    # indent=2 matches the spec's expected output; pass None for compact JSON
    indent: int | None = 2

    def render(self, report: Report) -> str:
        return json.dumps(
            self.to_dict(report),
            indent=self.indent,
            sort_keys=False,
            ensure_ascii=False,
            separators=(",", ": ") if self.indent is not None else (", ", ": "),
        )

    def to_dict(self, report: Report) -> ReportDict:
        return {
            "functions": [self._function_to_dict(fn) for fn in report.functions],
            "errors": [self._diagnostic_to_dict(err) for err in report.errors],
        }

    def _function_to_dict(self, fn: FunctionReport) -> FunctionDict:
        parameters: dict[str, str | None] = {p.name: p.annotation for p in fn.signature.parameters}
        fields = self._contract_fields(fn.contract)
        result: FunctionDict = {
            "name": fn.name,
            "status": fn.status,
            "parameters": parameters,
            "returns": fn.signature.returns,
            "behavior": fields.behavior,
            "examples": fields.examples_count,
            "constraints": fields.constraints,
            "calls": fields.calls,
            "reads": fields.reads,
        }
        if fn.diagnostics:
            result["diagnostics"] = [self._diagnostic_to_dict(d) for d in fn.diagnostics]
        return result

    def _contract_fields(self, contract: Contract | None) -> _ContractFields:
        if contract is None:
            return _ContractFields(
                behavior=[], examples_count=0, constraints=[], calls=[], reads=[]
            )
        return _ContractFields(
            behavior=[self._behavior_step_to_dict(step) for step in contract.behavior],
            examples_count=len(contract.examples),
            constraints=list(contract.constraints),
            calls=[self._callable_spec_to_dict(c) for c in contract.calls],
            reads=[self._attribute_read_to_dict(r) for r in contract.reads],
        )

    def _callable_spec_to_dict(self, spec: CallableSpec) -> CallableSpecDict:
        return {
            "qualified_name": spec.qualified_name,
            "parameters": {p.name: p.annotation for p in spec.parameters},
            "returns": spec.returns,
            "purpose": spec.purpose,
            "line": spec.line,
        }

    def _attribute_read_to_dict(self, spec: AttributeReadSpec) -> AttributeReadSpecDict:
        return {
            "qualified_name": spec.qualified_name,
            "annotation": spec.annotation,
            "purpose": spec.purpose,
            "line": spec.line,
        }

    def _behavior_step_to_dict(self, step: BehaviorStep) -> BehaviorStepDict:
        return {
            "kind": step.kind.value,
            "raw": step.raw,
            "line": step.line,
            # Sort so the output stays deterministic regardless of frozenset order
            "references": sorted(step.references),
        }

    def _diagnostic_to_dict(self, diagnostic: Diagnostic) -> DiagnosticDict:
        return {
            "code": diagnostic.code.value,
            "message": diagnostic.message,
            "line": diagnostic.line,
        }
