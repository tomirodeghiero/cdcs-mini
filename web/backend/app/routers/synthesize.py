"""Synthesis endpoint.

Wraps ``SynthesisService.compile`` in in-memory mode (no FS writes) so
the synthesized implementation and tests come back over the wire.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from web.backend.app.dependencies import (
    LLMClientDep,
    build_synthesis_service,
    select_adapter,
)
from web.backend.app.schemas import (
    DiagnosticInfo,
    SynthesisFailureDict,
    SynthesizedFunction,
    SynthesizeRequest,
    SynthesizeResponse,
)

from cdcs_mini.application.synthesis_service import (
    CompiledFunction,
)
from cdcs_mini.language.base import LanguageAdapter
from cdcs_mini.synthesis.artifacts import Lockfile
from cdcs_mini.synthesis.llm import LLMError

router = APIRouter(prefix="/synthesize", tags=["Synthesis"])


@router.post(
    "/from-source",
    response_model=SynthesizeResponse,
    summary="Synthesize implementations and tests from @generate contracts",
    description=(
        "Runs the full CDCS pipeline: parses contracts, validates them, then "
        "for every clean contract calls the LLM **twice** (implementation + "
        "tests, in separate prompts per PDF §9), runs the verification gates, "
        "and returns the generated code in-memory.\n\n"
        "**LLM backend** is resolved at request time:\n"
        "1. `CDCS_LLM_PROVIDER` env (`anthropic` / `ollama` / `pollinations`).\n"
        "2. `ANTHROPIC_API_KEY` in env → Anthropic Claude.\n"
        "3. Local Ollama if `localhost:11434` is reachable.\n"
        "4. Fallback: keyless **Pollinations.ai** (rate-limited)."
    ),
    responses={
        200: {"description": "Synthesis attempted. Per-function `status` says what happened."},
        502: {
            "description": "LLM backend failed (network error, rate limit exhausted).",
        },
    },
)
def from_source(payload: SynthesizeRequest, llm: LLMClientDep) -> SynthesizeResponse:
    adapter = select_adapter(payload.filename)
    service = build_synthesis_service(adapter, llm)
    try:
        report = service.compile(
            source=payload.source,
            source_path=Path(payload.filename),
            dest_dir=None,  # in-memory: no FS writes
            lockfile=Lockfile.empty(),
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}") from exc
    return _to_response(payload.filename, adapter, report.functions)


def _to_response(
    filename: str,
    adapter: LanguageAdapter,
    functions: tuple[CompiledFunction, ...],
) -> SynthesizeResponse:
    stem = Path(filename).stem
    impl_filename = f"{stem}{adapter.impl_artifact_suffix}"
    test_filename = _test_filename(stem, adapter.test_artifact_suffix)
    base = {
        "source_filename": filename,
        "language": adapter.name,
        "impl_filename": impl_filename,
        "test_filename": test_filename,
    }
    # Detect a source-level error (file didn't parse or the like) — we encode
    # that as the first compiled function being named ``<source>`` per the service.
    if len(functions) == 1 and functions[0].function_name == "<source>":
        errors = [
            DiagnosticInfo(code=d.code.value, message=d.message, line=d.line)
            for d in functions[0].upstream_diagnostics
        ]
        return SynthesizeResponse(**base, functions=[], errors=errors)
    rendered = [_render_function(fn) for fn in functions]
    return SynthesizeResponse(**base, functions=rendered, errors=[])


def _test_filename(stem: str, test_suffix: str) -> str:
    # Mirrors ``ArtifactEmitter._test_filename`` so the response shows
    # the same filename the on-disk emitter would produce.
    if ".test." in test_suffix:
        return f"{stem}{test_suffix}"
    return f"test_{stem}{test_suffix}"


def _render_function(fn: CompiledFunction) -> SynthesizedFunction:
    upstream = [
        DiagnosticInfo(code=d.code.value, message=d.message, line=d.line)
        for d in fn.upstream_diagnostics
    ]
    if fn.outcome is not None:
        return SynthesizedFunction(
            name=fn.function_name,
            line=fn.line,
            status=fn.status,
            implementation=fn.outcome.implementation_code,
            test=fn.outcome.test_code,
            contract_hash=fn.outcome.contract_hash,
            model=fn.outcome.model,
            llm_calls=fn.outcome.llm_calls,
            repair_attempts=fn.outcome.repair_attempts,
            upstream_diagnostics=upstream,
        )
    if fn.failure is not None:
        return SynthesizedFunction(
            name=fn.function_name,
            line=fn.line,
            status=fn.status,
            failure=SynthesisFailureDict(
                code=fn.failure.code.value,
                message=fn.failure.message,
                detail=[d.format() for d in fn.failure.detail],
                partial_implementation=fn.failure.partial_implementation,
            ),
            upstream_diagnostics=upstream,
        )
    return SynthesizedFunction(
        name=fn.function_name,
        line=fn.line,
        status=fn.status,
        upstream_diagnostics=upstream,
    )
