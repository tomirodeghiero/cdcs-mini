"""Pydantic schemas for the HTTP API.

The response wraps the shared ``ReportDict``, so the HTTP boundary
stays as typed as the CLI output — no ``Any`` slipping through.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cdcs_mini.reporting.schema import ReportDict

_SAMPLE_SOURCE = (
    "def parse_port(value: str) -> int:\n"
    '    """@generate\n'
    "    behavior:\n"
    "      strip(value)\n"
    "      require value matches digits\n"
    "      require 1 <= int(value) <= 65535\n"
    "      return int(value)\n"
    "\n"
    "    examples:\n"
    '      parse_port("80") == 80\n'
    '      parse_port("0") raises ValueError\n'
    "\n"
    "    constraints:\n"
    "      no_imports\n"
    "      no_network\n"
    "      no_filesystem\n"
    '    """\n'
    "    ...\n"
)


class FromSourceRequest(BaseModel):
    filename: str = Field(
        default="input.py",
        min_length=1,
        max_length=255,
        description="Logical filename used in diagnostics and error messages.",
        examples=["parse_port.py"],
    )
    source: str = Field(
        min_length=0,
        max_length=1_000_000,
        description="Raw Python source to analyze. Must be UTF-8 and parseable as Python 3.12.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"filename": "parse_port.py", "source": _SAMPLE_SOURCE},
            ],
        },
    )


class ReportResponse(BaseModel):
    # ReportDict already produces a precise schema in /docs, so we skip the manual example here
    report: ReportDict = Field(
        description=(
            "Deterministic report. `functions[]` always present; "
            "`errors[]` is non-empty only for file-level failures (e.g. SyntaxError)."
        ),
    )


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Always `ok` when the service is reachable.")

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


# --- synthesis endpoint shapes --------------------------------------


class SynthesizeRequest(BaseModel):
    filename: str = Field(
        default="input.py",
        min_length=1,
        max_length=255,
        description="Logical filename used in diagnostics and provenance.",
    )
    source: str = Field(
        min_length=0,
        max_length=200_000,
        description=(
            "Raw Python source. Every @generate function with a valid "
            "contract will trigger an LLM synthesis call."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"filename": "parse_port.py", "source": _SAMPLE_SOURCE}],
        },
    )


class DiagnosticInfo(BaseModel):
    code: str
    message: str
    line: int | None = None


class SynthesisFailureDict(BaseModel):
    code: str = Field(description="Compiler-style error code (PDF §8).")
    message: str = Field(description="Human-readable failure summary.")
    detail: list[str] = Field(
        default_factory=list,
        description="Per-gate failure messages, if any.",
    )
    partial_implementation: str | None = Field(
        default=None,
        description=(
            "Set when the impl synthesis succeeded but the test loop "
            "exhausted its retry budget — surfaces the LLM's impl output "
            "so the UI can still display the partial result."
        ),
    )


class SynthesizedFunction(BaseModel):
    name: str
    line: int
    status: str = Field(description="`ok` | `error` | `skipped`.")
    implementation: str | None = Field(
        default=None, description="Synthesized impl body (with provenance header)."
    )
    test: str | None = Field(
        default=None, description="Synthesized pytest module (with provenance header)."
    )
    contract_hash: str | None = Field(
        default=None,
        description="sha256 of the canonical prompt payload — provenance marker.",
    )
    model: str | None = Field(default=None)
    llm_calls: int | None = Field(default=None)
    repair_attempts: int | None = Field(default=None)
    failure: SynthesisFailureDict | None = Field(
        default=None, description="Present only when status == 'error'."
    )
    upstream_diagnostics: list[DiagnosticInfo] = Field(
        default_factory=list,
        description="Validator diagnostics that blocked synthesis before any LLM call.",
    )


class SynthesizeResponse(BaseModel):
    source_filename: str
    language: str = Field(
        default="python",
        description=(
            "Host language the synthesis ran for (``'python'`` or "
            "``'typescript'``). Picked by extension on the request "
            "``filename``; informs how the frontend renders the output."
        ),
    )
    impl_filename: str = Field(
        default="input_generated.py",
        description="Filename the synthesized impl would be written to on disk.",
    )
    test_filename: str = Field(
        default="test_input_generated.py",
        description="Filename the synthesized tests would be written to on disk.",
    )
    functions: list[SynthesizedFunction]
    errors: list[DiagnosticInfo] = Field(
        default_factory=list,
        description="File-level errors (syntax, IO). When non-empty, `functions` is empty.",
    )
