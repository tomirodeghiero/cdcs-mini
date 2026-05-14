"""``cdcs-mini`` CLI entry point.

Usage::

    cdcs-mini input.py --out report.json
    cdcs-mini input.py            # JSON to stdout

Exit codes:
    0 — report generated, no diagnostics
    1 — diagnostics emitted (the report still gets written)
    2 — usage error (missing file, bad arguments)

The decorated output goes through stderr. stdout and ``--out`` keep
the JSON contract byte-for-byte so pipes don't break.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from cdcs_mini.application.report_service import ReportService
from cdcs_mini.domain.models import Report
from cdcs_mini.reporting.json_reporter import JsonReporter

__version__ = "0.1.0"


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
    args = build_parser().parse_args(argv)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    ui = _UI(quiet=args.quiet, no_color=args.no_color)
    input_path: Path = args.input

    if not input_path.is_file():
        ui.fatal(f"cdcs-mini: input file not found: {input_path}")
        return 2

    try:
        source = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        ui.fatal(f"cdcs-mini: cannot read {input_path}: {exc}")
        return 2

    ui.banner()
    file_size = input_path.stat().st_size
    ui.input_info(input_path, file_size)

    started = time.perf_counter()
    report = ReportService.default().build_report(source, filename=str(input_path))
    elapsed_ms = (time.perf_counter() - started) * 1000

    payload = JsonReporter().render(report)

    if args.out is not None:
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        sys.stdout.write(payload + "\n")

    ui.analysis_info(report, elapsed_ms)
    ui.summary(report)
    ui.diagnostics(report)
    ui.json_panel(payload)
    ui.outcome(args.out, len(payload), report)

    return 1 if _has_any_diagnostic(report) else 0


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
        n_constraints = sum(
            len(fn.contract.constraints) for fn in report.functions if fn.contract is not None
        )

        table = Table(show_header=False, box=None, padding=(0, 2), expand=False)
        table.add_column(style="bright_white")
        table.add_column()

        diag_style = "bold green" if n_diag == 0 else "bold yellow"
        diag_glyph = "✅" if n_diag == 0 else "⚠️"

        table.add_row("Functions",   Text(str(n_fn), style="bold"))
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
        rows: list[tuple[str | None, str, str | None, str]] = []
        for d in report.errors:
            rows.append((None, d.code.value, str(d.line) if d.line is not None else None, d.message))
        for fn in report.functions:
            for d in fn.diagnostics:
                rows.append(
                    (fn.name, d.code.value, str(d.line) if d.line is not None else None, d.message)
                )
        if not rows:
            return

        header = Text()
        header.append(f"  ⚠ {len(rows)} diagnostic", style="bold yellow")
        if len(rows) != 1:
            header.append("s", style="bold yellow")
        self._console.print(header)
        self._console.print()

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
        for fn_name, code, line, msg in rows:
            table.add_row(code, line or "—", msg, fn_name or "—")
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
