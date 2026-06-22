"""Concrete :class:`LanguageAdapter` for Python.

Holds the language-specific knobs the pipeline needs without dictating
where the actual SourceParser / Gates / PromptBuilder live (those still
sit under ``parsing/``, ``synthesis/`` — moving them is a no-op
refactor we'll do when the TypeScript adapter actually needs the same
shape).
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
from typing import Final

from cdcs_mini.language.python.expression_parser import PythonExpressionParser
from cdcs_mini.parsing.source_parser import SourceParser
from cdcs_mini.synthesis.prompt import PYTHON_PROFILE, LanguageProfile

# DSL-level identifiers that are not Python builtins but should not be
# flagged as unknown parameters by the validator. ``True`` / ``False`` /
# ``None`` are tokens we routinely see inside ``require`` clauses and
# example RHSs.
_DSL_CONSTANTS: Final[frozenset[str]] = frozenset({"True", "False", "None"})

_PYTHON_KNOWN_GLOBALS: Final[frozenset[str]] = frozenset(dir(builtins)) | _DSL_CONSTANTS


@dataclass(frozen=True, slots=True)
class PythonAdapter:
    """Singleton-ish adapter for the Python language.

    Constructed without arguments; the dataclass fields are defaults so
    callers can ``PythonAdapter()`` and get a working adapter, or pass
    a custom expression parser / globals set when testing the seam.
    """

    name: str = "python"
    source_extensions: frozenset[str] = field(default_factory=lambda: frozenset({".py"}))
    impl_artifact_suffix: str = "_generated.py"
    test_artifact_suffix: str = "_generated.py"
    expression_parser: PythonExpressionParser = field(default_factory=PythonExpressionParser)
    source_parser: SourceParser = field(default_factory=SourceParser)
    known_globals: frozenset[str] = field(default_factory=lambda: _PYTHON_KNOWN_GLOBALS)
    prompt_profile: LanguageProfile = PYTHON_PROFILE
