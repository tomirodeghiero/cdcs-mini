/**
 * CLI wrapper for ``runExpressionOps``.
 *
 * Usage: read a JSON ``ExpressionRequest`` from stdin, write a JSON
 * ``ExpressionResponse`` to stdout. Errors go to stderr with exit code 2
 * — the Python caller distinguishes "no protocol violation, all entries
 * parsed (some may be null)" from "the runtime itself failed".
 */

import { runExpressionOps } from "../expressions.js";
import type { ExpressionRequest, ExpressionResponse } from "../types.js";
import { readAllStdin } from "./stdio.js";

async function main(): Promise<number> {
  const raw = await readAllStdin();
  let request: ExpressionRequest;
  try {
    request = JSON.parse(raw) as ExpressionRequest;
  } catch (err) {
    process.stderr.write(
      `cdcs-mini ts-runtime: invalid JSON on stdin: ${(err as Error).message}\n`,
    );
    return 2;
  }
  if (!Array.isArray(request.operations)) {
    process.stderr.write(`cdcs-mini ts-runtime: request must have an 'operations' array\n`);
    return 2;
  }
  const response: ExpressionResponse = {
    results: runExpressionOps(request.operations),
  };
  process.stdout.write(JSON.stringify(response));
  return 0;
}

main().then(
  (code) => {
    process.exit(code);
  },
  (err: unknown) => {
    process.stderr.write(`cdcs-mini ts-runtime: fatal: ${(err as Error).message}\n`);
    process.exit(2);
  },
);
