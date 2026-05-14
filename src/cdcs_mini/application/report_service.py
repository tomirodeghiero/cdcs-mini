"""Glues parsing and validation together into a final ``Report``.

Stays deliberately thin: it owns the order of the steps and the wiring
between collaborators, nothing else. Each collaborator comes through
the constructor so tests can swap any of them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import Contract, FunctionReport, Report
from cdcs_mini.parsing.dsl_parser import DSLParser
from cdcs_mini.parsing.source_parser import ParsedFunction, SourceParser
from cdcs_mini.validation.validators import DEFAULT_VALIDATORS, ContractValidator


@dataclass(frozen=True, slots=True)
class ReportService:
    source_parser: SourceParser
    dsl_parser: DSLParser
    validators: Sequence[ContractValidator]

    @classmethod
    def default(cls) -> ReportService:
        return cls(
            source_parser=SourceParser(),
            dsl_parser=DSLParser(),
            validators=DEFAULT_VALIDATORS,
        )

    def build_report(self, source: str, *, filename: str = "<input>") -> Report:
        parsed = self.source_parser.parse(source, filename=filename)
        if parsed.errors:
            return Report(functions=(), errors=tuple(sorted(parsed.errors)))

        return Report(
            functions=tuple(self._build_function_report(fn) for fn in parsed.functions),
            errors=(),
        )

    def _build_function_report(self, parsed: ParsedFunction) -> FunctionReport:
        diagnostics: list[Diagnostic] = list(parsed.diagnostics)

        if parsed.docstring is None:
            diagnostics.append(
                Diagnostic(
                    line=parsed.line,
                    code=DiagnosticCode.MISSING_GENERATE,
                    message="function has no @generate contract",
                )
            )
            return FunctionReport(
                name=parsed.name,
                line=parsed.line,
                signature=parsed.signature,
                contract=None,
                diagnostics=tuple(sorted(diagnostics)),
            )

        dsl_result = self.dsl_parser.parse(parsed.docstring, base_line=_dsl_base_line(parsed))
        diagnostics.extend(dsl_result.diagnostics)

        # A variadic signature is already unusable — running the rest of the
        # validators on it would just spam unrelated errors
        if not parsed.signature.has_variadic:
            diagnostics.extend(self._run_validators(parsed, dsl_result.contract))

        return FunctionReport(
            name=parsed.name,
            line=parsed.line,
            signature=parsed.signature,
            contract=dsl_result.contract,
            diagnostics=tuple(sorted(diagnostics)),
        )

    def _run_validators(
        self, parsed: ParsedFunction, contract: Contract
    ) -> list[Diagnostic]:
        result: list[Diagnostic] = []
        for validator in self.validators:
            result.extend(
                validator(
                    signature=parsed.signature,
                    contract=contract,
                    function_line=parsed.line,
                )
            )
        return result


def _dsl_base_line(parsed: ParsedFunction) -> int:
    # First DSL line sits one line under the @generate marker
    if parsed.docstring_line is None:
        return parsed.line
    return parsed.docstring_line + 1


def render_diagnostics(report: Report) -> str:
    """Flat, line-sorted layout for stderr — mostly useful for goldens."""
    lines: list[str] = [err.format() for err in report.errors]
    for fn in report.functions:
        for diag in fn.diagnostics:
            lines.append(f"{diag.format()} in {fn.name}")
    return "\n".join(lines)
