"""Rich-based console UI for the CLI.

Owns every byte of human-facing output. ``ConsoleUI`` is the only thing
in the CLI that touches a terminal; the driver passes it down so the
business logic stays free of presentation concerns. This separation is
what makes the driver testable without painting goldens against ANSI
escape sequences.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from cdcs.application.synthesis_service import CompilationReport, CompiledFunction
from cdcs.cli._version import __version__
from cdcs.domain.diagnostics import Diagnostic
from cdcs.domain.models import Report
from cdcs.synthesis.artifacts import StaleArtifact


class ConsoleUI:
    """Thin rich wrapper. Everything lands on stderr. ``--quiet`` mutes
    the chrome but never the fatal-error console — those have to be
    readable always.
    """

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
        title.append("🚀 cdcs ", style="bold cyan")
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

        bad = has_any_diagnostic(report)
        exit_text = Text()
        exit_text.append("  → ", style="dim")
        exit_text.append("exit ", style="bold")
        exit_text.append("1" if bad else "0", style="bold yellow" if bad else "bold green")
        self._console.print(exit_text)
        self._console.print()

    # --- compile / check chrome ------------------------------------

    def compile_banner(self, input_path: Path, dest_dir: Path, model: str) -> None:
        title = Text()
        title.append("🛠  cdcs compile ", style="bold cyan")
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
        title.append("🔎 cdcs check ", style="bold cyan")
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


# --- pure helpers (no rich state) -----------------------------------


def has_any_diagnostic(report: Report) -> bool:
    return bool(report.errors) or any(fn.diagnostics for fn in report.functions)


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


__all__ = ["ConsoleUI", "has_any_diagnostic"]
