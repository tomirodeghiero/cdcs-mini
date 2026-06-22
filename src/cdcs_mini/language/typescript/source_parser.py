"""TypeScript source parser.

Produces the same :class:`ParsedSource` / :class:`ParsedFunction` shape
the Python ``SourceParser`` does, so :class:`ReportService` can consume
either with no branching. Delegates the actual parsing to the
``ts-runtime/`` Node helpers — we never touch TS syntax in Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import Parameter, Signature
from cdcs_mini.language.typescript._runtime import (
    TypeScriptRuntimeError,
    call_parse_source,
)
from cdcs_mini.parsing.source_parser import ParsedFunction, ParsedSource

_ALLOWED_PARAMETER_KINDS: Final[frozenset[str]] = frozenset({"required", "optional", "rest"})


@dataclass(frozen=True, slots=True)
class TypeScriptSourceParser:
    """Wraps the ``parse-source`` ts-runtime CLI.

    Stateless: every ``parse()`` is a fresh subprocess. The DSL body
    extraction happens on the Node side and arrives ready to feed into
    :class:`~cdcs_mini.parsing.dsl_parser.DSLParser`.
    """

    def parse(self, source: str, *, filename: str = "<input>") -> ParsedSource:
        try:
            payload = call_parse_source(source, filename)
        except TypeScriptRuntimeError as exc:
            return ParsedSource(
                functions=(),
                errors=(
                    Diagnostic(
                        line=None,
                        code=DiagnosticCode.SYNTAX_ERROR,
                        message=f"ts-runtime invocation failed: {exc}",
                    ),
                ),
            )
        return _decode_response(payload)


def _decode_response(payload: dict[str, Any]) -> ParsedSource:
    errors = _decode_errors(payload.get("errors", []))
    if errors:
        return ParsedSource(functions=(), errors=errors)
    fn_payload = payload.get("functions", [])
    if not isinstance(fn_payload, list):
        raise TypeScriptRuntimeError(f"functions field must be a list, got {fn_payload!r}")
    return ParsedSource(
        functions=tuple(_decode_function(item) for item in fn_payload),
        errors=(),
    )


def _decode_errors(items: object) -> tuple[Diagnostic, ...]:
    if not isinstance(items, list):
        raise TypeScriptRuntimeError(f"errors field must be a list, got {items!r}")
    out: list[Diagnostic] = []
    for item in items:
        if not isinstance(item, dict):
            raise TypeScriptRuntimeError(f"error entry must be a dict, got {item!r}")
        line_raw = item.get("line")
        line = int(line_raw) if isinstance(line_raw, int) else None
        message_raw = item.get("message", "")
        message = message_raw if isinstance(message_raw, str) else str(message_raw)
        out.append(
            Diagnostic(
                line=line,
                code=DiagnosticCode.SYNTAX_ERROR,
                message=message,
            )
        )
    return tuple(out)


def _decode_function(item: object) -> ParsedFunction:
    if not isinstance(item, dict):
        raise TypeScriptRuntimeError(f"function entry must be a dict, got {item!r}")
    name = _expect_str(item, "name")
    line = _expect_int(item, "line")
    parameters = _decode_parameters(item.get("parameters", []))
    returns_raw = item.get("returns")
    returns = returns_raw if isinstance(returns_raw, str) else None
    has_variadic = bool(item.get("has_variadic", False))
    diagnostics: list[Diagnostic] = []
    if has_variadic:
        diagnostics.append(
            Diagnostic(
                line=line,
                code=DiagnosticCode.UNSUPPORTED_SIGNATURE,
                message="variadic arguments are not supported",
            )
        )
    dsl_body_raw = item.get("dsl_body")
    dsl_body = dsl_body_raw if isinstance(dsl_body_raw, str) else None
    dsl_line_raw = item.get("dsl_line")
    dsl_line = int(dsl_line_raw) if isinstance(dsl_line_raw, int) else None
    return ParsedFunction(
        name=name,
        line=line,
        signature=Signature(
            parameters=parameters,
            returns=returns,
            has_variadic=has_variadic,
        ),
        docstring=dsl_body,
        docstring_line=dsl_line,
        diagnostics=tuple(diagnostics),
    )


def _decode_parameters(items: object) -> tuple[Parameter, ...]:
    if not isinstance(items, list):
        raise TypeScriptRuntimeError(f"parameters must be a list, got {items!r}")
    result: list[Parameter] = []
    for item in items:
        if not isinstance(item, dict):
            raise TypeScriptRuntimeError(f"parameter must be a dict, got {item!r}")
        name = _expect_str(item, "name")
        annotation_raw = item.get("annotation")
        annotation = annotation_raw if isinstance(annotation_raw, str) else None
        kind = item.get("kind", "required")
        if kind not in _ALLOWED_PARAMETER_KINDS:
            raise TypeScriptRuntimeError(f"unknown parameter kind: {kind!r}")
        result.append(Parameter(name=name, annotation=annotation, kind=kind))
    return tuple(result)


def _expect_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise TypeScriptRuntimeError(f"expected string for {key!r}, got {value!r}")
    return value


def _expect_int(item: dict[str, Any], key: str) -> int:
    value = item.get(key)
    if not isinstance(value, int):
        raise TypeScriptRuntimeError(f"expected int for {key!r}, got {value!r}")
    return value
