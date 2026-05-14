"""Walks Python sources via ``ast``.

We only look at top-level ``def`` (and ``async def``) — methods,
lambdas and nested functions don't carry ``@generate`` contracts.
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass

from cdcs_mini.domain.diagnostics import Diagnostic, DiagnosticCode
from cdcs_mini.domain.models import Parameter, ParameterKind, Signature

GENERATE_MARKER = "@generate"


@dataclass(frozen=True, slots=True)
class ParsedFunction:
    name: str
    line: int
    signature: Signature
    docstring: str | None
    docstring_line: int | None
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True, slots=True)
class ParsedSource:
    functions: tuple[ParsedFunction, ...]
    errors: tuple[Diagnostic, ...]


class SourceParser:
    def parse(self, source: str, *, filename: str = "<input>") -> ParsedSource:
        try:
            module = ast.parse(source, filename=filename)
        except SyntaxError as exc:
            return ParsedSource(
                functions=(),
                errors=(
                    Diagnostic(
                        line=exc.lineno,
                        code=DiagnosticCode.SYNTAX_ERROR,
                        message=exc.msg,
                    ),
                ),
            )

        functions = tuple(
            self._parse_function(node)
            for node in module.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )
        return ParsedSource(functions=functions, errors=())

    def _parse_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ParsedFunction:
        diagnostics: list[Diagnostic] = []
        signature = self._build_signature(node, diagnostics)
        docstring, docstring_line = self._extract_generate_body(node)
        return ParsedFunction(
            name=node.name,
            line=node.lineno,
            signature=signature,
            docstring=docstring,
            docstring_line=docstring_line,
            diagnostics=tuple(diagnostics),
        )

    def _build_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        diagnostics: list[Diagnostic],
    ) -> Signature:
        args = node.args
        has_variadic = args.vararg is not None or args.kwarg is not None
        if has_variadic:
            diagnostics.append(
                Diagnostic(
                    line=node.lineno,
                    code=DiagnosticCode.UNSUPPORTED_SIGNATURE,
                    message="variadic arguments are not supported",
                )
            )

        parameters: list[Parameter] = []
        for arg in args.posonlyargs:
            parameters.append(_to_parameter(arg, "positional_only"))
        for arg in args.args:
            parameters.append(_to_parameter(arg, "positional_or_keyword"))
        for arg in args.kwonlyargs:
            parameters.append(_to_parameter(arg, "keyword_only"))

        return Signature(
            parameters=tuple(parameters),
            returns=_annotation_to_str(node.returns),
            has_variadic=has_variadic,
        )

    def _extract_generate_body(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> tuple[str | None, int | None]:
        raw = ast.get_docstring(node, clean=False)
        if raw is None or not node.body:
            return None, None
        first_stmt = node.body[0]
        if not isinstance(first_stmt, ast.Expr):
            return None, None

        dedented = textwrap.dedent(raw).strip("\n")
        if not dedented.lstrip().startswith(GENERATE_MARKER):
            return None, None

        # The DSL body starts one line below the @generate marker
        body = dedented.split(GENERATE_MARKER, 1)[1].lstrip("\n")
        return body, first_stmt.lineno


def _to_parameter(arg: ast.arg, kind: ParameterKind) -> Parameter:
    return Parameter(name=arg.arg, annotation=_annotation_to_str(arg.annotation), kind=kind)


def _annotation_to_str(node: ast.expr | None) -> str | None:
    return None if node is None else ast.unparse(node)
