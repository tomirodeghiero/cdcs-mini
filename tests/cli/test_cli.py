from __future__ import annotations

import json
from pathlib import Path

import pytest

from cdcs_mini.cli import main


def test_cli_writes_report_file(tmp_path: Path, fixtures_dir: Path) -> None:
    out = tmp_path / "report.json"
    exit_code = main([str(fixtures_dir / "valid_input.py"), "--out", str(out), "--quiet"])

    assert exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["functions"][0]["name"] == "parse_port"
    assert payload["errors"] == []


def test_cli_prints_to_stdout_when_out_omitted(
    fixtures_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([str(fixtures_dir / "valid_input.py"), "--quiet"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["functions"][0]["status"] == "ok"


def test_cli_returns_one_when_diagnostics_emitted(
    fixtures_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([str(fixtures_dir / "unknown_parameter.py"), "--quiet"])

    captured = capsys.readouterr()
    assert exit_code == 1
    payload = json.loads(captured.out)
    assert payload["functions"][0]["status"] == "error"


def test_cli_returns_two_for_missing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "nope.py"
    exit_code = main([str(missing)])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "not found" in captured.err


def test_cli_renders_diagnostics_to_stderr(
    fixtures_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main([str(fixtures_dir / "unknown_parameter.py")])
    captured = capsys.readouterr()
    assert "InconsistentPromptError" in captured.err
