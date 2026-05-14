"""Pydantic schemas for the HTTP API.

The response wraps the shared ``ReportDict``, so the HTTP boundary
stays as typed as the CLI output — no ``Any`` slipping through.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from cdcs_mini.reporting.schema import ReportDict

_SAMPLE_SOURCE = (
    'def parse_port(value: str) -> int:\n'
    '    """@generate\n'
    '    behavior:\n'
    '      strip(value)\n'
    '      require value matches digits\n'
    '      require 1 <= int(value) <= 65535\n'
    '      return int(value)\n'
    '\n'
    '    examples:\n'
    '      parse_port("80") == 80\n'
    '      parse_port("0") raises ValueError\n'
    '\n'
    '    constraints:\n'
    '      no_imports\n'
    '      no_network\n'
    '      no_filesystem\n'
    '    """\n'
    '    ...\n'
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
