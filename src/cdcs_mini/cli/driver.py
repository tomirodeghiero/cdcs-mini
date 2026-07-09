"""CLI control flow.

Three top-level modes (PDF §17):

* ``cdcs-mini input.py [--out report.json]`` (default) — analyzer/reporter,
  same behavior as the original POC: parses, validates, emits JSON.
* ``cdcs-mini compile input.py [--dest dir/]`` — full synthesis: invokes
  the LLM, emits ``input.generated.py`` / ``test_input.generated.py``,
  updates ``cdcs.lock``.
* ``cdcs-mini check input.py [--dest dir/]`` — CI mode: no LLM call;
  validates that lock + generated files are in sync with the current
  contracts.

Exit codes (preserved across modes):
    0 — clean
    1 — diagnostics / drift detected
    2 — usage error
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.application.synthesis_service import SynthesisService
from cdcs_mini.cli.parsers import (
    SUBCOMMANDS,
    build_check_parser,
    build_compile_parser,
    build_parser,
)
from cdcs_mini.cli.ui import ConsoleUI, has_any_diagnostic
from cdcs_mini.language.base import LanguageAdapter
from cdcs_mini.language.python.adapter import PythonAdapter
from cdcs_mini.language.typescript.adapter import TypeScriptAdapter
from cdcs_mini.language.typescript.code_parser import (
    try_parse_typescript,
    typescript_test_sanity_failures,
)
from cdcs_mini.reporting.json_reporter import JsonReporter
from cdcs_mini.synthesis.artifacts import (
    LOCK_FILENAME,
    ArtifactEmitter,
    load_lock,
    save_lock,
)
from cdcs_mini.synthesis.gates import GateChain
from cdcs_mini.synthesis.llm import LLMClient, LLMError, default_llm_client
from cdcs_mini.synthesis.orchestrator import SynthesisOrchestrator
from cdcs_mini.synthesis.policy import SynthesisPolicy
from cdcs_mini.synthesis.prompt import PromptBuilder


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] in SUBCOMMANDS:
        subcommand, rest = raw[0], raw[1:]
        if subcommand == "compile":
            return _run_compile(rest)
        if subcommand == "check":
            return _run_check(rest)
    # Backwards-compatible default: the analyzer/reporter
    args = build_parser().parse_args(raw)
    return _run(args)


# --- analyzer / reporter --------------------------------------------


def _run(args: argparse.Namespace) -> int:
    ui = ConsoleUI(quiet=args.quiet, no_color=args.no_color)
    input_path: Path = args.input

    source = _read_source(input_path, ui)
    if source is None:
        return 2

    ui.banner()
    ui.input_info(input_path, input_path.stat().st_size)

    adapter = select_adapter(input_path)
    started = time.perf_counter()
    report = ReportService.default(adapter).build_report(source, filename=str(input_path))
    elapsed_ms = (time.perf_counter() - started) * 1000

    payload = JsonReporter().render(report)
    _write_payload(payload, args.out)

    ui.analysis_info(report, elapsed_ms)
    ui.summary(report)
    ui.diagnostics(report)
    ui.json_panel(payload)
    ui.outcome(args.out, len(payload), report)

    return 1 if has_any_diagnostic(report) else 0


# --- compile subcommand ---------------------------------------------


def _run_compile(argv: Sequence[str]) -> int:
    args = build_compile_parser().parse_args(argv)
    ui = ConsoleUI(quiet=args.quiet, no_color=args.no_color)
    source = _read_source(args.input, ui)
    if source is None:
        return 2
    dest_dir = args.dest or args.input.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    lock_path = args.lock or (dest_dir / LOCK_FILENAME)
    lockfile = load_lock(lock_path)
    llm = _build_llm_client(args.model)
    adapter = select_adapter(args.input)
    service = _build_synthesis_service(adapter, llm)
    ui.compile_banner(args.input, dest_dir, llm.model)
    started = time.perf_counter()
    try:
        report = service.compile(
            source=source,
            source_path=args.input,
            dest_dir=dest_dir,
            lockfile=lockfile,
        )
    except LLMError as exc:
        ui.fatal(f"cdcs-mini: LLM error: {exc}")
        return 2
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not report.has_errors:
        save_lock(report.lockfile, lock_path)
    ui.compile_report(report, lock_path, elapsed_ms)
    return 1 if report.has_errors else 0


def _build_synthesis_service(adapter: LanguageAdapter, llm: LLMClient) -> SynthesisService:
    policy = SynthesisPolicy.strict_default()
    orchestrator_kwargs: dict[str, object] = {
        "prompt_builder": PromptBuilder(policy=policy, language=adapter.prompt_profile),
    }
    if adapter.name == "typescript":
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


def _build_llm_client(model: str | None) -> LLMClient:
    # Honor the documented backend-resolution order (CDCS_LLM_PROVIDER →
    # ANTHROPIC_API_KEY → Ollama → Pollinations). Explicit --model only
    # overrides the model id, not the backend choice.
    if model is not None:
        return default_llm_client(model=model)
    return default_llm_client()


# --- check subcommand ----------------------------------------------


def _run_check(argv: Sequence[str]) -> int:
    args = build_check_parser().parse_args(argv)
    ui = ConsoleUI(quiet=args.quiet, no_color=args.no_color)
    source = _read_source(args.input, ui)
    if source is None:
        return 2
    dest_dir = args.dest or args.input.parent
    lock_path = args.lock or (dest_dir / LOCK_FILENAME)
    lockfile = load_lock(lock_path)
    adapter = select_adapter(args.input)
    # The check path doesn't need a real LLM client — the orchestrator
    # isn't called in check mode. Pass any client to satisfy the type.
    service = SynthesisService(
        report_service=ReportService.default(adapter),
        orchestrator=SynthesisOrchestrator.with_llm(_NoopLLM()),
        emitter=ArtifactEmitter(
            impl_suffix=adapter.impl_artifact_suffix,
            test_suffix=adapter.test_artifact_suffix,
        ),
    )
    stale = service.check(
        source=source,
        source_path=args.input,
        dest_dir=dest_dir,
        lockfile=lockfile,
    )
    ui.check_report(args.input, stale)
    return 1 if stale else 0


class _NoopLLM:
    """Placeholder LLM used by ``check`` mode — never invoked."""

    model = "noop"

    def complete(self, prompt: object) -> str:  # pragma: no cover - never called
        _ = prompt
        raise RuntimeError("check mode must not call the LLM")


# --- shared helpers ------------------------------------------------


def select_adapter(path: Path) -> LanguageAdapter:
    """Pick the language adapter for a given source file by extension.

    Falls back to :class:`PythonAdapter` when the extension isn't
    recognised, matching cdcs-mini's original Python-only behaviour for
    paths like ``input`` (no suffix) used by the test fixtures.
    """
    suffix = path.suffix.lower()
    if suffix in {".ts", ".tsx"}:
        return TypeScriptAdapter()
    return PythonAdapter()


def _read_source(input_path: Path, ui: ConsoleUI) -> str | None:
    if not input_path.is_file():
        ui.fatal(f"cdcs-mini: input file not found: {input_path}")
        return None
    try:
        return input_path.read_text(encoding="utf-8")
    except OSError as exc:
        ui.fatal(f"cdcs-mini: cannot read {input_path}: {exc}")
        return None


def _write_payload(payload: str, out_path: Path | None) -> None:
    if out_path is not None:
        out_path.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")


__all__ = ["main", "select_adapter"]
