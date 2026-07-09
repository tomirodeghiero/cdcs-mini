"""Augmented prompt builder (PDF §5).

Assembles a deterministic prompt from five sources:

  * language signature   — extracted by ``SourceParser``;
  * user contract        — extracted by ``DSLParser``;
  * project policy       — language version, imports, typing rules;
  * verification policy  — gates and thresholds the result must pass;
  * generation mode      — strict-only in the POC.

The language-specific text fragments live in :class:`LanguageProfile`.
Swapping Python for TypeScript means swapping the profile — the
canonical prompt skeleton stays identical so all upstream hashing /
verification semantics keep their meaning.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Literal

from cdcs.domain.models import (
    AttributeReadSpec,
    BehaviorStep,
    CallableSpec,
    Contract,
    Example,
    Parameter,
    Signature,
)
from cdcs.synthesis.policy import SynthesisPolicy

PromptKind = Literal["implementation", "test", "repair"]


@dataclass(frozen=True, slots=True)
class Prompt:
    system: str
    user: str
    kind: PromptKind


@dataclass(frozen=True, slots=True)
class PromptTarget:
    """Identifies the function being synthesized.

    ``module_name`` is what the generated tests will import from; the
    orchestrator wires it from the source path.
    """

    function_name: str
    module_name: str


# --- LanguageProfile ------------------------------------------------


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    """Language-specific text fragments the prompt builder needs.

    The fields are deliberately strings (or callables that produce
    strings) rather than templates: keeps the contract clear and gives
    each language room to format signatures / imports the way LLMs are
    used to seeing them.
    """

    display_name: str
    test_runner: str
    builtins_label: str
    fenced_code_language: str
    code_fence_open: str
    render_signature_stub: Callable[[PromptTarget, Signature], str] = field(repr=False)
    render_test_import: Callable[[PromptTarget], str] = field(repr=False)
    impl_output_instructions: str = field(repr=False)
    # Test output instructions depend on the target (filename / function),
    # so we accept a callable. Constant instructions can wrap a fixed
    # string in ``lambda _target: "..."``.
    render_test_output_instructions: Callable[[PromptTarget], str] = field(repr=False)
    code_fence_close: str = "```"


# --- builders for the two language profiles -------------------------


def _render_parameter(parameter: Parameter) -> str:
    if parameter.annotation is None:
        return parameter.name
    return f"{parameter.name}: {parameter.annotation}"


def _render_callable(spec: CallableSpec) -> str:
    params = ", ".join(_render_parameter(p) for p in spec.parameters)
    returns = spec.returns or "None"
    base = f"{spec.qualified_name}({params}) -> {returns}"
    if spec.purpose:
        return f"{base}  # {spec.purpose}"
    return base


def _render_attribute(spec: AttributeReadSpec) -> str:
    annotation = f": {spec.annotation}" if spec.annotation else ""
    if spec.purpose:
        return f"{spec.qualified_name}{annotation}  # {spec.purpose}"
    return f"{spec.qualified_name}{annotation}"


# --- Python profile (default for back-compat) -----------------------


def _python_signature_stub(target: PromptTarget, signature: Signature) -> str:
    params = ", ".join(_render_parameter(p) for p in signature.parameters)
    returns = signature.returns or "None"
    return f"def {target.function_name}({params}) -> {returns}: ..."


def _python_test_import(target: PromptTarget) -> str:
    return f"from {target.module_name} import {target.function_name}"


_PYTHON_IMPL_INSTRUCTIONS: Final[str] = (
    "Output format: a single Python source fragment containing "
    "(a) any imports the function needs and (b) the function "
    "definition. No prose, no markdown fences, no commentary, "
    "no extra functions or classes."
)


def _python_test_instructions(target: PromptTarget) -> str:
    return (
        "Output format: a single Python source file beginning with "
        "`import pytest` and the import for the target function. "
        f"Use `from {target.module_name} import {target.function_name}`. "
        "Cover every Examples entry, and add tests for the empty "
        "and boundary cases implied by the contract. Use "
        "`pytest.raises` for the 'raises' examples. No prose, no "
        "markdown fences."
    )


PYTHON_PROFILE: Final[LanguageProfile] = LanguageProfile(
    display_name="Python",
    test_runner="pytest",
    builtins_label="Python builtins",
    fenced_code_language="python",
    code_fence_open="```python",
    render_signature_stub=_python_signature_stub,
    render_test_import=_python_test_import,
    impl_output_instructions=_PYTHON_IMPL_INSTRUCTIONS,
    render_test_output_instructions=_python_test_instructions,
)


# --- TypeScript profile ---------------------------------------------


def _typescript_signature_stub(target: PromptTarget, signature: Signature) -> str:
    params = ", ".join(_render_ts_parameter(p) for p in signature.parameters)
    returns = signature.returns or "void"
    return f"export function {target.function_name}({params}): {returns};"


def _render_ts_parameter(parameter: Parameter) -> str:
    optional = ""
    name = parameter.name
    if parameter.kind == "optional":
        optional = "?"
    elif parameter.kind == "rest":
        name = f"...{parameter.name}"
    if parameter.annotation is None:
        return f"{name}{optional}"
    return f"{name}{optional}: {parameter.annotation}"


def _typescript_test_import(target: PromptTarget) -> str:
    # Vitest setups commonly do `import { fn } from "./module.js";` even for
    # `.ts` sources — the `.js` suffix matches Node's ESM resolution.
    return f'import {{ {target.function_name} }} from "./{target.module_name}.js";'


_TYPESCRIPT_IMPL_INSTRUCTIONS: Final[str] = (
    "Output format: a single TypeScript source fragment containing "
    "(a) the function declaration with `export` and (b) any sibling "
    "helpers explicitly allowed by the Constraints. Keep the public "
    "API limited to the requested function — no extra exports. No "
    "prose, no markdown fences."
)


def _typescript_test_instructions(target: PromptTarget) -> str:
    fn = target.function_name
    module = target.module_name
    # Hand the model a literal vitest skeleton it can copy and fill in.
    # Smaller models (qwen-7b, llama) ignore prose instructions but
    # imitate concrete examples reliably.
    return (
        "Output format: ONE TypeScript test module. Start exactly with these "
        "two lines (no prose, no markdown fences):\n\n"
        '    import { test, expect } from "vitest";\n'
        f'    import {{ {fn} }} from "./{module}.js";\n\n'
        "Then emit one `test(name, () => {...})` per Examples entry. Inside "
        f"each test body, call `{fn}(...)` with the example's arguments and "
        f"assert with `expect({fn}(...)).toBe(value)` for `== value` cases, or "
        f"`expect(() => {fn}(...)).toThrow()` for `raises ...` cases. Do NOT "
        f"re-declare `{fn}` — import it. Do NOT output explanatory prose."
    )


TYPESCRIPT_PROFILE: Final[LanguageProfile] = LanguageProfile(
    display_name="TypeScript",
    test_runner="vitest",
    builtins_label="JavaScript/TypeScript globals",
    fenced_code_language="typescript",
    code_fence_open="```typescript",
    render_signature_stub=_typescript_signature_stub,
    render_test_import=_typescript_test_import,
    impl_output_instructions=_TYPESCRIPT_IMPL_INSTRUCTIONS,
    render_test_output_instructions=_typescript_test_instructions,
)


# --- PromptBuilder --------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromptBuilder:
    policy: SynthesisPolicy
    language: LanguageProfile = PYTHON_PROFILE

    @classmethod
    def default(cls) -> PromptBuilder:
        return cls(policy=SynthesisPolicy.strict_default())

    @classmethod
    def for_language(cls, language: LanguageProfile) -> PromptBuilder:
        return cls(policy=SynthesisPolicy.strict_default(), language=language)

    # --- public API ---------------------------------------------------

    def build_implementation_prompt(
        self,
        *,
        target: PromptTarget,
        signature: Signature,
        contract: Contract,
    ) -> Prompt:
        return Prompt(
            system=self._implementation_system(),
            user=self.canonical_payload(target, signature, contract),
            kind="implementation",
        )

    def build_test_prompt(
        self,
        *,
        target: PromptTarget,
        signature: Signature,
        contract: Contract,
    ) -> Prompt:
        return Prompt(
            system=self._test_system(target),
            user=self.canonical_payload(target, signature, contract),
            kind="test",
        )

    def build_repair_prompt(
        self,
        *,
        target: PromptTarget,
        signature: Signature,
        contract: Contract,
        previous_code: str,
        failures: str,
    ) -> Prompt:
        body = self.canonical_payload(target, signature, contract)
        repair = (
            "\n# Previous attempt (do not relax the contract — fix it):\n"
            f"{self.language.code_fence_open}\n{previous_code}\n"
            f"{self.language.code_fence_close}\n"
            "\n# Verification failures from that attempt:\n"
            f"{failures.strip()}\n"
            "\nRegenerate the function. Address every failure above. "
            "Output ONLY the function definition and required imports."
        )
        return Prompt(
            system=self._implementation_system(),
            user=body + repair,
            kind="repair",
        )

    # --- system prompts ----------------------------------------------

    def _implementation_system(self) -> str:
        mode = self.policy.generation.name
        lang = self.language
        return (
            "You are CDCS, a contract-driven code synthesizer. "
            f"You receive a {lang.display_name} function signature and a "
            "behavioral contract. Generate exactly one function body that "
            "satisfies the contract.\n\n"
            f"{lang.impl_output_instructions}\n\n"
            f"Mode: {mode}. In strict mode you MUST NOT introduce helper "
            "functions, classes, global state, or public APIs beyond the "
            "function itself. Only the callees declared in the 'Allowed "
            f"callees' section may be invoked (plus {lang.builtins_label}). "
            "Imports outside the project's allowed list are forbidden."
        )

    def _test_system(self, target: PromptTarget) -> str:
        lang = self.language
        return (
            "You are CDCS, a contract-driven test synthesizer. "
            f"You receive a {lang.display_name} function signature and a "
            "behavioral contract — you DO NOT receive the implementation. "
            f"Generate a {lang.test_runner} module that tests the contract "
            "independently.\n\n"
            f"{lang.render_test_output_instructions(target)}\n\n"
            f"Target import line: `{lang.render_test_import(target)}`."
        )

    # --- shared user payload -----------------------------------------

    def canonical_payload(
        self, target: PromptTarget, signature: Signature, contract: Contract
    ) -> str:
        """Deterministic prompt body — exposed so callers can hash it.

        Same body used in impl/test/repair prompts; same body fed to the
        ``contract_hash`` provenance computation.
        """
        sections = (
            self._signature_section(target, signature),
            self._behavior_section(contract.behavior),
            self._examples_section(contract.examples),
            self._calls_section(contract.calls),
            self._reads_section(contract.reads),
            self._constraints_section(contract.constraints),
            self._project_policy_section(),
            self._verification_policy_section(),
        )
        return "\n\n".join(s for s in sections if s)

    # --- individual sections -----------------------------------------

    def _signature_section(self, target: PromptTarget, signature: Signature) -> str:
        stub = self.language.render_signature_stub(target, signature)
        return f"# Function signature (authoritative)\n{stub}"

    def _behavior_section(self, behavior: tuple[BehaviorStep, ...]) -> str:
        if not behavior:
            return ""
        lines = "\n".join(f"  - {step.raw}" for step in behavior)
        return f"# Behavior\n{lines}"

    def _examples_section(self, examples: tuple[Example, ...]) -> str:
        if not examples:
            return ""
        lines = "\n".join(f"  - {example.raw}" for example in examples)
        return f"# Examples\n{lines}"

    def _calls_section(self, calls: tuple[CallableSpec, ...]) -> str:
        if not calls:
            return f"# Allowed callees\n  (none beyond {self.language.builtins_label})"
        lines = "\n".join(f"  - {_render_callable(c)}" for c in calls)
        return f"# Allowed callees\n{lines}"

    def _reads_section(self, reads: tuple[AttributeReadSpec, ...]) -> str:
        if not reads:
            return ""
        lines = "\n".join(f"  - {_render_attribute(a)}" for a in reads)
        return f"# Allowed attribute reads\n{lines}"

    def _constraints_section(self, constraints: tuple[str, ...]) -> str:
        if not constraints:
            return ""
        lines = "\n".join(f"  - {c}" for c in constraints)
        return f"# Constraints\n{lines}"

    def _project_policy_section(self) -> str:
        proj = self.policy.project
        allowed = "stdlib only" if not proj.allowed_imports else ", ".join(proj.allowed_imports)
        typing_rule = (
            "type annotations required on parameters and return"
            if proj.require_type_annotations
            else "annotations recommended"
        )
        return (
            "# Project policy\n"
            f"  - {self.language.display_name} {proj.python_version}\n"
            f"  - {typing_rule}\n"
            f"  - Allowed third-party imports: {allowed}"
        )

    def _verification_policy_section(self) -> str:
        v = self.policy.verification
        forbidden_calls = ", ".join(sorted(v.forbidden_call_names))
        return (
            "# Verification policy (the output WILL be checked against these)\n"
            f"  - Cyclomatic complexity ≤ {v.max_cyclomatic_complexity}\n"
            f"  - Lines ≤ {v.max_lines}, nesting depth ≤ {v.max_nesting_depth}\n"
            f"  - Forbidden calls: {forbidden_calls}\n"
            "  - Filesystem / network / subprocess modules forbidden "
            "unless explicitly allowed by Constraints"
        )
