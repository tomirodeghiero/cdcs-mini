from __future__ import annotations

from cdcs_mini.domain.diagnostics import DiagnosticCode
from cdcs_mini.domain.models import (
    BehaviorKind,
    BehaviorStep,
    Contract,
    Example,
    ExampleKind,
    Parameter,
    Signature,
)
from cdcs_mini.synthesis.llm import RecordedLLMClient
from cdcs_mini.synthesis.orchestrator import (
    SynthesisFailure,
    SynthesisOrchestrator,
    SynthesisOutcome,
    contract_hash,
)
from cdcs_mini.synthesis.policy import (
    GenerationMode,
    ProjectPolicy,
    SynthesisPolicy,
    VerificationPolicy,
)
from cdcs_mini.synthesis.prompt import PromptTarget

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
from example_generated import parse_port

def test_valid() -> None:
    assert parse_port("80") == 80

def test_invalid() -> None:
    with pytest.raises(ValueError):
        parse_port("0")
"""


def _signature() -> Signature:
    return Signature(
        parameters=(Parameter(name="value", annotation="str", kind="positional_or_keyword"),),
        returns="int",
    )


def _contract() -> Contract:
    return Contract(
        behavior=(
            BehaviorStep(
                kind=BehaviorKind.RETURN,
                raw="return int(value)",
                line=4,
                references=frozenset({"value"}),
            ),
        ),
        examples=(
            Example(
                kind=ExampleKind.EQUALS,
                raw='parse_port("80") == 80',
                line=5,
                call_target="parse_port",
            ),
        ),
        constraints=(),
        has_examples_section=True,
    )


def _target() -> PromptTarget:
    return PromptTarget(function_name="parse_port", module_name="example_generated")


def test_synthesize_returns_outcome_on_happy_path() -> None:
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    llm.register_kind("test", GOOD_TESTS)
    result = SynthesisOrchestrator.with_llm(llm).synthesize(
        target=_target(), signature=_signature(), contract=_contract()
    )
    assert isinstance(result, SynthesisOutcome)
    assert result.implementation_code.strip().startswith("def parse_port")
    assert "test_valid" in result.test_code
    assert result.llm_calls == 2
    assert result.repair_attempts == 0
    assert len(result.contract_hash) == 64


def test_synthesize_records_separate_impl_and_test_calls() -> None:
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    llm.register_kind("test", GOOD_TESTS)
    SynthesisOrchestrator.with_llm(llm).synthesize(
        target=_target(), signature=_signature(), contract=_contract()
    )
    kinds = [p.kind for p in llm.calls]
    assert kinds == ["implementation", "test"]
    # The test prompt must NOT contain the implementation body — only the
    # signature (with `...` placeholder), behavior, examples, etc.
    test_prompt = next(p for p in llm.calls if p.kind == "test")
    assert "stripped = value.strip()" not in test_prompt.user
    assert "port = int(stripped)" not in test_prompt.user


def test_unsafe_impl_emits_unsafe_generated_code_error() -> None:
    unsafe = "def parse_port(value: str) -> int:\n    return eval(value)\n"
    llm = RecordedLLMClient()
    llm.register_kind("implementation", unsafe)
    llm.register_kind("test", GOOD_TESTS)
    policy = SynthesisPolicy(
        generation=GenerationMode(),
        project=ProjectPolicy(),
        verification=VerificationPolicy(),
        max_repair_iterations=0,
    )
    result = SynthesisOrchestrator(llm=llm, policy=policy).synthesize(
        target=_target(), signature=_signature(), contract=_contract()
    )
    assert isinstance(result, SynthesisFailure)
    assert result.code == DiagnosticCode.UNSAFE_GENERATED_CODE


def test_too_complex_impl_emits_complexity_error() -> None:
    branches = "\n".join(f"    if value == {n}: return {n}" for n in range(20))
    too_complex = f"def parse_port(value: str) -> int:\n{branches}\n    return 0\n"
    llm = RecordedLLMClient()
    llm.register_kind("implementation", too_complex)
    llm.register_kind("test", GOOD_TESTS)
    policy = SynthesisPolicy(
        verification=VerificationPolicy(max_cyclomatic_complexity=5),
        max_repair_iterations=0,
    )
    result = SynthesisOrchestrator(llm=llm, policy=policy).synthesize(
        target=_target(), signature=_signature(), contract=_contract()
    )
    assert isinstance(result, SynthesisFailure)
    assert result.code == DiagnosticCode.GENERATED_CODE_TOO_COMPLEX


def test_repair_loop_recovers_when_second_attempt_passes() -> None:
    # The first attempt has the wrong return; second attempt is clean.
    bad_first = "def parse_port(value: str) -> int:\n    return eval(value)\n"
    llm = _SequencedLLM([bad_first, GOOD_IMPL, GOOD_TESTS])
    policy = SynthesisPolicy(max_repair_iterations=2)
    result = SynthesisOrchestrator(llm=llm, policy=policy).synthesize(
        target=_target(), signature=_signature(), contract=_contract()
    )
    assert isinstance(result, SynthesisOutcome)
    assert result.repair_attempts == 1
    assert result.llm_calls == 3


def test_undeclared_callee_emits_dedicated_error() -> None:
    code = "def issue(self, user_id: int) -> str:\n    return self._sign(str(user_id))\n"
    llm = RecordedLLMClient()
    llm.register_kind("implementation", code)
    llm.register_kind("test", GOOD_TESTS)
    signature = Signature(
        parameters=(
            Parameter(name="self", annotation=None, kind="positional_or_keyword"),
            Parameter(name="user_id", annotation="int", kind="positional_or_keyword"),
        ),
        returns="str",
    )
    contract = Contract(behavior=(), examples=(), constraints=(), has_examples_section=True)
    policy = SynthesisPolicy(max_repair_iterations=0)
    target = PromptTarget(function_name="issue", module_name="m")
    result = SynthesisOrchestrator(llm=llm, policy=policy).synthesize(
        target=target, signature=signature, contract=contract
    )
    assert isinstance(result, SynthesisFailure)
    assert result.code == DiagnosticCode.UNDECLARED_CALLEE


def test_test_synthesis_failure_emits_exceeded_test_iterations() -> None:
    llm = RecordedLLMClient()
    llm.register_kind("implementation", GOOD_IMPL)
    # The test response doesn't import the target → sanity fail every time
    llm.register_kind("test", "def not_a_test() -> None:\n    pass\n")
    policy = SynthesisPolicy(max_repair_iterations=0)
    result = SynthesisOrchestrator(llm=llm, policy=policy).synthesize(
        target=_target(), signature=_signature(), contract=_contract()
    )
    assert isinstance(result, SynthesisFailure)
    assert result.code == DiagnosticCode.EXCEEDED_TEST_ITERATIONS


def test_contract_hash_is_stable_and_input_sensitive() -> None:
    policy = SynthesisPolicy.strict_default()
    h1 = contract_hash(_target(), _signature(), _contract(), policy)
    h2 = contract_hash(_target(), _signature(), _contract(), policy)
    assert h1 == h2
    # Change behavior → hash changes
    different = Contract(
        behavior=(
            BehaviorStep(
                kind=BehaviorKind.RETURN,
                raw="return 0",
                line=4,
                references=frozenset(),
            ),
        ),
        examples=_contract().examples,
        constraints=(),
        has_examples_section=True,
    )
    assert contract_hash(_target(), _signature(), different, policy) != h1


# --- helpers ---------------------------------------------------------


class _SequencedLLM:
    """Returns prerecorded responses in order, regardless of prompt kind."""

    model = "sequenced"

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[object] = []

    def complete(self, prompt: object) -> str:
        self.calls.append(prompt)
        if not self._responses:
            raise RuntimeError("no more responses")
        return self._responses.pop(0)
