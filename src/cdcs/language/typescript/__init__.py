"""TypeScript language adapter.

Implements the same :class:`~cdcs.language.base.LanguageAdapter`
contract as :class:`~cdcs.language.python.PythonAdapter` by
delegating expression and source parsing to the ``ts-runtime/`` Node
helpers via subprocess. The DSL parser doesn't change — it goes through
the same Protocol it does for Python.
"""

from __future__ import annotations

from cdcs.language.typescript.adapter import TypeScriptAdapter
from cdcs.language.typescript.expression_parser import TypeScriptExpressionParser
from cdcs.language.typescript.source_parser import TypeScriptSourceParser

__all__ = [
    "TypeScriptAdapter",
    "TypeScriptExpressionParser",
    "TypeScriptSourceParser",
]
