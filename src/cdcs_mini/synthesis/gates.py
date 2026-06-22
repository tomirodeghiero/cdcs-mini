"""Verification gates (PDF §15).

Every gate is a pure function over a parsed AST plus the contract,
signature, and policy. They never mutate state, never touch the disk
on their own. The orchestrator runs them in order and aggregates the
results.

Two flavours:

  * **AST gates** (``StructureGate``, ``SecurityGate``, ``CalleeAllowListGate``,
    ``ComplexityGate``) — implemented inline because they're the
    non-substitutable safety net. No subprocess, no external tooling.
  * **External tool gates** — wrapped behind ``ExternalToolGate`` Protocol.
    The default impl shells out to ``ruff``, ``mypy``, ``pytest``. Tests
    stub them with no-op implementations.

The split keeps the security-critical checks in-process and the
tooling-noisy checks pluggable.
"""

from __future__ import annotations

import ast
import builtins
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

from cdcs_mini.domain.models import Contract, Signature
from cdcs_mini.synthesis.policy import SynthesisPolicy
from cdcs_mini.synthesis.prompt import PromptTarget

_PY_BUILTINS: Final[frozenset[str]] = frozenset(dir(builtins))


@dataclass(frozen=True, slots=True)
class GateFailure:
    gate: str
    message: str
    line: int | None = None

    def format(self) -> str:
        location = f"line {self.line}: " if self.line is not None else ""
        return f"[{self.gate}] {location}{self.message}"


@dataclass(frozen=True, slots=True)
class GateReport:
    failures: tuple[GateFailure, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.failures

    def merge(self, other: GateReport) -> GateReport:
        return GateReport(failures=self.failures + other.failures)


@dataclass(frozen=True, slots=True)
class Candidate:
    """Material the gates inspect together.

    Built once from the LLM output; reused by every gate so we parse the
    code exactly once.
    """

    code: str
    # ``object`` rather than ``ast.Module`` because non-Python adapters
    # carry a different parse tree shape (or none at all). The Python
    # gates below assert ``isinstance(tree, ast.Module)`` and skip out
    # cleanly otherwise so a TS-side run never trips them.
    tree: object
    target: PromptTarget
    signature: Signature
    contract: Contract
    policy: SynthesisPolicy


class Gate(Protocol):
    @property
    def name(self) -> str: ...

    def check(self, candidate: Candidate) -> GateReport: ...


# --- helpers ---------------------------------------------------------


def _find_target_function(tree: object, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    if not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _attribute_root(node: ast.expr) -> ast.Name | None:
    """Walk down an ``Attribute`` chain to the root ``Name``, if any."""
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current
    return None


def _attribute_path(node: ast.Attribute) -> str:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


# --- StructureGate ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class StructureGate:
    """Top-level shape check: target function exists with the right signature.

    Without this, a downstream test import that names the function would
    crash with a confusing AttributeError. We'd rather flag it cleanly.
    """

    name: str = "structure"

    def check(self, candidate: Candidate) -> GateReport:
        # Non-Python adapter: structural validation lives in language-specific
        # gates (eslint/tsc for TS). Skip cleanly so the chain doesn't trip.
        if not isinstance(candidate.tree, ast.Module):
            return GateReport()
        func = _find_target_function(candidate.tree, candidate.target.function_name)
        if func is None:
            return GateReport(
                failures=(
                    GateFailure(
                        gate=self.name,
                        message=(
                            f"generated code does not define {candidate.target.function_name!r}"
                        ),
                    ),
                )
            )
        failures: list[GateFailure] = []
        expected = candidate.signature
        got = _signature_param_signature(func)
        want = _expected_param_signature(expected)
        if got != want:
            failures.append(
                GateFailure(
                    gate=self.name,
                    line=func.lineno,
                    message=(f"generated signature differs from contract: got {got}, want {want}"),
                )
            )
        return GateReport(failures=tuple(failures))


def _signature_param_signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    parts = []
    for arg in func.args.args:
        annotation = "" if arg.annotation is None else ast.unparse(arg.annotation)
        parts.append(f"{arg.arg}:{annotation}")
    returns = "" if func.returns is None else ast.unparse(func.returns)
    return "(" + ",".join(parts) + ")->" + returns


def _expected_param_signature(signature: Signature) -> str:
    parts = []
    for parameter in signature.parameters:
        annotation = parameter.annotation or ""
        parts.append(f"{parameter.name}:{annotation}")
    returns = signature.returns or ""
    return "(" + ",".join(parts) + ")->" + returns


# --- SecurityGate ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class SecurityGate:
    """AST policy pass (PDF §16).

    Rejects calls to eval/exec/compile, dynamic imports, and modules
    that touch the network, filesystem, or subprocess unless allowed
    explicitly via project policy ``allowed_imports``.
    """

    name: str = "security"

    def check(self, candidate: Candidate) -> GateReport:
        if not isinstance(candidate.tree, ast.Module):
            return GateReport()
        policy = candidate.policy.verification
        allow_imports = frozenset(candidate.policy.project.allowed_imports)
        failures: list[GateFailure] = []
        for node in ast.walk(candidate.tree):
            failures.extend(self._inspect_node(node, policy, allow_imports))
        return GateReport(failures=tuple(failures))

    def _inspect_node(
        self,
        node: ast.AST,
        policy: object,
        allow_imports: frozenset[str],
    ) -> Iterable[GateFailure]:
        from cdcs_mini.synthesis.policy import VerificationPolicy  # local: avoid cycles

        assert isinstance(policy, VerificationPolicy)
        if isinstance(node, ast.Call):
            yield from self._inspect_call(node, policy)
        elif isinstance(node, ast.Import):
            yield from self._inspect_import(node, policy, allow_imports)
        elif isinstance(node, ast.ImportFrom):
            yield from self._inspect_import_from(node, policy, allow_imports)

    def _inspect_call(self, call: ast.Call, policy: object) -> Iterable[GateFailure]:
        from cdcs_mini.synthesis.policy import VerificationPolicy

        assert isinstance(policy, VerificationPolicy)
        if isinstance(call.func, ast.Name) and call.func.id in policy.forbidden_call_names:
            yield GateFailure(
                gate=self.name,
                line=call.lineno,
                message=f"forbidden call: {call.func.id}",
            )
        elif isinstance(call.func, ast.Attribute):
            path = _attribute_path(call.func)
            if path in policy.forbidden_attribute_calls:
                yield GateFailure(
                    gate=self.name,
                    line=call.lineno,
                    message=f"forbidden call: {path}",
                )

    def _inspect_import(
        self, node: ast.Import, policy: object, allow_imports: frozenset[str]
    ) -> Iterable[GateFailure]:
        for alias in node.names:
            failure = self._check_module(node.lineno, alias.name, policy, allow_imports)
            if failure is not None:
                yield failure

    def _inspect_import_from(
        self,
        node: ast.ImportFrom,
        policy: object,
        allow_imports: frozenset[str],
    ) -> Iterable[GateFailure]:
        module = node.module or ""
        if not module:
            return
        failure = self._check_module(node.lineno, module, policy, allow_imports)
        if failure is not None:
            yield failure

    def _check_module(
        self,
        lineno: int,
        module: str,
        policy: object,
        allow_imports: frozenset[str],
    ) -> GateFailure | None:
        from cdcs_mini.synthesis.policy import VerificationPolicy

        assert isinstance(policy, VerificationPolicy)
        root = module.split(".", 1)[0]
        if root in allow_imports:
            return None
        forbidden = policy.network_modules | policy.filesystem_modules | policy.subprocess_modules
        if module in forbidden or root in forbidden:
            return GateFailure(
                gate=self.name,
                line=lineno,
                message=(
                    f"forbidden import: {module} (network/filesystem/subprocess; "
                    "not in project allow_imports)"
                ),
            )
        return None


# --- CalleeAllowListGate --------------------------------------------


@dataclass(frozen=True, slots=True)
class CalleeAllowListGate:
    """Enforces declared Calls:/Reads: surface for ``self.X`` access.

    Any ``self.foo()`` or ``self.foo`` reference inside the synthesized
    function must resolve to a declared callee or attribute. This is the
    AST counterpart to the ``Calls:`` / ``Reads:`` DSL extension and is
    the safety net for class-method synthesis when the synthesizer
    doesn't see the rest of the class.
    """

    name: str = "callee-allowlist"

    def check(self, candidate: Candidate) -> GateReport:
        func = _find_target_function(candidate.tree, candidate.target.function_name)
        if func is None:
            return GateReport()
        declared_calls = {spec.qualified_name for spec in candidate.contract.calls}
        declared_reads = {spec.qualified_name for spec in candidate.contract.reads}
        # ``self`` exists as a name only if it's a declared parameter
        has_self = bool(
            candidate.signature.parameters and candidate.signature.parameters[0].name == "self"
        )
        failures: list[GateFailure] = []
        for node in ast.walk(func):
            failures.extend(self._check_node(node, declared_calls, declared_reads, has_self))
        return GateReport(failures=tuple(failures))

    def _check_node(
        self,
        node: ast.AST,
        declared_calls: set[str],
        declared_reads: set[str],
        has_self: bool,
    ) -> Iterable[GateFailure]:
        if not isinstance(node, ast.Attribute):
            return
        root = _attribute_root(node)
        if root is None or root.id != "self":
            return
        path = _attribute_path(node)
        if not has_self:
            yield GateFailure(
                gate=self.name,
                line=node.lineno,
                message=(f"references {path!r} but function has no 'self' parameter"),
            )
            return
        # In a Call context, the Attribute IS the callee. Otherwise it's an
        # attribute read. Walk-time we can't tell easily, so we accept either
        # declaration. The split between Calls/Reads is a contract concern,
        # not a synthesizer concern.
        if path in declared_calls or path in declared_reads:
            return
        yield GateFailure(
            gate=self.name,
            line=node.lineno,
            message=(f"undeclared callee/attribute: {path}. Add it to Calls: or Reads:."),
        )


# --- ComplexityGate --------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComplexityGate:
    """Cyclomatic complexity, body length, and nesting depth check.

    Pure-AST implementation — no radon dependency. The numbers come from
    counting branching constructs (``if``, ``for``, ``while``, ``case``,
    ``except``, boolean operators, comprehensions) plus a baseline of 1.
    """

    name: str = "complexity"

    def check(self, candidate: Candidate) -> GateReport:
        func = _find_target_function(candidate.tree, candidate.target.function_name)
        if func is None:
            return GateReport()
        verification = candidate.policy.verification
        failures: list[GateFailure] = []
        complexity = _cyclomatic_complexity(func)
        if complexity > verification.max_cyclomatic_complexity:
            failures.append(
                GateFailure(
                    gate=self.name,
                    line=func.lineno,
                    message=(
                        f"cyclomatic complexity {complexity} exceeds limit "
                        f"{verification.max_cyclomatic_complexity}"
                    ),
                )
            )
        lines = _function_line_count(func)
        if lines > verification.max_lines:
            failures.append(
                GateFailure(
                    gate=self.name,
                    line=func.lineno,
                    message=f"function spans {lines} lines, exceeds {verification.max_lines}",
                )
            )
        nesting = _max_nesting_depth(func)
        if nesting > verification.max_nesting_depth:
            failures.append(
                GateFailure(
                    gate=self.name,
                    line=func.lineno,
                    message=(f"nesting depth {nesting} exceeds {verification.max_nesting_depth}"),
                )
            )
        return GateReport(failures=tuple(failures))


_BRANCH_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.match_case,
    ast.Assert,
    ast.comprehension,
    ast.BoolOp,
)


def _cyclomatic_complexity(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    score = 1
    for node in ast.walk(func):
        if isinstance(node, _BRANCH_NODES):
            score += 1
    return score


def _function_line_count(func: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end: int | None = func.end_lineno
    if end is None:
        return 0
    return end - func.lineno + 1


_NESTING_NODES: Final[tuple[type[ast.AST], ...]] = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)


def _max_nesting_depth(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
) -> int:
    return _depth(func, 0)


def _depth(node: ast.AST, current: int) -> int:
    is_nesting = isinstance(node, _NESTING_NODES)
    next_level = current + 1 if is_nesting else current
    best = next_level
    for child in ast.iter_child_nodes(node):
        best = max(best, _depth(child, next_level))
    return best


# --- ExternalToolGate Protocol + default --------------------------


class ExternalToolGate(Protocol):
    """Pluggable wrapper for ruff / mypy / pytest.

    Implementations must not raise — they return a ``GateReport`` even
    on subprocess failure. Tests typically swap this for a stub.
    """

    @property
    def name(self) -> str: ...

    def check_files(self, *, source_file: Path, test_file: Path) -> GateReport: ...


@dataclass(frozen=True, slots=True)
class RuffCheckGate:
    """``ruff check`` over the generated source + test file."""

    name: str = "ruff-check"

    def check_files(self, *, source_file: Path, test_file: Path) -> GateReport:
        return _run_tool(
            self.name,
            args=("ruff", "check", str(source_file), str(test_file)),
            success_code=0,
        )


@dataclass(frozen=True, slots=True)
class MypyGate:
    name: str = "mypy"

    def check_files(self, *, source_file: Path, test_file: Path) -> GateReport:
        return _run_tool(
            self.name,
            args=("mypy", "--strict", str(source_file), str(test_file)),
            success_code=0,
        )


@dataclass(frozen=True, slots=True)
class PytestGate:
    name: str = "pytest"

    def check_files(self, *, source_file: Path, test_file: Path) -> GateReport:
        _ = source_file  # pytest discovers via the test file path
        return _run_tool(
            self.name,
            args=("pytest", "-q", "-x", str(test_file)),
            success_code=0,
        )


def _run_tool(name: str, *, args: tuple[str, ...], success_code: int) -> GateReport:
    try:
        # ``check=False`` because non-zero exit is the failure signal, not an exception.
        completed = subprocess.run(args, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return GateReport(
            failures=(
                GateFailure(
                    gate=name,
                    message=f"{args[0]} not installed; skip-or-install required",
                ),
            )
        )
    if completed.returncode == success_code:
        return GateReport()
    output = (completed.stdout + "\n" + completed.stderr).strip()
    return GateReport(
        failures=(
            GateFailure(
                gate=name,
                message=output or f"{args[0]} failed with exit code {completed.returncode}",
            ),
        )
    )


# --- gate chain factory ---------------------------------------------


@dataclass(frozen=True, slots=True)
class GateChain:
    """Ordered chain of in-process AST gates.

    External-tool gates are run separately by the orchestrator because
    they operate on files on disk, not the in-memory candidate. Keeping
    them out of this chain makes unit tests trivial.
    """

    gates: tuple[Gate, ...] = field(default_factory=lambda: _default_gates())

    def run(self, candidate: Candidate) -> GateReport:
        report = GateReport()
        for gate in self.gates:
            report = report.merge(gate.check(candidate))
        return report


def _default_gates() -> tuple[Gate, ...]:
    # Build via a List[Gate] so each element widens to Gate individually;
    # otherwise mypy's invariant tuple typing rejects the heterogeneous
    # tuple of concrete gate classes.
    gates: list[Gate] = [
        StructureGate(),
        SecurityGate(),
        CalleeAllowListGate(),
        ComplexityGate(),
    ]
    return tuple(gates)


# Reference helpers re-exported for callers that want builtin matching.
KNOWN_BUILTINS: Final[frozenset[str]] = _PY_BUILTINS
