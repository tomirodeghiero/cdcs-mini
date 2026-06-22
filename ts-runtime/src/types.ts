/**
 * JSON protocol shared between the Python caller and the Node helpers.
 *
 * Every CLI script is one round trip: read a request from stdin, write
 * a response to stdout. The Python side speaks this in batches so we
 * pay the Node startup cost once per source file, not once per
 * expression.
 */

/** Identifier extraction: which names does an expression reference? */
export type IdentifiersOp = {
  readonly kind: "identifiers";
  /** Caller-supplied label so the response can be re-keyed in order. */
  readonly id: string;
  /** Raw expression text, as it appears inside the DSL. */
  readonly expression: string;
};

/** Call-target extraction: ``foo(args)`` -> ``"foo"`` (and only that shape). */
export type CallTargetOp = {
  readonly kind: "call_target";
  readonly id: string;
  readonly expression: string;
};

/** Annotation validation: ``Array<string>`` parses, ``not a type`` doesn't. */
export type AnnotationOp = {
  readonly kind: "annotation";
  readonly id: string;
  readonly expression: string;
};

/** Parameter list parsing for a callable signature in the DSL ``calls:`` section. */
export type ParameterListOp = {
  readonly kind: "param_list";
  readonly id: string;
  readonly expression: string;
};

export type ExpressionOp = IdentifiersOp | CallTargetOp | AnnotationOp | ParameterListOp;

export type ExpressionRequest = {
  readonly operations: readonly ExpressionOp[];
};

/** A parameter as it lands in a parsed ``calls:`` callable signature. */
export type ParameterRecord = {
  /** Identifier of the parameter. */
  readonly name: string;
  /** Type annotation as written (``"string"``, ``"number[]"``, ...) or null. */
  readonly annotation: string | null;
  /** ``"required"`` / ``"optional"`` (``param?: T``) / ``"rest"`` (``...rest: T[]``). */
  readonly kind: "required" | "optional" | "rest";
};

export type IdentifiersResult = {
  readonly id: string;
  readonly kind: "identifiers";
  /** Lowercased identifier list, or null when the expression doesn't parse. */
  readonly identifiers: readonly string[] | null;
};

export type CallTargetResult = {
  readonly id: string;
  readonly kind: "call_target";
  /** Name of the called function, or null if the expression isn't a bare call. */
  readonly call_target: string | null;
};

export type AnnotationResult = {
  readonly id: string;
  readonly kind: "annotation";
  readonly valid_annotation: boolean;
};

export type ParameterListResult = {
  readonly id: string;
  readonly kind: "param_list";
  /** Parsed parameters, or null if the list isn't a valid TS parameter list. */
  readonly parameters: readonly ParameterRecord[] | null;
};

export type ExpressionResult =
  | IdentifiersResult
  | CallTargetResult
  | AnnotationResult
  | ParameterListResult;

export type ExpressionResponse = {
  readonly results: readonly ExpressionResult[];
};

/* --------------------------------------------------------------------------
 * Source-level protocol — extract top-level functions + their JSDoc body.
 * ------------------------------------------------------------------------ */

export type SourceRequest = {
  /** TypeScript source code to inspect (entire file as one string). */
  readonly source: string;
  /** Logical filename. Used for diagnostic output and nothing else. */
  readonly filename: string;
};

export type SourceParameter = {
  readonly name: string;
  readonly annotation: string | null;
  readonly kind: "required" | "optional" | "rest";
};

export type SourceFunction = {
  readonly name: string;
  /** 1-based line number where the function declaration starts. */
  readonly line: number;
  readonly parameters: readonly SourceParameter[];
  readonly returns: string | null;
  /** True if the parameter list contains a rest element. */
  readonly has_variadic: boolean;
  /** Raw JSDoc body of the ``@generate`` block, or null if none. */
  readonly dsl_body: string | null;
  /** 1-based line where the ``@generate`` block opens; null if no JSDoc. */
  readonly dsl_line: number | null;
};

export type SourceDiagnostic = {
  /** 1-based line, or null when the diagnostic is file-level. */
  readonly line: number | null;
  readonly code: string;
  readonly message: string;
};

export type SourceResponse = {
  readonly functions: readonly SourceFunction[];
  readonly errors: readonly SourceDiagnostic[];
};
