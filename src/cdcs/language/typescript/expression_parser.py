"""TypeScript implementation of :class:`ExpressionParser`.

Each method spawns a short-lived Node subprocess via
:mod:`cdcs.language.typescript._runtime`. Results are memoised on
the instance so repeated queries inside one DSL parse (e.g. the same
``require`` clause appearing twice) cost a single subprocess invocation.
Cross-instance caching is the caller's job — we keep the parser
stateless from a semantic standpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cdcs.domain.models import Parameter
from cdcs.language.typescript._runtime import (
    TypeScriptRuntimeError,
    call_parse_expressions,
)

_KIND_IDENTIFIERS = "identifiers"
_KIND_CALL_TARGET = "call_target"
_KIND_ANNOTATION = "annotation"
_KIND_PARAM_LIST = "param_list"


@dataclass
class TypeScriptExpressionParser:
    """Bridges the DSL parser to the Node-side TS Compiler API.

    Not a frozen dataclass because we want a private mutable cache. The
    cache key is ``(kind, expression)`` and the value is whatever the
    Node side returned for that operation. The cache is bounded by the
    number of unique DSL expressions in a contract — small.
    """

    _cache: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict, repr=False)

    def extract_identifiers(self, expression: str) -> frozenset[str] | None:
        result = self._query(_KIND_IDENTIFIERS, expression)
        ids = result.get("identifiers")
        if ids is None:
            return None
        if not isinstance(ids, list):
            raise TypeScriptRuntimeError(f"expected list of identifiers, got {ids!r}")
        return frozenset(str(name) for name in ids)

    def extract_call_target(self, expression: str) -> str | None:
        result = self._query(_KIND_CALL_TARGET, expression)
        target = result.get("call_target")
        if target is None:
            return None
        if not isinstance(target, str):
            raise TypeScriptRuntimeError(f"expected string call_target, got {target!r}")
        return target

    def is_valid_annotation(self, annotation: str) -> bool:
        result = self._query(_KIND_ANNOTATION, annotation)
        valid = result.get("valid_annotation")
        return bool(valid)

    def parse_parameter_list(self, params_text: str) -> tuple[Parameter, ...] | None:
        result = self._query(_KIND_PARAM_LIST, params_text)
        params = result.get("parameters")
        if params is None:
            return None
        if not isinstance(params, list):
            raise TypeScriptRuntimeError(f"expected list of parameters, got {params!r}")
        return tuple(_to_parameter(item) for item in params)

    # --- internals --------------------------------------------------

    def _query(self, kind: str, expression: str) -> dict[str, Any]:
        cached: dict[str, Any] | None = self._cache.get((kind, expression))
        if cached is not None:
            return cached
        results = call_parse_expressions(
            [{"kind": kind, "id": "0", "expression": expression}],
        )
        if not results:
            raise TypeScriptRuntimeError(
                f"ts-runtime returned no result for {kind} on {expression!r}"
            )
        record = results[0]
        if not isinstance(record, dict):
            raise TypeScriptRuntimeError(f"unexpected result shape: {record!r}")
        self._cache[(kind, expression)] = record
        return record


def _to_parameter(item: dict[str, Any]) -> Parameter:
    name = item.get("name")
    if not isinstance(name, str):
        raise TypeScriptRuntimeError(f"parameter missing 'name': {item!r}")
    annotation_raw = item.get("annotation")
    annotation = annotation_raw if isinstance(annotation_raw, str) else None
    kind_raw = item.get("kind", "required")
    if kind_raw not in {"required", "optional", "rest"}:
        raise TypeScriptRuntimeError(f"unknown parameter kind: {kind_raw!r}")
    return Parameter(name=name, annotation=annotation, kind=kind_raw)
