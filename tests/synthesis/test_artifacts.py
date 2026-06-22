from __future__ import annotations

from pathlib import Path

from cdcs_mini.synthesis.artifacts import (
    ArtifactEmitter,
    LockEntry,
    Lockfile,
    detect_stale,
    load_lock,
    save_lock,
)
from cdcs_mini.synthesis.orchestrator import SynthesisOutcome
from cdcs_mini.synthesis.prompt import PromptTarget


def _outcome(function_name: str = "parse_port") -> SynthesisOutcome:
    return SynthesisOutcome(
        target=PromptTarget(function_name=function_name, module_name="m"),
        implementation_code=f"def {function_name}(value: str) -> int:\n    return int(value)\n",
        test_code=(
            "import pytest\n"
            f"from m import {function_name}\n"
            f"def test_simple() -> None:\n    assert {function_name}('1') == 1\n"
        ),
        contract_hash="a" * 64,
        model="recorded",
        llm_calls=2,
        repair_attempts=0,
    )


def test_emit_writes_files_with_provenance_header(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text("placeholder", encoding="utf-8")
    artifact = ArtifactEmitter().emit(
        outcome=_outcome(),
        source_path=source_path,
        dest_dir=tmp_path,
        mode="strict",
    )
    impl_text = artifact.implementation_path.read_text()
    test_text = artifact.test_path.read_text()
    assert "GENERATED FILE - DO NOT EDIT MANUALLY" in impl_text
    assert "ports.py::parse_port" in impl_text
    assert f"sha256:{'a' * 64}" in impl_text
    assert "Mode: strict" in impl_text
    assert "def parse_port" in impl_text
    assert "import pytest" in test_text
    assert "def test_simple" in test_text


def test_emit_returns_lock_entry_with_body_hashes(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text("placeholder", encoding="utf-8")
    artifact = ArtifactEmitter().emit(
        outcome=_outcome(),
        source_path=source_path,
        dest_dir=tmp_path,
        mode="strict",
    )
    entry = artifact.lock_entry
    assert entry.source == "ports.py"
    assert entry.function == "parse_port"
    assert entry.contract_hash == "a" * 64
    assert len(entry.implementation_hash) == 64
    assert len(entry.test_hash) == 64


def test_lockfile_upsert_replaces_existing_entry() -> None:
    initial = Lockfile.empty().upsert(
        LockEntry(
            source="a.py",
            function="f",
            contract_hash="old",
            implementation_path="a.generated.py",
            implementation_hash="x" * 64,
            test_path="test_a.generated.py",
            test_hash="y" * 64,
            model="m",
            mode="strict",
        )
    )
    updated = initial.upsert(
        LockEntry(
            source="a.py",
            function="f",
            contract_hash="new",
            implementation_path="a.generated.py",
            implementation_hash="x" * 64,
            test_path="test_a.generated.py",
            test_hash="y" * 64,
            model="m",
            mode="strict",
        )
    )
    assert len(updated.entries) == 1
    assert updated.entries[0].contract_hash == "new"


def test_lockfile_round_trip(tmp_path: Path) -> None:
    lockfile = Lockfile.empty().upsert(
        LockEntry(
            source="a.py",
            function="f",
            contract_hash="h" * 64,
            implementation_path="a.generated.py",
            implementation_hash="x" * 64,
            test_path="test_a.generated.py",
            test_hash="y" * 64,
            model="m",
            mode="strict",
        )
    )
    path = tmp_path / "cdcs.lock"
    save_lock(lockfile, path)
    reloaded = load_lock(path)
    assert reloaded == lockfile


def test_detect_stale_flags_missing_entry(tmp_path: Path) -> None:
    stale = detect_stale(
        lockfile=Lockfile.empty(),
        expected=[("a.py", "f", "h" * 64)],
        dest_dir=tmp_path,
    )
    assert len(stale) == 1
    assert stale[0].reason == "missing"


def test_detect_stale_flags_contract_drift(tmp_path: Path) -> None:
    lockfile = Lockfile.empty().upsert(
        LockEntry(
            source="a.py",
            function="f",
            contract_hash="old" * 21 + "o",  # 64 chars
            implementation_path="a.generated.py",
            implementation_hash="x" * 64,
            test_path="test_a.generated.py",
            test_hash="y" * 64,
            model="m",
            mode="strict",
        )
    )
    stale = detect_stale(
        lockfile=lockfile,
        expected=[("a.py", "f", "new" * 21 + "n")],
        dest_dir=tmp_path,
    )
    assert len(stale) == 1
    assert stale[0].reason == "contract_drift"


def test_detect_stale_flags_manual_edit(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text("placeholder", encoding="utf-8")
    artifact = ArtifactEmitter().emit(
        outcome=_outcome(),
        source_path=source_path,
        dest_dir=tmp_path,
        mode="strict",
    )
    # Tamper with the generated impl by inserting code inside the
    # function section (between FN/END markers). Edits past the END
    # marker are out of scope for body-hash detection.
    impl_text = artifact.implementation_path.read_text()
    tampered = impl_text.replace("return int(value)", "return int(value) + 0")
    artifact.implementation_path.write_text(tampered)
    lockfile = Lockfile.empty().upsert(artifact.lock_entry)
    stale = detect_stale(
        lockfile=lockfile,
        expected=[("ports.py", "parse_port", artifact.lock_entry.contract_hash)],
        dest_dir=tmp_path,
    )
    assert any(s.reason == "manual_edit" for s in stale)


def test_detect_stale_clean_state(tmp_path: Path) -> None:
    source_path = tmp_path / "ports.py"
    source_path.write_text("placeholder", encoding="utf-8")
    artifact = ArtifactEmitter().emit(
        outcome=_outcome(),
        source_path=source_path,
        dest_dir=tmp_path,
        mode="strict",
    )
    lockfile = Lockfile.empty().upsert(artifact.lock_entry)
    stale = detect_stale(
        lockfile=lockfile,
        expected=[("ports.py", "parse_port", artifact.lock_entry.contract_hash)],
        dest_dir=tmp_path,
    )
    assert stale == ()
