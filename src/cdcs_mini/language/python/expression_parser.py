"""Python implementation of the ``ExpressionParser`` Protocol.

Carries the AST-based logic that used to live as static helpers inside
``DSLParser``. Centralising it here lets the DSL parser stay
language-agnostic and lets a TypeScript adapter plug in equivalent logic
through the same Protocol.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from cdcs_mini.domain.models import Parameter, ParameterKind


@dataclass(frozen=True, slots=True)
class PythonExpressionParser:
    """Stateless expression parser that uses :mod:`ast` under the hood."""

    def extract_identifiers(self, expression: str) -> frozenset[str] | None:
        tree = self._try_parse_eval(expression)
        if tree is None:
            return None
        callee_ids = self._call_func_node_ids(tree)
        return frozenset(
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and id(node) not in callee_ids
        )

    def extract_call_target(self, expression: str) -> str | None:
        tree = self._try_parse_eval(expression)
        if tree is None:
            return None
        call = tree.body
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            return None
        return call.func.id

    def is_valid_annotation(self, annotation: str) -> bool:
        return self._try_parse_eval(annotation) is not None

    def parse_parameter_list(self, params_text: str) -> tuple[Parameter, ...] | None:
        # Validate by building a probe def and using ast — gives us free
        # support for type annotations, defaults and keyword-only markers.
        probe = f"def __probe__({params_text}) -> None: pass"
        try:
            tree = ast.parse(probe)
        except SyntaxError:
            return None
        func_def = tree.body[0]
        if not isinstance(func_def, ast.FunctionDef):
            return None
        if func_def.args.vararg is not None or func_def.args.kwarg is not None:
            return None
        return self._collect_callable_parameters(func_def.args)

    # --- helpers ------------------------------------------------------

    @staticmethod
    def _try_parse_eval(expression: str) -> ast.Expression | None:
        try:
            return ast.parse(expression, mode="eval")
        except SyntaxError:
            return None

    @staticmethod
    def _call_func_node_ids(tree: ast.AST) -> set[int]:
        return {
            id(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

    @staticmethod
    def _collect_callable_parameters(args: ast.arguments) -> tuple[Parameter, ...]:
        def to_param(arg: ast.arg, kind: ParameterKind) -> Parameter:
            annotation = None if arg.annotation is None else ast.unparse(arg.annotation)
            return Parameter(name=arg.arg, annotation=annotation, kind=kind)

        return (
            *(to_param(a, "positional_only") for a in args.posonlyargs),
            *(to_param(a, "positional_or_keyword") for a in args.args),
            *(to_param(a, "keyword_only") for a in args.kwonlyargs),
        )
