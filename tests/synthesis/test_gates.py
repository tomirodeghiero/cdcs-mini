from __future__ import annotations

import ast
from collections.abc import Callable

from cdcs_mini.domain.models import (
    AttributeReadSpec,
    CallableSpec,
    Contract,
    Parameter,
    Signature,
)
from cdcs_mini.synthesis.gates import (
    CalleeAllowListGate,
    Candidate,
    ComplexityGate,
    GateChain,
    SecurityGate,
    StructureGate,
)
from cdcs_mini.synthesis.policy import (
    ProjectPolicy,
    SynthesisPolicy,
    VerificationPolicy,
)
from cdcs_mini.synthesis.prompt import PromptTarget

MakeCandidate = Callable[..., Candidate]


def _build_candidate(
    *,
    code: str,
    function_name: str = "parse_port",
    parameters: tuple[Parameter, ...] = (
        Parameter(name="value", annotation="str", kind="positional_or_keyword"),
    ),
    returns: str | None = "int",
    contract: Contract | None = None,
    policy: SynthesisPolicy | None = None,
) -> Candidate:
    tree = ast.parse(code)
    return Candidate(
        code=code,
        tree=tree,
        target=PromptTarget(function_name=function_name, module_name="m"),
        signature=Signature(parameters=parameters, returns=returns),
        contract=contract
        or Contract(
            behavior=(),
            examples=(),
            constraints=(),
            has_examples_section=True,
        ),
        policy=policy or SynthesisPolicy.strict_default(),
    )


# --- StructureGate ---------------------------------------------------


def test_structure_gate_passes_when_function_matches_signature() -> None:
    code = "def parse_port(value: str) -> int:\n    return int(value)\n"
    report = StructureGate().check(_build_candidate(code=code))
    assert report.passed


def test_structure_gate_flags_missing_function() -> None:
    code = "def something_else(value: str) -> int:\n    return 0\n"
    report = StructureGate().check(_build_candidate(code=code))
    assert not report.passed
    assert "parse_port" in report.failures[0].message


def test_structure_gate_flags_signature_mismatch() -> None:
    code = "def parse_port(value: int) -> int:\n    return value\n"
    report = StructureGate().check(_build_candidate(code=code))
    assert not report.passed
    assert "signature" in report.failures[0].message


# --- SecurityGate ----------------------------------------------------


def test_security_gate_flags_eval() -> None:
    code = "def parse_port(value: str) -> int:\n    return eval(value)\n"
    report = SecurityGate().check(_build_candidate(code=code))
    assert not report.passed
    assert "eval" in report.failures[0].message


def test_security_gate_flags_subprocess_run() -> None:
    code = (
        "import subprocess\n"
        "def parse_port(value: str) -> int:\n"
        "    subprocess.run(['ls'])\n"
        "    return 0\n"
    )
    report = SecurityGate().check(_build_candidate(code=code))
    assert not report.passed
    messages = {f.message for f in report.failures}
    assert any("subprocess" in m for m in messages)


def test_security_gate_allows_imports_explicitly_permitted() -> None:
    code = (
        "import httpx\n"
        "def parse_port(value: str) -> int:\n"
        "    _ = httpx.get  # noqa\n"
        "    return 1\n"
    )
    policy = SynthesisPolicy(
        project=ProjectPolicy(allowed_imports=("httpx",)),
        verification=VerificationPolicy(),
    )
    report = SecurityGate().check(_build_candidate(code=code, policy=policy))
    assert report.passed


def test_security_gate_flags_network_module_without_allow() -> None:
    code = "import socket\ndef parse_port(value: str) -> int:\n    _ = socket\n    return 1\n"
    report = SecurityGate().check(_build_candidate(code=code))
    assert not report.passed
    assert "socket" in report.failures[0].message


# --- CalleeAllowListGate --------------------------------------------


def test_callee_allowlist_flags_undeclared_self_call() -> None:
    code = "def issue(self, user_id: int) -> str:\n    return self._sign(str(user_id))\n"
    candidate = _build_candidate(
        code=code,
        function_name="issue",
        parameters=(
            Parameter(name="self", annotation=None, kind="positional_or_keyword"),
            Parameter(name="user_id", annotation="int", kind="positional_or_keyword"),
        ),
        returns="str",
    )
    report = CalleeAllowListGate().check(candidate)
    assert not report.passed
    assert "self._sign" in report.failures[0].message


def test_callee_allowlist_passes_when_self_call_is_declared() -> None:
    code = "def issue(self, user_id: int) -> str:\n    return self._sign(str(user_id))\n"
    contract = Contract(
        behavior=(),
        examples=(),
        constraints=(),
        calls=(
            CallableSpec(
                qualified_name="self._sign",
                parameters=(
                    Parameter(name="payload", annotation="str", kind="positional_or_keyword"),
                ),
                returns="str",
                purpose="HMAC",
                line=5,
            ),
        ),
        has_examples_section=True,
    )
    candidate = _build_candidate(
        code=code,
        function_name="issue",
        parameters=(
            Parameter(name="self", annotation=None, kind="positional_or_keyword"),
            Parameter(name="user_id", annotation="int", kind="positional_or_keyword"),
        ),
        returns="str",
        contract=contract,
    )
    report = CalleeAllowListGate().check(candidate)
    assert report.passed


def test_callee_allowlist_allows_self_attribute_read_when_declared() -> None:
    code = "def issue(self) -> bytes:\n    return self.secret_key\n"
    contract = Contract(
        behavior=(),
        examples=(),
        constraints=(),
        reads=(
            AttributeReadSpec(
                qualified_name="self.secret_key",
                annotation="bytes",
                purpose="",
                line=5,
            ),
        ),
        has_examples_section=True,
    )
    candidate = _build_candidate(
        code=code,
        function_name="issue",
        parameters=(Parameter(name="self", annotation=None, kind="positional_or_keyword"),),
        returns="bytes",
        contract=contract,
    )
    report = CalleeAllowListGate().check(candidate)
    assert report.passed


def test_callee_allowlist_ignores_method_calls_on_parameters() -> None:
    # value.strip() is a method on the parameter — not subject to allow-list
    code = "def parse_port(value: str) -> int:\n    return int(value.strip())\n"
    report = CalleeAllowListGate().check(_build_candidate(code=code))
    assert report.passed


# --- ComplexityGate --------------------------------------------------


def test_complexity_gate_passes_simple_function() -> None:
    code = "def parse_port(value: str) -> int:\n    return int(value)\n"
    report = ComplexityGate().check(_build_candidate(code=code))
    assert report.passed


def test_complexity_gate_flags_deep_nesting() -> None:
    code = (
        "def parse_port(value: str) -> int:\n"
        "    if value:\n"
        "        if len(value) > 0:\n"
        "            if value[0].isdigit():\n"
        "                if value[-1].isdigit():\n"
        "                    if int(value) > 0:\n"
        "                        return int(value)\n"
        "    return 0\n"
    )
    policy = SynthesisPolicy(verification=VerificationPolicy(max_nesting_depth=2))
    report = ComplexityGate().check(_build_candidate(code=code, policy=policy))
    assert not report.passed
    messages = " ".join(f.message for f in report.failures)
    assert "nesting" in messages


def test_complexity_gate_flags_high_cyclomatic() -> None:
    branches = "\n".join(f"    if value == {n}: return {n}" for n in range(15))
    code = f"def parse_port(value: str) -> int:\n{branches}\n    return 0\n"
    policy = SynthesisPolicy(verification=VerificationPolicy(max_cyclomatic_complexity=5))
    report = ComplexityGate().check(_build_candidate(code=code, policy=policy))
    assert not report.passed
    assert any("cyclomatic" in f.message for f in report.failures)


# --- GateChain -------------------------------------------------------


def test_gate_chain_aggregates_failures_from_every_gate() -> None:
    code = (
        "def parse_port(value: int) -> int:\n"  # signature mismatch (int vs str)
        "    return eval(value)\n"  # security violation
    )
    report = GateChain().run(_build_candidate(code=code))
    assert not report.passed
    gates_with_failures = {f.gate for f in report.failures}
    assert "structure" in gates_with_failures
    assert "security" in gates_with_failures
