"""Synthesis orchestrator (PDF §6 + §9).

Owns the order of operations:

1. Build the augmented implementation prompt.
2. Call the LLM. Parse the result.
3. Run AST gates (structure, security, callee allow-list, complexity).
4. If any gate fails, build a repair prompt (gates + previous code) and
   try again. Up to ``max_repair_iterations``.
5. Once the impl is clean, build a SEPARATE test prompt that does **not**
   contain the implementation (PDF §9). Call the LLM. Parse the result.
6. Sanity-check the test file (imports the target, has at least one
   ``test_`` function).
7. Return a ``SynthesisOutcome`` carrying impl code, test code, and
   provenance metadata. On budget exhaustion, return a
   ``SynthesisFailure`` carrying the matching compiler-style error code.

External-tool gates (ruff / mypy / pytest) run **after** the
orchestrator finishes, because they operate on files on disk — see the
artifact emitter and the CLI driver.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.domain.models import Contract, Signature
from cdcs_mini.synthesis.gates import (
    Candidate,
    GateChain,
    GateFailure,
)
from cdcs_mini.synthesis.llm import DEFAULT_MODEL, LLMClient, LLMError
from cdcs_mini.synthesis.policy import SynthesisPolicy
from cdcs_mini.synthesis.prompt import Prompt, PromptBuilder, PromptTarget


@dataclass(frozen=True, slots=True)
class SynthesisOutcome:
    target: PromptTarget
    implementation_code: str
    test_code: str
    contract_hash: str
    model: str
    llm_calls: int
    repair_attempts: int


@dataclass(frozen=True, slots=True)
class SynthesisFailure:
    target: PromptTarget
    code: DiagnosticCode
    message: str
    detail: tuple[GateFailure, ...] = ()
    # When the impl succeeded but the test loop hit ``EXCEEDED_TEST_ITERATIONS``,
    # we still know the impl is good — surface it so the UI can show what the
    # LLM produced even though we couldn't lock in a test pair.
    partial_implementation: str | None = None


SynthesisResult = SynthesisOutcome | SynthesisFailure


@dataclass(slots=True)
class _RunState:
    """Mutable counters scoped to one synthesize() call."""

    llm_calls: int = 0
    repair_attempts: int = 0


@dataclass(frozen=True, slots=True)
class SynthesisOrchestrator:
    llm: LLMClient
    policy: SynthesisPolicy = field(default_factory=SynthesisPolicy.strict_default)
    gate_chain: GateChain = field(default_factory=GateChain)
    prompt_builder: PromptBuilder = field(default_factory=PromptBuilder.default)
    # Validates LLM output is syntactically a module in the host language.
    # Returns ``(tree, None)`` on success; ``(None, message)`` on failure.
    # ``tree`` is passed to the gate chain via :class:`Candidate`.``tree``;
    # downstream gates can ignore it when they don't need an AST (TS today).
    code_parser: Callable[[str], tuple[object | None, str | None]] = field(
        default=lambda code: _try_parse(code), repr=False
    )
    # Language-specific sanity check for the *test* output: must look like
    # a test module that imports the target. Receives the raw stripped
    # output (post fence-strip) plus the target. Returns a non-empty
    # failure tuple to trigger a repair iteration.
    test_sanity_checker: Callable[[str, PromptTarget], tuple[GateFailure, ...]] = field(
        default=lambda _raw, _target: (), repr=False
    )

    @classmethod
    def with_llm(
        cls,
        llm: LLMClient,
        *,
        prompt_builder: PromptBuilder | None = None,
        gate_chain: GateChain | None = None,
        code_parser: Callable[[str], tuple[object | None, str | None]] | None = None,
        test_sanity_checker: Callable[[str, PromptTarget], tuple[GateFailure, ...]] | None = None,
    ) -> SynthesisOrchestrator:
        kwargs: dict[str, object] = {"llm": llm}
        if prompt_builder is not None:
            kwargs["prompt_builder"] = prompt_builder
        if gate_chain is not None:
            kwargs["gate_chain"] = gate_chain
        if code_parser is not None:
            kwargs["code_parser"] = code_parser
        if test_sanity_checker is not None:
            kwargs["test_sanity_checker"] = test_sanity_checker
        return cls(**kwargs)  # type: ignore[arg-type]

    # --- main entry --------------------------------------------------

    def synthesize(
        self, *, target: PromptTarget, signature: Signature, contract: Contract
    ) -> SynthesisResult:
        state = _RunState()
        impl_result = self._synthesize_implementation(
            target=target, signature=signature, contract=contract, state=state
        )
        if isinstance(impl_result, SynthesisFailure):
            return impl_result
        impl_code = impl_result
        test_result = self._synthesize_tests(
            target=target, signature=signature, contract=contract, state=state
        )
        if isinstance(test_result, SynthesisFailure):
            # Impl succeeded — attach it to the failure so the UI can still
            # show the LLM's work even when tests didn't lock in.
            return _attach_impl_to_failure(test_result, impl_code)
        test_code = test_result
        return SynthesisOutcome(
            target=target,
            implementation_code=impl_code,
            test_code=test_code,
            contract_hash=contract_hash(target, signature, contract, self.policy),
            model=self.llm.model,
            llm_calls=state.llm_calls,
            repair_attempts=state.repair_attempts,
        )

    # --- implementation loop -----------------------------------------

    def _synthesize_implementation(
        self,
        *,
        target: PromptTarget,
        signature: Signature,
        contract: Contract,
        state: _RunState,
    ) -> str | SynthesisFailure:
        prompt = self.prompt_builder.build_implementation_prompt(
            target=target, signature=signature, contract=contract
        )
        last_code = ""
        last_failures: tuple[GateFailure, ...] = ()
        for attempt in range(self.policy.max_repair_iterations + 1):
            try:
                raw = self.llm.complete(prompt)
            except LLMError as exc:
                return SynthesisFailure(
                    target=target,
                    code=DiagnosticCode.LLM_CALL_FAILED,
                    message=f"LLM call failed: {exc}",
                )
            state.llm_calls += 1
            raw = _strip_markdown_fence(raw)
            tree, parse_failure = self.code_parser(raw)
            if tree is None:
                last_code = raw
                last_failures = (
                    GateFailure(gate="parse", message=parse_failure or "syntax error"),
                )
            else:
                candidate = Candidate(
                    code=raw,
                    tree=tree,
                    target=target,
                    signature=signature,
                    contract=contract,
                    policy=self.policy,
                )
                report = self.gate_chain.run(candidate)
                if report.passed:
                    return raw
                last_code = raw
                last_failures = report.failures
            # Out of attempts → bail. Distinguish complexity from generic
            # gate failure so the diagnostic code matches PDF §8.
            if attempt == self.policy.max_repair_iterations:
                return _failure_from_gate_report(target, last_failures)
            # Build a repair prompt for the next iteration
            failures_text = "\n".join(f.format() for f in last_failures)
            prompt = self.prompt_builder.build_repair_prompt(
                target=target,
                signature=signature,
                contract=contract,
                previous_code=last_code,
                failures=failures_text,
            )
            state.repair_attempts += 1
        # Unreachable: the loop returns or fails by attempt N
        return SynthesisFailure(  # pragma: no cover
            target=target,
            code=DiagnosticCode.EXCEEDED_LINT_ITERATIONS,
            message="repair loop exited without producing code",
        )

    # --- test loop --------------------------------------------------

    def _synthesize_tests(
        self,
        *,
        target: PromptTarget,
        signature: Signature,
        contract: Contract,
        state: _RunState,
    ) -> str | SynthesisFailure:
        prompt = self.prompt_builder.build_test_prompt(
            target=target, signature=signature, contract=contract
        )
        for attempt in range(self.policy.max_repair_iterations + 1):
            try:
                raw = self.llm.complete(prompt)
            except LLMError as exc:
                return SynthesisFailure(
                    target=target,
                    code=DiagnosticCode.LLM_CALL_FAILED,
                    message=f"LLM call failed during test synthesis: {exc}",
                )
            state.llm_calls += 1
            raw = _strip_markdown_fence(raw)
            tree, parse_failure = self.code_parser(raw)
            failures = _test_sanity_failures(tree, parse_failure, target)
            if not failures:
                # Language-specific extra checks (vitest imports for TS, ...)
                failures = self.test_sanity_checker(raw, target)
            if not failures:
                return raw
            if attempt == self.policy.max_repair_iterations:
                return SynthesisFailure(
                    target=target,
                    code=DiagnosticCode.EXCEEDED_TEST_ITERATIONS,
                    message="generated tests did not pass sanity checks within retry budget",
                    detail=failures,
                )
            failures_text = "\n".join(f.format() for f in failures)
            prompt = self.prompt_builder.build_repair_prompt(
                target=target,
                signature=signature,
                contract=contract,
                previous_code=raw,
                failures=failures_text,
            )
            state.repair_attempts += 1
        return SynthesisFailure(  # pragma: no cover
            target=target,
            code=DiagnosticCode.EXCEEDED_TEST_ITERATIONS,
            message="test loop exited without producing code",
        )


# --- helpers ---------------------------------------------------------


def _try_parse(code: str) -> tuple[ast.Module | None, str | None]:
    try:
        return ast.parse(code), None
    except SyntaxError as exc:
        return None, f"{exc.msg} at line {exc.lineno}"


def _attach_impl_to_failure(failure: SynthesisFailure, impl_code: str) -> SynthesisFailure:
    return SynthesisFailure(
        target=failure.target,
        code=failure.code,
        message=failure.message,
        detail=failure.detail,
        partial_implementation=impl_code,
    )


def _strip_markdown_fence(raw: str) -> str:
    """Strip a single leading/trailing markdown code fence if present.

    Smaller models (qwen, Llama) ignore the "no fences" instruction often
    enough that it's cheaper to undo it once than to pay for a repair
    iteration. Idempotent: a clean LLM output passes through unchanged.
    """
    stripped = raw.strip()
    if not stripped.startswith("```"):
        return raw
    # ``` or ```python / ```typescript opener — drop the first line
    lines = stripped.splitlines()
    if not lines:
        return raw
    body = "\n".join(lines[1:])
    if body.rstrip().endswith("```"):
        body = body.rstrip()[: -len("```")].rstrip()
    return body


def _failure_from_gate_report(
    target: PromptTarget, failures: tuple[GateFailure, ...]
) -> SynthesisFailure:
    """Map the dominant gate failure to the right PDF §8 error code."""
    by_gate = {failure.gate for failure in failures}
    if "security" in by_gate:
        code = DiagnosticCode.UNSAFE_GENERATED_CODE
    elif "callee-allowlist" in by_gate:
        code = DiagnosticCode.UNDECLARED_CALLEE
    elif "complexity" in by_gate:
        code = DiagnosticCode.GENERATED_CODE_TOO_COMPLEX
    else:
        code = DiagnosticCode.EXCEEDED_LINT_ITERATIONS
    message = "; ".join(f.format() for f in failures)
    return SynthesisFailure(target=target, code=code, message=message, detail=failures)


def _test_sanity_failures(
    tree: object, parse_failure: str | None, target: PromptTarget
) -> tuple[GateFailure, ...]:
    if tree is None:
        return (
            GateFailure(
                gate="test-parse",
                message=parse_failure or "syntax error in generated tests",
            ),
        )
    # Non-Python adapters (TypeScript) don't return an ``ast.Module``;
    # their out-of-band gates (vitest etc.) handle import/test-function
    # checks. Skip the Python-AST sanity probes when we can't read them.
    if not isinstance(tree, ast.Module):
        return ()
    if not _imports_target(tree, target):
        return (
            GateFailure(
                gate="test-structure",
                message=(
                    f"generated tests must import {target.function_name!r} "
                    f"from {target.module_name!r}"
                ),
            ),
        )
    if not _has_test_function(tree):
        return (
            GateFailure(
                gate="test-structure",
                message="generated tests must define at least one `test_` function",
            ),
        )
    return ()


def _imports_target(tree: ast.Module, target: PromptTarget) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == target.module_name and any(
            alias.name == target.function_name for alias in node.names
        ):
            return True
    return False


def _has_test_function(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test_")
        for node in tree.body
    )


# --- contract hash (provenance) -------------------------------------


def contract_hash(
    target: PromptTarget,
    signature: Signature,
    contract: Contract,
    policy: SynthesisPolicy,
) -> str:
    """SHA-256 over the prompt user payload.

    Using the user payload as the canonical form means *any* change that
    affects synthesis input changes the hash — signature, behavior,
    examples, calls, reads, constraints, project/verification policy,
    mode. Same input → same hash → CI can detect stale artifacts.
    """
    payload = PromptBuilder(policy=policy).canonical_payload(target, signature, contract)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "DEFAULT_MODEL",
    "Prompt",
    "SynthesisFailure",
    "SynthesisOrchestrator",
    "SynthesisOutcome",
    "SynthesisResult",
    "contract_hash",
]
