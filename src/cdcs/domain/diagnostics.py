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

    # Synthesis-pipeline diagnostics (PDF §8 + Calls/Reads extension)
    INCOMPLETE_PROMPT = "IncompletePromptError"
    CONTRADICTORY_EXAMPLES = "ContradictoryExamplesError"
    PROMPT_CANNOT_SATISFY_TESTS = "PromptCannotSatisfyTestsError"
    EXCEEDED_LINT_ITERATIONS = "ExceededLintIterationsError"
    EXCEEDED_TEST_ITERATIONS = "ExceededTestIterationsError"
    GENERATED_CODE_TOO_COMPLEX = "GeneratedCodeTooComplexError"
    UNSAFE_GENERATED_CODE = "UnsafeGeneratedCodeError"
    UNDECLARED_CALLEE = "UndeclaredCalleeError"
    INCONSISTENT_CALLABLE_SURFACE = "InconsistentCallableSurfaceError"
    # Operational, not contract — kept separate so the user can tell an LLM
    # outage apart from a contract violation in the generated artifact.
    LLM_CALL_FAILED = "LLMCallFailedError"


# Field order = sort order. Two Diagnostics compare by line, then code, then message
@dataclass(frozen=True, slots=True, order=True)
class Diagnostic:
    line: int | None
    code: DiagnosticCode
    message: str

    def format(self) -> str:
        location = f"line {self.line}: " if self.line is not None else ""
        return f"{self.code.value}: {location}{self.message}"
