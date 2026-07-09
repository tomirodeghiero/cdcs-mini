"""Project, mode, and verification policies for the synthesis pipeline.

Mirrors the "Augmented Prompt Model" of PDF §5 and the verification
gates of §15. Pure value types — no I/O. The CLI is what materialises
these (from defaults today, from ``cdcs.toml`` tomorrow).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ModeName = Literal["strict", "refactor"]


@dataclass(frozen=True, slots=True)
class GenerationMode:
    """How permissive the synthesizer is allowed to be.

    The POC only ships ``strict``: the model returns exactly the
    requested function body, no helpers, no new public APIs. ``refactor``
    is reserved for a future iteration where helper extraction is
    permitted but each helper becomes its own ``@generate`` artifact.
    """

    name: ModeName = "strict"
    allow_local_helpers: bool = False


@dataclass(frozen=True, slots=True)
class ProjectPolicy:
    """Project-wide rules that apply to every synthesized function."""

    python_version: str = "3.12+"
    require_type_annotations: bool = True
    # Empty tuple means "stdlib only". Anything else lists permitted top-level
    # import roots (e.g. ``("pydantic", "httpx")``). The contract can override
    # per-function via its ``Constraints:`` section.
    allowed_imports: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    """Thresholds and forbidden surfaces for the verification gates."""

    max_cyclomatic_complexity: int = 8
    max_lines: int = 60
    max_nesting_depth: int = 4
    # AST-level forbidden calls. Always enforced for generated code; the
    # contract's ``Constraints:`` can extend this set but never relax it.
    forbidden_call_names: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"eval", "exec", "compile", "__import__", "globals", "locals"}
        )
    )
    forbidden_attribute_calls: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"os.system", "os.popen", "subprocess.run", "subprocess.Popen"}
        )
    )
    # Module imports rejected unless the constraint string explicitly allows them.
    network_modules: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"socket", "http", "http.client", "urllib", "urllib.request", "requests", "httpx"}
        )
    )
    filesystem_modules: frozenset[str] = field(
        default_factory=lambda: frozenset({"pathlib", "io", "shutil", "tempfile"})
    )
    subprocess_modules: frozenset[str] = field(
        default_factory=lambda: frozenset({"subprocess", "os"})
    )


@dataclass(frozen=True, slots=True)
class SynthesisPolicy:
    """Bundle of every policy the prompt builder and gates need.

    One value, passed everywhere, immutable. Tests construct it directly
    with their own thresholds; production reads it from configuration.
    """

    generation: GenerationMode = field(default_factory=GenerationMode)
    project: ProjectPolicy = field(default_factory=ProjectPolicy)
    verification: VerificationPolicy = field(default_factory=VerificationPolicy)
    max_repair_iterations: int = 3

    @classmethod
    def strict_default(cls) -> SynthesisPolicy:
        return cls()
