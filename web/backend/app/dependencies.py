"""Dependency providers.

Endpoints pull the service and the reporter via ``ServiceDep`` /
``ReporterDep`` rather than reaching for module-level singletons.
That's what makes them easy to override from tests::

    app.dependency_overrides[get_reporter] = lambda: my_fake
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from cdcs.application.report_service import ReportService
from cdcs.application.synthesis_service import SynthesisService
from cdcs.language.base import LanguageAdapter
from cdcs.language.python.adapter import PythonAdapter
from cdcs.language.typescript.adapter import TypeScriptAdapter
from cdcs.language.typescript.code_parser import (
    try_parse_typescript,
    typescript_test_sanity_failures,
)
from cdcs.reporting.base import Reporter
from cdcs.reporting.json_reporter import JsonReporter
from cdcs.synthesis.artifacts import ArtifactEmitter
from cdcs.synthesis.gates import GateChain
from cdcs.synthesis.llm import LLMClient, default_llm_client
from cdcs.synthesis.orchestrator import SynthesisOrchestrator
from cdcs.synthesis.policy import SynthesisPolicy
from cdcs.synthesis.prompt import PromptBuilder


def select_adapter(filename: str) -> LanguageAdapter:
    """Pick the language adapter for a request based on the filename.

    Mirrors :func:`cdcs.cli.select_adapter` so the HTTP layer and
    the CLI agree on how an upload becomes a language. Unknown
    extensions fall back to Python.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in {".ts", ".tsx"}:
        return TypeScriptAdapter()
    return PythonAdapter()


@lru_cache(maxsize=1)
def get_service() -> ReportService:
    return ReportService.default()


@lru_cache(maxsize=1)
def get_reporter() -> Reporter:
    return JsonReporter()


def get_llm_client() -> LLMClient:
    """Resolve an LLM client per environment.

    Defaults to the keyless public **Pollinations.ai** backend so the
    synthesis demo works out of the box. ``ANTHROPIC_API_KEY`` (or
    ``CDCS_LLM_PROVIDER=anthropic``) flips to the Anthropic SDK for
    production-grade runs.
    """
    return default_llm_client()


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


def build_synthesis_service(adapter: LanguageAdapter, llm: LLMClient) -> SynthesisService:
    """Assemble a per-adapter :class:`SynthesisService`.

    Cannot be cached across requests: the adapter is chosen from the
    request's filename, so each call gets a fresh service tuned to
    Python or TypeScript.
    """
    policy = SynthesisPolicy.strict_default()
    orchestrator_kwargs: dict[str, object] = {
        "prompt_builder": PromptBuilder(policy=policy, language=adapter.prompt_profile),
    }
    if adapter.name == "typescript":
        # TS LLM output isn't ``ast``-parseable; route validation through
        # the Node ts-runtime, and drop the in-process Python gate chain
        # (eslint/tsc/vitest gates are exercised out-of-band).
        orchestrator_kwargs["code_parser"] = try_parse_typescript
        orchestrator_kwargs["gate_chain"] = GateChain(gates=())
        orchestrator_kwargs["test_sanity_checker"] = typescript_test_sanity_failures
    return SynthesisService(
        report_service=ReportService.default(adapter),
        orchestrator=SynthesisOrchestrator.with_llm(llm, **orchestrator_kwargs),  # type: ignore[arg-type]
        emitter=ArtifactEmitter(
            impl_suffix=adapter.impl_artifact_suffix,
            test_suffix=adapter.test_artifact_suffix,
        ),
        policy=policy,
    )


ServiceDep = Annotated[ReportService, Depends(get_service)]
ReporterDep = Annotated[Reporter, Depends(get_reporter)]
