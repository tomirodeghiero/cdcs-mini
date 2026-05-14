"""cdcs-mini: deterministic parser and JSON reporter for @generate contracts."""

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import (
    BehaviorStep,
    Contract,
    Example,
    FunctionReport,
    Parameter,
    Report,
    Signature,
)

__all__ = [
    "BehaviorStep",
    "Contract",
    "Diagnostic",
    "DiagnosticCode",
    "Example",
    "FunctionReport",
    "Parameter",
    "Report",
    "ReportService",
    "Signature",
]
