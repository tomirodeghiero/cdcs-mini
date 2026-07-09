"""High-level compile/check workflow (PDF §6 end-to-end).

Glues every stage together:

  parse source                (SourceParser)
   -> parse @generate DSL     (DSLParser)
   -> validate contract        (ContractValidator chain)
   -> [abort if any diagnostic]
   -> synthesize impl + tests  (SynthesisOrchestrator)
   -> emit files               (ArtifactEmitter)
   -> update lock              (Lockfile)

``check`` mode does everything up to "validate contract", then compares
the current contract hashes against the lock instead of calling the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cdcs.application.report_service import ReportService
from cdcs.domain.diagnostics import Diagnostic
from cdcs.domain.models import Contract, FunctionReport
from cdcs.synthesis.artifacts import (
    ArtifactEmitter,
    Lockfile,
    StaleArtifact,
    detect_stale,
)
from cdcs.synthesis.orchestrator import (
    SynthesisFailure,
    SynthesisOrchestrator,
    SynthesisOutcome,
    contract_hash,
)
from cdcs.synthesis.policy import SynthesisPolicy
from cdcs.synthesis.prompt import PromptBuilder, PromptTarget


@dataclass(frozen=True, slots=True)
class CompiledFunction:
    function_name: str
    line: int
    status: Literal["ok", "error", "skipped"]
    outcome: SynthesisOutcome | None = None
    failure: SynthesisFailure | None = None
    upstream_diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class CompilationReport:
    source_path: Path
    functions: tuple[CompiledFunction, ...]
    lockfile: Lockfile

    @property
    def has_errors(self) -> bool:
        return any(fn.status == "error" for fn in self.functions)


@dataclass(frozen=True, slots=True)
class SynthesisService:
    report_service: ReportService
    orchestrator: SynthesisOrchestrator
    emitter: ArtifactEmitter = field(default_factory=ArtifactEmitter)
    policy: SynthesisPolicy = field(default_factory=SynthesisPolicy.strict_default)

    # --- compile ----------------------------------------------------

    def compile(
        self,
        *,
        source: str,
        source_path: Path,
        dest_dir: Path | None,
        lockfile: Lockfile,
    ) -> CompilationReport:
        """Compile every @generate function in ``source``.

        When ``dest_dir`` is ``None`` the orchestrator still runs and the
        outcome (impl + test code, contract hash, model info) is exposed
        through ``CompilationReport.functions[].outcome``, but **nothing
        is written to disk** and the lock is not updated. This is the
        mode the HTTP layer uses — it returns the synthesized code to
        the client in-memory, no FS side effects.
        """
        report = self.report_service.build_report(source, filename=str(source_path))
        compiled: list[CompiledFunction] = []
        updated = lockfile
        # Bail at the source level if syntax error
        if report.errors:
            return CompilationReport(
                source_path=source_path,
                functions=(
                    CompiledFunction(
                        function_name="<source>",
                        line=0,
                        status="error",
                        upstream_diagnostics=report.errors,
                    ),
                ),
                lockfile=updated,
            )
        # Clean slate: emit() appends per function, so stale bodies from a
        # previous run would otherwise pile up below the new ones. Use the
        # emitter's own suffixes so this stays correct for any language.
        if dest_dir is not None:
            impl_name = f"{source_path.stem}{self.emitter.impl_suffix}"
            test_name = _test_filename_for(source_path.stem, self.emitter.test_suffix)
            for name in (impl_name, test_name):
                (dest_dir / name).unlink(missing_ok=True)
        for fn in report.functions:
            compiled_fn, updated = self._compile_function(
                fn=fn,
                source_path=source_path,
                dest_dir=dest_dir,
                lockfile=updated,
            )
            compiled.append(compiled_fn)
        return CompilationReport(
            source_path=source_path,
            functions=tuple(compiled),
            lockfile=updated,
        )

    def _compile_function(
        self,
        *,
        fn: FunctionReport,
        source_path: Path,
        dest_dir: Path | None,
        lockfile: Lockfile,
    ) -> tuple[CompiledFunction, Lockfile]:
        if fn.diagnostics or fn.contract is None:
            return (
                CompiledFunction(
                    function_name=fn.name,
                    line=fn.line,
                    status="skipped" if fn.contract is None else "error",
                    upstream_diagnostics=fn.diagnostics,
                ),
                lockfile,
            )
        target = PromptTarget(
            function_name=fn.name,
            module_name=f"{source_path.stem}_generated",
        )
        result = self.orchestrator.synthesize(
            target=target,
            signature=fn.signature,
            contract=fn.contract,
        )
        if isinstance(result, SynthesisFailure):
            return (
                CompiledFunction(
                    function_name=fn.name,
                    line=fn.line,
                    status="error",
                    failure=result,
                ),
                lockfile,
            )
        next_lock = lockfile
        if dest_dir is not None:
            artifact = self.emitter.emit(
                outcome=result,
                source_path=source_path,
                dest_dir=dest_dir,
                mode=self.policy.generation.name,
            )
            next_lock = lockfile.upsert(artifact.lock_entry)
        return (
            CompiledFunction(
                function_name=fn.name,
                line=fn.line,
                status="ok",
                outcome=result,
            ),
            next_lock,
        )

    # --- check ------------------------------------------------------

    def check(
        self,
        *,
        source: str,
        source_path: Path,
        dest_dir: Path,
        lockfile: Lockfile,
    ) -> tuple[StaleArtifact, ...]:
        """Compute expected hashes from the current contracts and detect drift.

        Does NOT call the LLM. Designed to run in CI to refuse merges
        when generated artifacts are out of sync with source contracts.
        """
        report = self.report_service.build_report(source, filename=str(source_path))
        if report.errors:
            # Surface source-level errors as stale entries so CI sees them
            return tuple(
                StaleArtifact(
                    source=source_path.name,
                    function="<source>",
                    reason="missing",
                    detail=diagnostic.format(),
                )
                for diagnostic in report.errors
            )
        builder = PromptBuilder(policy=self.policy)
        expected: list[tuple[str, str, str]] = []
        upstream: list[StaleArtifact] = []
        for fn in report.functions:
            if fn.diagnostics or fn.contract is None:
                upstream.extend(_upstream_stale(source_path, fn))
                continue
            target = PromptTarget(
                function_name=fn.name,
                module_name=f"{source_path.stem}_generated",
            )
            h = _hash_with_builder(builder, target, fn.signature, fn.contract)
            expected.append((source_path.name, fn.name, h))
        return tuple(upstream) + detect_stale(
            lockfile=lockfile, expected=expected, dest_dir=dest_dir
        )


def _test_filename_for(stem: str, test_suffix: str) -> str:
    """Mirror ``ArtifactEmitter._test_filename`` for the cleanup step.

    Vitest uses ``foo.test.ts``; pytest uses ``test_foo.py``. The suffix
    decides which.
    """
    if ".test." in test_suffix:
        return f"{stem}{test_suffix}"
    return f"test_{stem}{test_suffix}"


def _hash_with_builder(
    builder: PromptBuilder, target: PromptTarget, signature: object, contract: Contract
) -> str:
    # Indirection so the type checker is happy with the explicit signature type
    from cdcs.domain.models import Signature  # local import to avoid cycles

    assert isinstance(signature, Signature)
    return contract_hash(target, signature, contract, builder.policy)


def _upstream_stale(source_path: Path, fn: FunctionReport) -> list[StaleArtifact]:
    if not fn.diagnostics:
        return []
    return [
        StaleArtifact(
            source=source_path.name,
            function=fn.name,
            reason="missing",
            detail=diagnostic.format(),
        )
        for diagnostic in fn.diagnostics
    ]
