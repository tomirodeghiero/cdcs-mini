from __future__ import annotations

from cdcs_mini.domain.models import (
    AttributeReadSpec,
    BehaviorKind,
    BehaviorStep,
    CallableSpec,
    Contract,
    Example,
    ExampleKind,
    Parameter,
    Signature,
)
from cdcs_mini.synthesis.prompt import PromptBuilder, PromptTarget


def _signature(*params: tuple[str, str | None]) -> Signature:
    return Signature(
        parameters=tuple(
            Parameter(name=name, annotation=annotation, kind="positional_or_keyword")
            for name, annotation in params
        ),
        returns="int",
    )


def _contract(
    *,
    behavior: tuple[BehaviorStep, ...] = (),
    examples: tuple[Example, ...] = (),
    constraints: tuple[str, ...] = (),
    calls: tuple[CallableSpec, ...] = (),
    reads: tuple[AttributeReadSpec, ...] = (),
) -> Contract:
    return Contract(
        behavior=behavior,
        examples=examples,
        constraints=constraints,
        calls=calls,
        reads=reads,
        has_examples_section=True,
    )


def _target() -> PromptTarget:
    return PromptTarget(function_name="parse_port", module_name="example.generated")


def _basic_contract() -> Contract:
    return _contract(
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
    )


def test_impl_and_test_prompts_share_user_payload_but_differ_in_system() -> None:
    builder = PromptBuilder.default()
    target = _target()
    signature = _signature(("value", "str"))
    contract = _basic_contract()

    impl = builder.build_implementation_prompt(
        target=target, signature=signature, contract=contract
    )
    test = builder.build_test_prompt(target=target, signature=signature, contract=contract)

    assert impl.user == test.user
    assert impl.system != test.system
    assert "implementation" not in test.system.lower() or "DO NOT" in test.system


def test_test_prompt_does_not_mention_implementation() -> None:
    builder = PromptBuilder.default()
    target = _target()
    test = builder.build_test_prompt(
        target=target,
        signature=_signature(("value", "str")),
        contract=_basic_contract(),
    )
    # The test prompt must NOT contain the implementation; PDF §9.
    # It's enforced structurally by ``build_test_prompt`` taking only the
    # signature + contract, never an impl. We assert the system prompt
    # makes this explicit.
    assert "DO NOT receive the implementation" in test.system


def test_user_payload_contains_signature_behavior_examples_and_policy() -> None:
    builder = PromptBuilder.default()
    target = _target()
    contract = _basic_contract()
    prompt = builder.build_implementation_prompt(
        target=target,
        signature=_signature(("value", "str")),
        contract=contract,
    )
    payload = prompt.user
    assert "def parse_port(value: str) -> int" in payload
    assert "Behavior" in payload
    assert "return int(value)" in payload
    assert "Examples" in payload
    assert 'parse_port("80") == 80' in payload
    assert "Project policy" in payload
    assert "Verification policy" in payload


def test_user_payload_includes_calls_and_reads_when_present() -> None:
    builder = PromptBuilder.default()
    target = _target()
    contract = _contract(
        examples=(Example(kind=ExampleKind.EQUALS, raw="f(1) == 1", line=5, call_target="f"),),
        calls=(
            CallableSpec(
                qualified_name="self._sign",
                parameters=(
                    Parameter(name="payload", annotation="str", kind="positional_or_keyword"),
                ),
                returns="str",
                purpose="HMAC of payload",
                line=8,
            ),
        ),
        reads=(
            AttributeReadSpec(
                qualified_name="self.secret_key",
                annotation="bytes",
                purpose="used by _sign",
                line=10,
            ),
        ),
    )
    prompt = builder.build_implementation_prompt(
        target=target,
        signature=_signature(("self", None), ("value", "str")),
        contract=contract,
    )
    assert "Allowed callees" in prompt.user
    assert "self._sign(payload: str) -> str  # HMAC of payload" in prompt.user
    assert "Allowed attribute reads" in prompt.user
    assert "self.secret_key: bytes  # used by _sign" in prompt.user


def test_repair_prompt_includes_previous_code_and_failures() -> None:
    builder = PromptBuilder.default()
    target = _target()
    prompt = builder.build_repair_prompt(
        target=target,
        signature=_signature(("value", "str")),
        contract=_basic_contract(),
        previous_code="def parse_port(value: str) -> int:\n    return 0",
        failures="E1: tests failed: test_parse_valid_ports",
    )
    assert prompt.kind == "repair"
    assert "Previous attempt" in prompt.user
    assert "def parse_port" in prompt.user
    assert "Verification failures" in prompt.user
    assert "test_parse_valid_ports" in prompt.user


def test_prompts_are_deterministic_across_builds() -> None:
    builder = PromptBuilder.default()
    target = _target()
    signature = _signature(("value", "str"))
    contract = _basic_contract()
    first = builder.build_implementation_prompt(
        target=target, signature=signature, contract=contract
    )
    second = builder.build_implementation_prompt(
        target=target, signature=signature, contract=contract
    )
    assert first.system == second.system
    assert first.user == second.user
