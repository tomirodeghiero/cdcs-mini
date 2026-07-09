"""Language adapters.

Everything in this package generalises cdcs away from "Python only".
A ``LanguageAdapter`` bundles the per-language concerns the rest of the
pipeline needs: how to extract identifiers from a DSL expression, what
the language's built-in globals are, what extension generated artifacts
get, etc. The default adapter for the current POC is
:class:`~cdcs.language.python.adapter.PythonAdapter`.
"""

from __future__ import annotations

from cdcs.language.base import ExpressionParser, LanguageAdapter
from cdcs.language.python.adapter import PythonAdapter
from cdcs.language.typescript.adapter import TypeScriptAdapter

__all__ = ["ExpressionParser", "LanguageAdapter", "PythonAdapter", "TypeScriptAdapter"]
