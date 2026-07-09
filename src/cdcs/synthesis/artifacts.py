"""Generated-artifact emission and provenance (PDF §10).

Writes ``foo.generated.py``, ``test_foo.generated.py``, and updates
``cdcs.lock`` with one entry per synthesized function. The lock carries
both:

  * ``contract_hash`` — sha256 over the canonical prompt payload. Lets
    CI detect contracts that drifted since the last regen.
  * ``implementation_hash`` / ``test_hash`` — sha256 over the body of
    each generated file. Lets CI detect manual edits to generated files.

The lock format is JSON with stable key order — same input gives the
same bytes, so the file behaves nicely in code review and merges.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from cdcs.synthesis.orchestrator import SynthesisOutcome

LOCK_VERSION: Final[str] = "0.1.0"
GENERATOR_VERSION: Final[str] = "cdcs 0.1.0"
LOCK_FILENAME: Final[str] = "cdcs.lock"

_DO_NOT_EDIT_BANNER: Final[str] = (
    "# GENERATED FILE - DO NOT EDIT MANUALLY\n"
    "# Regeneration: change the @generate contract in the source file and "
    "re-run `cdcs compile`.\n"
)


@dataclass(frozen=True, slots=True)
class LockEntry:
    source: str  # relative path to source file
    function: str  # function name
    contract_hash: str  # sha256 of canonical prompt payload
    implementation_path: str
    implementation_hash: str  # sha256 of generated impl body
    test_path: str
    test_hash: str  # sha256 of generated test body
    model: str
    mode: str

    def to_dict(self) -> dict[str, str]:
        # Explicit dict shape; consumers parse it for the lock file
        return {
            "source": self.source,
            "function": self.function,
            "contract_hash": self.contract_hash,
            "implementation_path": self.implementation_path,
            "implementation_hash": self.implementation_hash,
            "test_path": self.test_path,
            "test_hash": self.test_hash,
            "model": self.model,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> LockEntry:
        return cls(
            source=data["source"],
            function=data["function"],
            contract_hash=data["contract_hash"],
            implementation_path=data["implementation_path"],
            implementation_hash=data["implementation_hash"],
            test_path=data["test_path"],
            test_hash=data["test_hash"],
            model=data["model"],
            mode=data["mode"],
        )


@dataclass(frozen=True, slots=True)
class Lockfile:
    version: str
    generator: str
    entries: tuple[LockEntry, ...]

    @classmethod
    def empty(cls) -> Lockfile:
        return cls(version=LOCK_VERSION, generator=GENERATOR_VERSION, entries=())

    def to_json(self) -> str:
        body = {
            "version": self.version,
            "generator": self.generator,
            "entries": [entry.to_dict() for entry in self.entries],
        }
        return json.dumps(body, indent=2, sort_keys=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Lockfile:
        data = json.loads(text)
        entries = tuple(LockEntry.from_dict(e) for e in data.get("entries", []))
        return cls(
            version=data.get("version", LOCK_VERSION),
            generator=data.get("generator", GENERATOR_VERSION),
            entries=entries,
        )

    def upsert(self, entry: LockEntry) -> Lockfile:
        replaced = False
        new_entries: list[LockEntry] = []
        for existing in self.entries:
            if existing.source == entry.source and existing.function == entry.function:
                new_entries.append(entry)
                replaced = True
            else:
                new_entries.append(existing)
        if not replaced:
            new_entries.append(entry)
        # Stable order: sort by (source, function)
        new_entries.sort(key=lambda e: (e.source, e.function))
        return Lockfile(version=self.version, generator=self.generator, entries=tuple(new_entries))

    def find(self, *, source: str, function: str) -> LockEntry | None:
        for entry in self.entries:
            if entry.source == source and entry.function == function:
                return entry
        return None


# --- emission --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmittedArtifact:
    implementation_path: Path
    test_path: Path
    lock_entry: LockEntry


@dataclass(frozen=True, slots=True)
class ArtifactEmitter:
    """Writes generated files + updates the lock file.

    The emitter is the only component in the synthesis pipeline that
    touches the filesystem. Keeping that responsibility isolated makes
    everything upstream pure and testable.

    ``impl_suffix`` / ``test_suffix`` come from the active
    :class:`~cdcs.language.base.LanguageAdapter`. Defaults keep the
    Python convention so legacy ``ArtifactEmitter()`` calls in tests
    continue to work unchanged.
    """

    impl_suffix: str = "_generated.py"
    test_suffix: str = "_generated.py"

    def emit(
        self,
        *,
        outcome: SynthesisOutcome,
        source_path: Path,
        dest_dir: Path,
        mode: str,
    ) -> EmittedArtifact:
        """Append the function's section to the module's impl/test files.

        Multi-function source files share a single ``{stem}.generated.py``
        output. The first call writes the preamble + first section; later
        calls append a new section guarded by ``# === FN <name> ===``
        markers. Callers that want a clean slate per compile run should
        remove the target files first (the SynthesisService does this).
        """
        impl_path = dest_dir / f"{source_path.stem}{self.impl_suffix}"
        # Tests get the conventional ``test_`` prefix for pytest and a
        # neutral one for vitest — the suffix decides which.
        test_path = dest_dir / f"{_test_filename(source_path.stem, self.test_suffix)}"
        impl_body = outcome.implementation_code.rstrip() + "\n"
        test_body = outcome.test_code.rstrip() + "\n"
        _append_section(
            path=impl_path,
            source_path=source_path,
            mode=mode,
            outcome=outcome,
            body=impl_body,
        )
        _append_section(
            path=test_path,
            source_path=source_path,
            mode=mode,
            outcome=outcome,
            body=test_body,
        )
        entry = LockEntry(
            source=source_path.name,
            function=outcome.target.function_name,
            contract_hash=outcome.contract_hash,
            implementation_path=impl_path.name,
            implementation_hash=_sha256(impl_body),
            test_path=test_path.name,
            test_hash=_sha256(test_body),
            model=outcome.model,
            mode=mode,
        )
        return EmittedArtifact(
            implementation_path=impl_path,
            test_path=test_path,
            lock_entry=entry,
        )


def _test_filename(stem: str, test_suffix: str) -> str:
    """Pick the test file name that matches the language's runner.

    Vitest discovers ``*.test.ts`` files; a leading ``test_`` would be
    redundant noise. Pytest discovers ``test_*.py``; the prefix is what
    triggers collection. We branch on whether the suffix carries the
    ``.test.`` infix.
    """
    if ".test." in test_suffix:
        return f"{stem}{test_suffix}"
    return f"test_{stem}{test_suffix}"


def _append_section(
    *,
    path: Path,
    source_path: Path,
    mode: str,
    outcome: SynthesisOutcome,
    body: str,
) -> None:
    name = outcome.target.function_name
    section = (
        f"# === FN {name} ===\n"
        + f"# Source: {source_path.name}::{name}\n"
        + f"# Source contract hash: sha256:{outcome.contract_hash}\n"
        + f"# Model: {outcome.model}\n"
        + "\n"
        + body
        + f"# === END {name} ===\n"
    )
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing.rstrip() + "\n\n" + section, encoding="utf-8")
        return
    preamble = (
        _DO_NOT_EDIT_BANNER
        + f"# Source: {source_path.name}\n"
        + f"# Generator: {GENERATOR_VERSION}\n"
        + f"# Mode: {mode}\n"
        + "\n"
    )
    path.write_text(preamble + section, encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- lock IO --------------------------------------------------------


def load_lock(path: Path) -> Lockfile:
    if not path.is_file():
        return Lockfile.empty()
    return Lockfile.from_json(path.read_text(encoding="utf-8"))


def save_lock(lockfile: Lockfile, path: Path) -> None:
    path.write_text(lockfile.to_json(), encoding="utf-8")


# --- staleness detection (--check mode) ----------------------------


StaleReason = Literal["missing", "contract_drift", "manual_edit", "absent_file"]


@dataclass(frozen=True, slots=True)
class StaleArtifact:
    source: str
    function: str
    reason: StaleReason
    detail: str


def detect_stale(
    *,
    lockfile: Lockfile,
    expected: Sequence[tuple[str, str, str]],  # (source, function, contract_hash)
    dest_dir: Path,
) -> tuple[StaleArtifact, ...]:
    """Compare lock + actual files against the current contracts.

    Returns one ``StaleArtifact`` per drift. Empty tuple → CI is green.
    Each ``expected`` triple is what the current contracts say should
    be in the lock. Entries in the lock that don't appear in
    ``expected`` are silently ignored — they may belong to a different
    source file processed elsewhere.
    """
    stale: list[StaleArtifact] = []
    lock_index = {(e.source, e.function): e for e in lockfile.entries}
    for source, function, current_hash in expected:
        entry = lock_index.get((source, function))
        if entry is None:
            stale.append(
                StaleArtifact(
                    source=source,
                    function=function,
                    reason="missing",
                    detail="no lock entry; run `cdcs compile`",
                )
            )
            continue
        if entry.contract_hash != current_hash:
            stale.append(
                StaleArtifact(
                    source=source,
                    function=function,
                    reason="contract_drift",
                    detail=(
                        f"contract changed since regen "
                        f"(lock={entry.contract_hash[:12]}, "
                        f"current={current_hash[:12]})"
                    ),
                )
            )
            continue
        stale.extend(_detect_file_drift(entry=entry, dest_dir=dest_dir))
    return tuple(stale)


def _detect_file_drift(*, entry: LockEntry, dest_dir: Path) -> Iterable[StaleArtifact]:
    impl_path = dest_dir / entry.implementation_path
    test_path = dest_dir / entry.test_path
    if not impl_path.is_file():
        yield StaleArtifact(
            source=entry.source,
            function=entry.function,
            reason="absent_file",
            detail=f"generated impl missing: {impl_path.name}",
        )
        return
    if not test_path.is_file():
        yield StaleArtifact(
            source=entry.source,
            function=entry.function,
            reason="absent_file",
            detail=f"generated tests missing: {test_path.name}",
        )
        return
    impl_body = _extract_section(impl_path.read_text(encoding="utf-8"), entry.function)
    test_body = _extract_section(test_path.read_text(encoding="utf-8"), entry.function)
    if _sha256(impl_body) != entry.implementation_hash:
        yield StaleArtifact(
            source=entry.source,
            function=entry.function,
            reason="manual_edit",
            detail=f"impl body changed manually: {impl_path.name}",
        )
    if _sha256(test_body) != entry.test_hash:
        yield StaleArtifact(
            source=entry.source,
            function=entry.function,
            reason="manual_edit",
            detail=f"test body changed manually: {test_path.name}",
        )


def _extract_section(text: str, function_name: str) -> str:
    """Return just the body of one function's section in a generated file.

    Sections are delimited by ``# === FN <name> ===`` / ``# === END
    <name> ===`` markers. The body is everything between the section's
    blank line (after its header comments) and the END marker. Returning
    only this slice makes per-function hashes survive co-tenancy with
    other generated functions in the same file.
    """
    start_marker = f"# === FN {function_name} ===\n"
    end_marker = f"# === END {function_name} ===\n"
    start = text.find(start_marker)
    end = text.find(end_marker, start) if start != -1 else -1
    if start == -1 or end == -1:
        return text
    section_text = text[start + len(start_marker) : end]
    # Strip the per-section header (# Source / # Source contract hash /
    # # Model lines + the blank line that separates header from body).
    lines = section_text.splitlines(keepends=True)
    index = 0
    while index < len(lines) and lines[index].startswith("#"):
        index += 1
    while index < len(lines) and lines[index].strip() == "":
        index += 1
        break
    return "".join(lines[index:])
