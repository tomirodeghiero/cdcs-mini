/**
 * Source-level helpers: walk a TypeScript source file and extract every
 * top-level function declaration plus its ``/** @generate ... *\/``
 * JSDoc body. Mirrors what the Python ``SourceParser`` does for ``.py``
 * sources.
 *
 * "Top level" means either a ``function foo() {}`` declaration or a
 * ``const foo = () => {}`` (and the ``function`` expression variant)
 * declared directly inside the module. Methods, nested functions and
 * class members are intentionally ignored — the contract is module-level.
 */

import ts from "typescript";
import type { SourceDiagnostic, SourceFunction, SourceParameter } from "./types.js";

const GENERATE_MARKER = "@generate";

export type ParsedSource = {
  readonly functions: readonly SourceFunction[];
  readonly errors: readonly SourceDiagnostic[];
};

export function parseSource(source: string, filename: string): ParsedSource {
  const sf = ts.createSourceFile(
    filename,
    source,
    ts.ScriptTarget.Latest,
    /*setParentNodes*/ true,
    ts.ScriptKind.TS,
  );
  const parseErrors = collectParseDiagnostics(sf);
  if (parseErrors.length > 0) {
    return { functions: [], errors: parseErrors };
  }
  const functions: SourceFunction[] = [];
  for (const stmt of sf.statements) {
    const fn = parseTopLevelFunction(stmt, sf);
    if (fn !== null) functions.push(fn);
  }
  return { functions, errors: [] };
}

/* ------------------------------------------------------------------ *
 * Statement-level extraction
 * ------------------------------------------------------------------ */

function parseTopLevelFunction(stmt: ts.Statement, sf: ts.SourceFile): SourceFunction | null {
  if (ts.isFunctionDeclaration(stmt)) {
    return fromFunctionDeclaration(stmt, sf);
  }
  if (ts.isVariableStatement(stmt)) {
    return fromVariableStatement(stmt, sf);
  }
  return null;
}

function fromFunctionDeclaration(
  decl: ts.FunctionDeclaration,
  sf: ts.SourceFile,
): SourceFunction | null {
  if (decl.name === undefined) return null;
  const name = decl.name.text;
  const line = lineOf(decl, sf);
  const { parameters, hasVariadic } = collectParameters(decl.parameters);
  const returns = decl.type ? decl.type.getText() : null;
  const jsdoc = findGenerateJsDoc(decl, sf);
  return {
    name,
    line,
    parameters,
    returns,
    has_variadic: hasVariadic,
    dsl_body: jsdoc?.body ?? null,
    dsl_line: jsdoc?.line ?? null,
  };
}

function fromVariableStatement(
  stmt: ts.VariableStatement,
  sf: ts.SourceFile,
): SourceFunction | null {
  // Only single-declaration ``const foo = () => {}`` / ``= function() {}``
  // forms qualify as top-level functions for our purposes.
  if (stmt.declarationList.declarations.length !== 1) return null;
  const decl = stmt.declarationList.declarations[0];
  if (decl === undefined || decl.initializer === undefined) return null;
  if (!ts.isIdentifier(decl.name)) return null;
  const init = decl.initializer;
  const fnLike = ts.isArrowFunction(init) || ts.isFunctionExpression(init) ? init : null;
  if (fnLike === null) return null;
  const name = decl.name.text;
  const line = lineOf(stmt, sf);
  const { parameters, hasVariadic } = collectParameters(fnLike.parameters);
  const returns = fnLike.type ? fnLike.type.getText() : null;
  const jsdoc = findGenerateJsDoc(stmt, sf);
  return {
    name,
    line,
    parameters,
    returns,
    has_variadic: hasVariadic,
    dsl_body: jsdoc?.body ?? null,
    dsl_line: jsdoc?.line ?? null,
  };
}

/* ------------------------------------------------------------------ *
 * Parameter collection
 * ------------------------------------------------------------------ */

type CollectedParameters = {
  readonly parameters: readonly SourceParameter[];
  readonly hasVariadic: boolean;
};

function collectParameters(params: ts.NodeArray<ts.ParameterDeclaration>): CollectedParameters {
  const parameters: SourceParameter[] = [];
  let hasVariadic = false;
  for (const param of params) {
    const record = toSourceParameter(param);
    if (record.kind === "rest") hasVariadic = true;
    parameters.push(record);
  }
  return { parameters, hasVariadic };
}

function toSourceParameter(param: ts.ParameterDeclaration): SourceParameter {
  const name = ts.isIdentifier(param.name) ? param.name.text : param.name.getText();
  const annotation = param.type ? param.type.getText() : null;
  let kind: SourceParameter["kind"] = "required";
  if (param.dotDotDotToken !== undefined) {
    kind = "rest";
  } else if (param.questionToken !== undefined || param.initializer !== undefined) {
    kind = "optional";
  }
  return { name, annotation, kind };
}

/* ------------------------------------------------------------------ *
 * JSDoc @generate extraction
 * ------------------------------------------------------------------ */

type GenerateBody = {
  readonly body: string;
  readonly line: number;
};

function findGenerateJsDoc(node: ts.Node, sf: ts.SourceFile): GenerateBody | null {
  const ranges = ts.getLeadingCommentRanges(sf.text, node.getFullStart());
  if (ranges === undefined) return null;
  for (const range of ranges) {
    if (range.kind !== ts.SyntaxKind.MultiLineCommentTrivia) continue;
    const raw = sf.text.slice(range.pos, range.end);
    if (!raw.startsWith("/**")) continue;
    const body = extractGenerateBody(raw);
    if (body === null) continue;
    return {
      body,
      // 1-based line of the JSDoc opener
      line: ts.getLineAndCharacterOfPosition(sf, range.pos).line + 1,
    };
  }
  return null;
}

/**
 * Strip the JSDoc framing (``/** ... *\/``) and the leading ``*`` of
 * each line, then return whatever sits below the ``@generate`` marker.
 */
function extractGenerateBody(raw: string): string | null {
  // Trim the outer ``/**`` and ``*/`` and break into lines.
  const inner = raw.replace(/^\/\*\*/, "").replace(/\*\/$/, "");
  const lines = inner.split(/\r?\n/).map((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("*")) {
      return trimmed.replace(/^\*\s?/, "");
    }
    return trimmed;
  });
  const markerIdx = lines.findIndex((line) => line.trim() === GENERATE_MARKER);
  if (markerIdx === -1) return null;
  // Body lives below the marker. Drop any all-blank trailing lines so
  // the Python side doesn't have to.
  const body = lines
    .slice(markerIdx + 1)
    .join("\n")
    .replace(/\s+$/, "");
  return body;
}

/* ------------------------------------------------------------------ *
 * Diagnostics
 * ------------------------------------------------------------------ */

function collectParseDiagnostics(sf: ts.SourceFile): readonly SourceDiagnostic[] {
  const withDiags = sf as ts.SourceFile & {
    parseDiagnostics?: readonly ts.Diagnostic[];
  };
  const diags = withDiags.parseDiagnostics;
  if (diags === undefined || diags.length === 0) return [];
  return diags.map((d) => toSourceDiagnostic(d, sf));
}

function toSourceDiagnostic(diag: ts.Diagnostic, sf: ts.SourceFile): SourceDiagnostic {
  const line =
    diag.start !== undefined ? ts.getLineAndCharacterOfPosition(sf, diag.start).line + 1 : null;
  const message = ts.flattenDiagnosticMessageText(diag.messageText, "\n");
  return { line, code: "SyntaxError", message };
}

/* ------------------------------------------------------------------ *
 * Position helpers
 * ------------------------------------------------------------------ */

function lineOf(node: ts.Node, sf: ts.SourceFile): number {
  return ts.getLineAndCharacterOfPosition(sf, node.getStart(sf)).line + 1;
}
