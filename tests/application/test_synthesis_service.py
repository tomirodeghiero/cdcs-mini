from __future__ import annotations

from pathlib import Path

from cdcs.application.report_service import ReportService
from cdcs.application.synthesis_service import SynthesisService
from cdcs.synthesis.artifacts import LOCK_FILENAME, ArtifactEmitter, Lockfile
from cdcs.synthesis.llm import RecordedLLMClient
from cdcs.synthesis.orchestrator import SynthesisOrchestrator
from cdcs.synthesis.policy import SynthesisPolicy

VALID_SOURCE = '''\
def parse_port(value: str) -> int:
    """@generate
    behavior:
      strip(value)
      require value matches digits
      require 1 <= int(value) <= 65535
      return int(value)
    examples:
      parse_port("80") == 80
      parse_port("443") == 443
      parse_port("0") raises ValueError
    constraints:
      no_imports
    """
    ...
'''

GOOD_IMPL = """\
def parse_port(value: str) -> int:
    stripped = value.strip()
    if not stripped.isdigit():
        raise ValueError("port must be base-10 digits")
    port = int(stripped)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return port
"""

GOOD_TESTS = """\
import pytest
from ports_generated import parse_port

def test_valid() -> None:
    assert parse_port("80") == 80

def test_invalid() -> None:
    with pytest.raises(ValueError):
        parse_port("0")
"""


def _build_service(llm: RecordedLLMClient) -> SynthesisService:
    return SynthesisService(
        report_service=ReportService.default(),
        orchestrator=SynthesisOrchestrator.with_llm(llm),
        emitter=ArtifactEmitter(),
        policy=SynthesisPolicy.strict_default(),
    )


def test_compile_writes_generated_files_and_updates_lock(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text(VALID_SOURCE, encoding="utf-8")
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    llm.register_kind("test", GOOD_TESTS)
    service = _build_service(llm)
    report = service.compile(
        source=VALID_SOURCE,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=Lockfile.empty(),
    )
    assert not report.has_errors
    assert (tmp_path / "ports_generated.py").is_file()
    assert (tmp_path / "test_ports_generated.py").is_file()
    assert len(report.lockfile.entries) == 1


def test_compile_aborts_per_function_when_upstream_diagnostics_exist(
    tmp_path: Path,
) -> None:
    bad_source = '''\
def total(values: list[int]) -> int:
    """@generate
    Sum all numbers in nums.
    examples:
      total([1, 2]) == 3
    """
    ...
'''
    source_path = tmp_path / "bad.py"
    source_path.write_text(bad_source, encoding="utf-8")
    llm = RecordedLLMClient()  # never gets called
    service = _build_service(llm)
    report = service.compile(
        source=bad_source,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=Lockfile.empty(),
    )
    assert report.has_errors
    # The LLM must NOT have been called for the error function
    assert llm.calls == []


def test_check_clean_when_lock_matches_current_contract(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text(VALID_SOURCE, encoding="utf-8")
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    llm.register_kind("test", GOOD_TESTS)
    service = _build_service(llm)
    # Compile once to generate everything
    report = service.compile(
        source=VALID_SOURCE,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=Lockfile.empty(),
    )
    stale = service.check(
        source=VALID_SOURCE,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=report.lockfile,
    )
    assert stale == ()


def test_check_detects_contract_drift_after_source_edit(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text(VALID_SOURCE, encoding="utf-8")
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    llm.register_kind("test", GOOD_TESTS)
    service = _build_service(llm)
    report = service.compile(
        source=VALID_SOURCE,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=Lockfile.empty(),
    )
    # Now edit the source contract — same name, different behavior
    edited = VALID_SOURCE.replace("return int(value)", "return int(value) + 1")
    stale = service.check(
        source=edited,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=report.lockfile,
    )
    assert len(stale) == 1
    assert stale[0].reason == "contract_drift"


def test_lockfile_round_trip_through_compile(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text(VALID_SOURCE, encoding="utf-8")
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    llm.register_kind("test", GOOD_TESTS)
    service = _build_service(llm)
    report = service.compile(
        source=VALID_SOURCE,
        source_path=source_path,
        dest_dir=tmp_path,
        lockfile=Lockfile.empty(),
    )
    # Persist lock and reload — same content
    lock_path = tmp_path / LOCK_FILENAME
    lock_path.write_text(report.lockfile.to_json(), encoding="utf-8")
    reloaded = Lockfile.from_json(lock_path.read_text(encoding="utf-8"))
    assert reloaded == report.lockfile
