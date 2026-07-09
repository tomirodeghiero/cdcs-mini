/**
 * CLI wrapper for ``parseSource``.
 *
 * Usage: read a JSON ``SourceRequest`` from stdin, write a JSON
 * ``SourceResponse`` to stdout. The Python caller invokes this once per
 * ``.ts``/``.tsx`` file under analysis.
 */

import { parseSource } from "../source.js";
import type { SourceRequest, SourceResponse } from "../types.js";
import { readAllStdin } from "./stdio.js";

async function main(): Promise<number> {
  const raw = await readAllStdin();
  let request: SourceRequest;
  try {
    request = JSON.parse(raw) as SourceRequest;
  } catch (err) {
    process.stderr.write(
      `cdcs ts-runtime: invalid JSON on stdin: ${(err as Error).message}\n`,
    );
    return 2;
  }
  if (typeof request.source !== "string" || typeof request.filename !== "string") {
    process.stderr.write(`cdcs ts-runtime: request must have 'source' and 'filename'\n`);
    return 2;
  }
  const parsed = parseSource(request.source, request.filename);
  const response: SourceResponse = {
    functions: parsed.functions,
    errors: parsed.errors,
  };
  process.stdout.write(JSON.stringify(response));
  return 0;
}

main().then(
  (code) => {
    process.exit(code);
  },
  (err: unknown) => {
    process.stderr.write(`cdcs ts-runtime: fatal: ${(err as Error).message}\n`);
    process.exit(2);
  },
);
