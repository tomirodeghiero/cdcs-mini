/**
 * Expression-level helpers used by the DSL parser on the Python side.
 *
 * Every helper takes one expression string and returns either a typed
 * result or null. Null is the "unparseable" signal — the caller turns
 * it into a ``MalformedDSLError`` diagnostic. We never throw.
 */

import ts from "typescript";
import type {
  AnnotationResult,
  CallTargetResult,
  ExpressionOp,
  ExpressionResult,
  IdentifiersResult,
  ParameterListResult,
  ParameterRecord,
} from "./types.js";

/* ------------------------------------------------------------------ *
 * extract_identifiers
 * ------------------------------------------------------------------ */

/**
 * Identifier names referenced inside a TS expression, excluding the
 * names of functions being *called*. Mirrors the Python semantics:
 * ``foo(x, y)`` -> ``["x", "y"]``.
 *
 * Returns null if the expression doesn't parse as a valid TS expression.
 */
export function extractIdentifiers(expression: string): readonly string[] | null {
  const expr = parseAsExpression(expression);
  if (expr === null) return null;

  // Collect identifier nodes that should NOT count as parameter references:
  //   - callee names in ``foo(args)``  (excluded so ``foo`` doesn't leak)
  //   - property names in ``obj.attr`` (mirrors Python: ``Attribute.attr``
  //     is a string, not a Name, so it never gets picked up there either)
  //   - property names in ``obj[key]`` are still captured via ``key``
  //     because that's a real reference.
  const excluded = new Set<ts.Node>();
  visit(expr, (node) => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression)) {
      excluded.add(node.expression);
    }
    if (ts.isPropertyAccessExpression(node) && ts.isIdentifier(node.name)) {
      excluded.add(node.name);
    }
  });

  const identifiers = new Set<string>();
  visit(expr, (node) => {
    if (ts.isIdentifier(node) && !excluded.has(node)) {
      identifiers.add(node.text);
    }
  });
  return Array.from(identifiers).sort();
}

/* ------------------------------------------------------------------ *
 * extract_call_target
 * ------------------------------------------------------------------ */

/**
 * The name of the function being called in ``foo(args)``. Returns null
 * when the expression is not a *single bare call* — property accesses
 * (``obj.method(x)``) and binary expressions return null. Same shape as
 * the Python implementation.
 */
export function extractCallTarget(expression: string): string | null {
  const expr = parseAsExpression(expression);
  if (expr === null) return null;
  if (!ts.isCallExpression(expr)) return null;
  if (!ts.isIdentifier(expr.expression)) return null;
  return expr.expression.text;
}

/* ------------------------------------------------------------------ *
 * is_valid_annotation
 * ------------------------------------------------------------------ */

/**
 * True when the string parses as a syntactically valid TS type
 * annotation (``string``, ``Array<number>``, ``{ x: number }``, ...).
 *
 * Implementation trick: wrap the annotation inside a placeholder type
 * alias and ask TS to parse it. Anything that parses cleanly is a
 * valid annotation.
 */
export function isValidAnnotation(expression: string): boolean {
  const trimmed = expression.trim();
  if (trimmed.length === 0) return false;
  const probe = `type __probe__ = ${trimmed};`;
  const sf = ts.createSourceFile(
    "__probe__.ts",
    probe,
    ts.ScriptTarget.Latest,
    /*setParentNodes*/ true,
    ts.ScriptKind.TS,
  );
  if (hasParseError(sf)) return false;
  const stmt = sf.statements[0];
  if (stmt === undefined || !ts.isTypeAliasDeclaration(stmt)) return false;
  // The TS parser is permissive — it'll happily build an ``ErrorType`` for
  // garbage input. Re-validate by walking the alias body for any token of
  // kind Unknown.
  return !containsUnknownTokens(stmt.type);
}

/* ------------------------------------------------------------------ *
 * parse_parameter_list
 * ------------------------------------------------------------------ */

/**
 * Parse the body of a parenthesised parameter list as it appears in a
 * DSL ``calls:`` signature (``"x: number, y?: string"``). Returns null
 * when the list isn't a valid TS parameter list.
 */
export function parseParameterList(expression: string): readonly ParameterRecord[] | null {
  // Probe by wrapping the parameter list inside an arrow function — that
  // lets TS apply its full parameter-list grammar, including type
  // annotations, defaults, optional markers and rest elements.
  const probe = `const __probe__ = (${expression}): void => { return; };`;
  const sf = ts.createSourceFile(
    "__probe__.ts",
    probe,
    ts.ScriptTarget.Latest,
    /*setParentNodes*/ true,
    ts.ScriptKind.TS,
  );
  if (hasParseError(sf)) return null;
  const stmt = sf.statements[0];
  if (stmt === undefined || !ts.isVariableStatement(stmt)) return null;
  const decl = stmt.declarationList.declarations[0];
  if (decl === undefined || decl.initializer === undefined) return null;
  if (!ts.isArrowFunction(decl.initializer)) return null;
  return decl.initializer.parameters.map(toParameterRecord);
}

/* ------------------------------------------------------------------ *
 * Batched protocol entry point
 * ------------------------------------------------------------------ */

/** Apply each operation in order and collect typed results. */
export function runExpressionOps(ops: readonly ExpressionOp[]): readonly ExpressionResult[] {
  return ops.map(runOne);
}

function runOne(op: ExpressionOp): ExpressionResult {
  switch (op.kind) {
    case "identifiers":
      return {
        id: op.id,
        kind: "identifiers",
        identifiers: extractIdentifiers(op.expression),
      } satisfies IdentifiersResult;
    case "call_target":
      return {
        id: op.id,
        kind: "call_target",
        call_target: extractCallTarget(op.expression),
      } satisfies CallTargetResult;
    case "annotation":
      return {
        id: op.id,
        kind: "annotation",
        valid_annotation: isValidAnnotation(op.expression),
      } satisfies AnnotationResult;
    case "param_list":
      return {
        id: op.id,
        kind: "param_list",
        parameters: parseParameterList(op.expression),
      } satisfies ParameterListResult;
  }
}

/* ------------------------------------------------------------------ *
 * Helpers
 * ------------------------------------------------------------------ */

/**
 * Parse ``expression`` as a standalone TS expression. Returns the
 * inner node (without the synthetic wrapper) or null on parse failure.
 */
function parseAsExpression(expression: string): ts.Expression | null {
  const trimmed = expression.trim();
  if (trimmed.length === 0) return null;
  // Use an expression statement as the probe. ``(expr);`` triggers TS's
  // expression-statement grammar so any binary/call/identifier shape is
  // accepted, just like ``ast.parse(..., mode="eval")`` on the Python side.
  const probe = `(${trimmed});`;
  const sf = ts.createSourceFile(
    "__probe__.ts",
    probe,
    ts.ScriptTarget.Latest,
    /*setParentNodes*/ true,
    ts.ScriptKind.TS,
  );
  if (hasParseError(sf)) return null;
  const stmt = sf.statements[0];
  if (stmt === undefined || !ts.isExpressionStatement(stmt)) return null;
  // Unwrap the synthetic outer parentheses we added in the probe.
  const outer = stmt.expression;
  if (ts.isParenthesizedExpression(outer)) {
    return outer.expression;
  }
  return outer;
}

function hasParseError(sourceFile: ts.SourceFile): boolean {
  // ``parseDiagnostics`` is part of TS's internal SourceFile shape;
  // it's the canonical source of "did this file parse cleanly?".
  const withDiags = sourceFile as ts.SourceFile & {
    parseDiagnostics?: readonly ts.Diagnostic[];
  };
  const diags = withDiags.parseDiagnostics;
  return diags !== undefined && diags.length > 0;
}

function visit(node: ts.Node, callback: (node: ts.Node) => void): void {
  callback(node);
  node.forEachChild((child) => visit(child, callback));
}

function containsUnknownTokens(node: ts.Node): boolean {
  let found = false;
  visit(node, (child) => {
    if (child.kind === ts.SyntaxKind.Unknown) found = true;
  });
  return found;
}

function toParameterRecord(param: ts.ParameterDeclaration): ParameterRecord {
  const name = ts.isIdentifier(param.name) ? param.name.text : param.name.getText();
  const annotation = param.type ? param.type.getText() : null;
  let kind: ParameterRecord["kind"] = "required";
  if (param.dotDotDotToken !== undefined) {
    kind = "rest";
  } else if (param.questionToken !== undefined || param.initializer !== undefined) {
    kind = "optional";
  }
  return { name, annotation, kind };
}
