"""``cdcs-mini`` CLI entry point.

Three top-level modes:

* ``cdcs-mini input.py [--out report.json]`` (default) — analyzer/reporter,
  same behavior as the original POC: parses, validates, emits JSON.
* ``cdcs-mini compile input.py [--dest dir/]`` — full synthesis: invokes
  the LLM, emits ``input.generated.py``/``test_input.generated.py``,
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
from typing import NamedTuple

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.application.synthesis_service import (
    CompilationReport,
    CompiledFunction,
    SynthesisService,
)
from cdcs_mini.domain.diagnostics import Diagnostic
from cdcs_mini.domain.models import Report
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
    StaleArtifact,
    load_lock,
    save_lock,
)
from cdcs_mini.synthesis.gates import GateChain
from cdcs_mini.synthesis.llm import LLMClient, LLMError, default_llm_client
from cdcs_mini.synthesis.orchestrator import SynthesisOrchestrator
from cdcs_mini.synthesis.policy import SynthesisPolicy
from cdcs_mini.synthesis.prompt import PromptBuilder

__version__ = "0.1.0"

SUBCOMMANDS: frozenset[str] = frozenset({"compile", "check"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdcs-mini",
        description=(
            "Generate a deterministic JSON report from @generate contracts "
            "embedded in a Python source file."
        ),
    )
    parser.add_argument("input", type=Path, help="path to the Python source file")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="destination JSON file (writes to stdout if omitted)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress decorative output on stderr",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable colored output on stderr",
    )
    return parser


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


# --- compile subcommand ---------------------------------------------


def _build_compile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdcs-mini compile",
        description=(
            "Synthesize and verify implementation and tests for every "
            "@generate function in the source file."
        ),
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="output directory (defaults to the input file's directory)",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=None,
        help="path to cdcs.lock (defaults to <dest>/cdcs.lock)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="override the LLM model id (default: claude-opus-4-7)",
    )
    parser.add_argument("--quiet", action="store_true", help="suppress decorative output on stderr")
    parser.add_argument("--no-color", action="store_true", help="disable colored output on stderr")
    return parser


def _run_compile(argv: Sequence[str]) -> int:
    args = _build_compile_parser().parse_args(argv)
    ui = _UI(quiet=args.quiet, no_color=args.no_color)
    source = _read_source(args.input, ui)
    if source is None:
        return 2
    dest_dir = args.dest or args.input.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    lock_path = args.lock or (dest_dir / LOCK_FILENAME)
    lockfile = load_lock(lock_path)
    llm = _build_llm_client(args.model)
    adapter = _select_adapter(args.input)
    policy = SynthesisPolicy.strict_default()
    orchestrator_kwargs: dict[str, object] = {
        "prompt_builder": PromptBuilder(policy=policy, language=adapter.prompt_profile),
    }
    if adapter.name == "typescript":
        orchestrator_kwargs["code_parser"] = try_parse_typescript
        orchestrator_kwargs["gate_chain"] = GateChain(gates=())
        orchestrator_kwargs["test_sanity_checker"] = typescript_test_sanity_failures
    service = SynthesisService(
        report_service=ReportService.default(adapter),
        orchestrator=SynthesisOrchestrator.with_llm(llm, **orchestrator_kwargs),  # type: ignore[arg-type]
        emitter=ArtifactEmitter(
            impl_suffix=adapter.impl_artifact_suffix,
            test_suffix=adapter.test_artifact_suffix,
        ),
        policy=policy,
    )
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


def _select_adapter(path: Path) -> LanguageAdapter:
    """Pick the language adapter for a given source file by extension.

    Falls back to :class:`PythonAdapter` when the extension isn't
    recognised, matching cdcs-mini's original Python-only behaviour for
    paths like ``input`` (no suffix) used by the test fixtures.
    """
    suffix = path.suffix.lower()
    if suffix in {".ts", ".tsx"}:
        return TypeScriptAdapter()
    return PythonAdapter()


def _build_llm_client(model: str | None) -> LLMClient:
    # Honor the documented backend-resolution order (CDCS_LLM_PROVIDER →
    # ANTHROPIC_API_KEY → Ollama → Pollinations). Explicit --model only
    # overrides the model id, not the backend choice.
    if model is not None:
        return default_llm_client(model=model)
    return default_llm_client()


# --- check subcommand ----------------------------------------------


def _build_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cdcs-mini check",
        description="Verify that generated artifacts match the current @generate contracts (CI mode).",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--dest", type=Path, default=None)
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    return parser


def _run_check(argv: Sequence[str]) -> int:
    args = _build_check_parser().parse_args(argv)
    ui = _UI(quiet=args.quiet, no_color=args.no_color)
    source = _read_source(args.input, ui)
    if source is None:
        return 2
    dest_dir = args.dest or args.input.parent
    lock_path = args.lock or (dest_dir / LOCK_FILENAME)
    lockfile = load_lock(lock_path)
    adapter = _select_adapter(args.input)
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


def _run(args: argparse.Namespace) -> int:
    ui = _UI(quiet=args.quiet, no_color=args.no_color)
    input_path: Path = args.input

    source = _read_source(input_path, ui)
    if source is None:
        return 2

    ui.banner()
    ui.input_info(input_path, input_path.stat().st_size)

    adapter = _select_adapter(input_path)
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

    return 1 if _has_any_diagnostic(report) else 0


def _read_source(input_path: Path, ui: _UI) -> str | None:
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


def _has_any_diagnostic(report: Report) -> bool:
    return bool(report.errors) or any(fn.diagnostics for fn in report.functions)


class _UI:
    # Thin rich wrapper. Everything lands on stderr. --quiet mutes the chrome
    # but never the fatal-error console — those have to be readable always

    def __init__(self, *, quiet: bool, no_color: bool) -> None:
        self._console = Console(
            stderr=True,
            no_color=no_color,
            highlight=False,
            quiet=quiet,
        )
        # Separate console so fatal errors survive --quiet
        self._errors = Console(stderr=True, no_color=no_color, highlight=False)

    # --- top of run -------------------------------------------------

    def banner(self) -> None:
        title = Text()
        title.append("🚀 cdcs-mini ", style="bold cyan")
        title.append(f"v{__version__} ", style="dim")
        title.append("· ", style="dim")
        title.append("deterministic @generate analyzer", style="italic dim")
        self._console.print()
        self._console.print(title)
        self._console.print()

    def input_info(self, path: Path, size: int) -> None:
        text = Text()
        text.append("  📄 ", style="")
        text.append("input        ", style="bold")
        text.append(str(path), style="cyan")
        text.append(f"  ({_human_bytes(size)})", style="dim")
        self._console.print(text)

    def analysis_info(self, report: Report, elapsed_ms: float) -> None:
        n_fn = len(report.functions)
        text = Text()
        text.append("  ⚙  ", style="")
        text.append("analysis     ", style="bold")
        text.append(f"{n_fn} function" + ("" if n_fn == 1 else "s"), style="cyan")
        text.append(f"  ·  {elapsed_ms:.1f} ms", style="dim")
        self._console.print(text)
        self._console.print()

    # --- summary ----------------------------------------------------

    def summary(self, report: Report) -> None:
        n_fn = len(report.functions)
        n_diag = _total_diagnostics(report)
        n_constraints = _total_constraints(report)
        diag_style, diag_glyph = _diag_decorations(n_diag)

        table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
        table.add_column(style="bright_white")
        table.add_column()

        table.add_row("Functions", Text(str(n_fn), style="bold"))
        table.add_row("Diagnostics", Text(f"{n_diag}  {diag_glyph}", style=diag_style))
        table.add_row("Constraints", Text(str(n_constraints), style="bold"))

        self._console.print(
            Panel(
                table,
                title="📊 Report summary",
                title_align="left",
                border_style="bright_black",
                padding=(0, 1),
                box=ROUNDED,
                expand=False,
            )
        )
        self._console.print()

    # --- diagnostics table ------------------------------------------

    def diagnostics(self, report: Report) -> None:
        rows = _collect_diagnostic_rows(report)
        if not rows:
            return
        self._print_diagnostics_header(len(rows))
        self._print_diagnostics_table(rows)

    def _print_diagnostics_header(self, count: int) -> None:
        header = Text()
        header.append(f"  ⚠ {count} diagnostic", style="bold yellow")
        if count != 1:
            header.append("s", style="bold yellow")
        self._console.print(header)
        self._console.print()

    def _print_diagnostics_table(self, rows: list[_DiagRow]) -> None:
        table = Table(
            show_header=True,
            header_style="bold bright_black",
            border_style="bright_black",
            box=ROUNDED,
            padding=(0, 1),
            expand=False,
        )
        table.add_column("Code", style="yellow")
        table.add_column("Line", justify="right", style="dim")
        table.add_column("Message")
        table.add_column("Function", style="cyan")
        for row in rows:
            table.add_row(row.code, row.line or "—", row.message, row.fn_name or "—")
        self._console.print(table)
        self._console.print()

    # --- JSON report ------------------------------------------------

    def json_panel(self, payload: str) -> None:
        body = Syntax(
            payload,
            "json",
            theme="monokai",
            line_numbers=True,
            word_wrap=False,
            background_color="default",
        )
        self._console.print(
            Panel(
                body,
                title="📦 report.json",
                title_align="left",
                border_style="bright_black",
                padding=(0, 1),
                box=ROUNDED,
                expand=False,
            )
        )
        self._console.print()

    # --- bottom -----------------------------------------------------

    def outcome(self, out_path: Path | None, payload_size: int, report: Report) -> None:
        if out_path is not None:
            text = Text()
            text.append("  💾 ", style="")
            text.append("wrote        ", style="bold")
            text.append(str(out_path), style="cyan")
            text.append(f"  ({_human_bytes(payload_size)})", style="dim")
            self._console.print(text)

        bad = _has_any_diagnostic(report)
        exit_text = Text()
        exit_text.append("  → ", style="dim")
        exit_text.append("exit ", style="bold")
        exit_text.append("1" if bad else "0", style="bold yellow" if bad else "bold green")
        self._console.print(exit_text)
        self._console.print()

    # --- compile / check chrome ------------------------------------

    def compile_banner(self, input_path: Path, dest_dir: Path, model: str) -> None:
        title = Text()
        title.append("🛠  cdcs-mini compile ", style="bold cyan")
        title.append(f"v{__version__}", style="dim")
        self._console.print()
        self._console.print(title)
        for label, value in (
            ("source", str(input_path)),
            ("dest  ", str(dest_dir)),
            ("model ", model),
        ):
            text = Text()
            text.append("  ·  ", style="dim")
            text.append(label, style="bold")
            text.append(f"  {value}", style="cyan")
            self._console.print(text)
        self._console.print()

    def compile_report(
        self,
        report: CompilationReport,
        lock_path: Path,
        elapsed_ms: float,
    ) -> None:
        for fn in report.functions:
            self._print_compiled_function(fn)
        ok = sum(1 for fn in report.functions if fn.status == "ok")
        err = sum(1 for fn in report.functions if fn.status == "error")
        skipped = sum(1 for fn in report.functions if fn.status == "skipped")
        summary = Text()
        summary.append("\n  ✓ ", style="bold green" if err == 0 else "bold yellow")
        summary.append(f"{ok} synthesized", style="bold")
        summary.append(f"  ·  {err} errors", style="bold red" if err else "dim")
        summary.append(f"  ·  {skipped} skipped", style="dim")
        summary.append(f"  ·  {elapsed_ms:.0f} ms", style="dim")
        self._console.print(summary)
        if not report.has_errors:
            self._console.print(Text(f"\n  📝 lock: {lock_path}", style="dim"))
        self._console.print()

    def _print_compiled_function(self, fn: CompiledFunction) -> None:
        marker = {"ok": "✓", "error": "✗", "skipped": "•"}[fn.status]
        style = {"ok": "bold green", "error": "bold red", "skipped": "dim"}[fn.status]
        line = Text()
        line.append(f"  {marker} ", style=style)
        line.append(fn.function_name, style="cyan")
        if fn.status == "ok" and fn.outcome is not None:
            line.append(
                f"  ({fn.outcome.llm_calls} LLM calls, {fn.outcome.repair_attempts} repairs)",
                style="dim",
            )
        if fn.status == "error" and fn.failure is not None:
            line.append(f"  {fn.failure.code.value}", style="red")
        self._console.print(line)
        if fn.status == "error":
            if fn.failure is not None:
                self._console.print(Text(f"      {fn.failure.message}", style="red"))
            for diagnostic in fn.upstream_diagnostics:
                self._console.print(Text(f"      {diagnostic.format()}", style="red"))

    def check_report(self, input_path: Path, stale: tuple[StaleArtifact, ...]) -> None:
        title = Text()
        title.append("🔎 cdcs-mini check ", style="bold cyan")
        title.append(f"v{__version__}  ", style="dim")
        title.append(str(input_path), style="dim")
        self._console.print()
        self._console.print(title)
        if not stale:
            self._console.print(Text("  ✓ artifacts in sync", style="bold green"))
            self._console.print()
            return
        self._console.print(Text(f"  ✗ {len(stale)} drift(s) detected", style="bold red"))
        for item in stale:
            line = Text()
            line.append("    · ", style="dim")
            line.append(f"{item.source}::{item.function}", style="cyan")
            line.append(f"  [{item.reason}]", style="bold red")
            line.append(f"  {item.detail}", style="dim")
            self._console.print(line)
        self._console.print()

    # --- fatal ------------------------------------------------------

    def fatal(self, message: str) -> None:
        self._errors.print(f"[bold red]✗[/] {message}")


def _human_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _total_diagnostics(report: Report) -> int:
    return len(report.errors) + sum(len(fn.diagnostics) for fn in report.functions)


def _total_constraints(report: Report) -> int:
    return sum(len(fn.contract.constraints) for fn in report.functions if fn.contract is not None)


def _diag_decorations(n_diag: int) -> tuple[str, str]:
    if n_diag == 0:
        return "bold green", "✅"
    return "bold yellow", "⚠️"


class _DiagRow(NamedTuple):
    fn_name: str | None
    code: str
    line: str | None
    message: str


def _diag_row(fn_name: str | None, diagnostic: Diagnostic) -> _DiagRow:
    return _DiagRow(
        fn_name=fn_name,
        code=diagnostic.code.value,
        line=str(diagnostic.line) if diagnostic.line is not None else None,
        message=diagnostic.message,
    )


def _collect_diagnostic_rows(report: Report) -> list[_DiagRow]:
    rows: list[_DiagRow] = [_diag_row(None, d) for d in report.errors]
    for fn in report.functions:
        rows.extend(_diag_row(fn.name, d) for d in fn.diagnostics)
    return rows


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
