"""Concrete :class:`LanguageAdapter` for TypeScript.

Mirrors the shape of :class:`~cdcs_mini.language.python.PythonAdapter`,
but the expression parser delegates to the ts-runtime workspace and
``known_globals`` carries the TypeScript/JavaScript builtins instead of
Python's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from cdcs_mini.language.typescript.expression_parser import TypeScriptExpressionParser
from cdcs_mini.language.typescript.source_parser import TypeScriptSourceParser
from cdcs_mini.synthesis.prompt import TYPESCRIPT_PROFILE, LanguageProfile

# Conservative starter set: enough to cover the identifiers the DSL is
# likely to reference inside ``require`` / ``return`` / examples. Add
# more as real contracts surface false positives.
_TS_GLOBAL_VALUES: Final[frozenset[str]] = frozenset(
    {
        # Literals / keywords usable as values in expressions
        "true",
        "false",
        "null",
        "undefined",
        "NaN",
        "Infinity",
        "this",
        # Top-level functions
        "parseInt",
        "parseFloat",
        "isNaN",
        "isFinite",
        "encodeURIComponent",
        "decodeURIComponent",
        # Constructor / namespace objects
        "Array",
        "Boolean",
        "Date",
        "Error",
        "Function",
        "JSON",
        "Map",
        "Math",
        "Number",
        "Object",
        "Promise",
        "RegExp",
        "Set",
        "String",
        "Symbol",
        "WeakMap",
        "WeakSet",
        "console",
        # Common error types referenced by ``raises ...`` examples
        "TypeError",
        "RangeError",
        "SyntaxError",
        "ReferenceError",
        # ``ValueError`` is Python — but the DSL keeps ``raises X`` syntax
        # uniform, so contracts may still write ``raises ValueError`` for
        # readability. Allow it.
        "ValueError",
    }
)


@dataclass(frozen=True, slots=True)
class TypeScriptAdapter:
    """Adapter wiring TS sources into the language-agnostic pipeline."""

    name: str = "typescript"
    source_extensions: frozenset[str] = field(default_factory=lambda: frozenset({".ts", ".tsx"}))
    # Mirrors the convention from PythonAdapter but for the TS world:
    # impl lives at ``{stem}_generated.ts``, tests at
    # ``test_{stem}_generated.test.ts`` (the doubled ``.test.`` is the
    # idiomatic vitest naming so ``vitest`` discovers them automatically).
    impl_artifact_suffix: str = "_generated.ts"
    test_artifact_suffix: str = "_generated.test.ts"
    expression_parser: TypeScriptExpressionParser = field(
        default_factory=TypeScriptExpressionParser
    )
    source_parser: TypeScriptSourceParser = field(default_factory=TypeScriptSourceParser)
    known_globals: frozenset[str] = field(default_factory=lambda: _TS_GLOBAL_VALUES)
    prompt_profile: LanguageProfile = TYPESCRIPT_PROFILE
