"""Diagnostic types — shared by every stage of the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DiagnosticCode(StrEnum):
    # StrEnum: codes go to JSON as plain strings, no repr noise
    SYNTAX_ERROR = "SyntaxError"
    MALFORMED_DSL = "MalformedDSLError"
    MISSING_GENERATE = "MissingGenerateError"
    MISSING_SAMPLES = "MissingSamplesError"
    INCONSISTENT_PROMPT = "InconsistentPromptError"
    UNSUPPORTED_SIGNATURE = "UnsupportedSignatureError"
    INVALID_EXAMPLE = "InvalidExampleError"


# Field order = sort order. Two Diagnostics compare by line, then code, then message
@dataclass(frozen=True, slots=True, order=True)
class Diagnostic:
    line: int | None
    code: DiagnosticCode
    message: str

    def format(self) -> str:
        location = f"line {self.line}: " if self.line is not None else ""
        return f"{self.code.value}: {location}{self.message}"
