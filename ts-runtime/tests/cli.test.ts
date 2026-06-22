/**
 * Spawn the CLI bins as real subprocesses (via ``tsx`` so we don't need
 * to compile first), send JSON on stdin, parse the response. This is
 * the contract the Python side will consume in Fase 3, so it earns its
 * own end-to-end check.
 */

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";
import type {
  ExpressionRequest,
  ExpressionResponse,
  SourceRequest,
  SourceResponse,
} from "../src/types.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");
const tsxBin = path.join(projectRoot, "node_modules", ".bin", "tsx");
const expressionsBin = path.join(projectRoot, "src", "bin", "parse-expressions.ts");
const sourceBin = path.join(projectRoot, "src", "bin", "parse-source.ts");

async function callBin<T>(bin: string, payload: unknown): Promise<T> {
  return await new Promise<T>((resolve, reject) => {
    const child = spawn(tsxBin, [bin], { stdio: ["pipe", "pipe", "pipe"] });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    child.stdout.on("data", (c: Buffer) => stdoutChunks.push(c));
    child.stderr.on("data", (c: Buffer) => stderrChunks.push(c));
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        const stderr = Buffer.concat(stderrChunks).toString("utf8");
        reject(new Error(`bin exited ${code}: ${stderr}`));
        return;
      }
      try {
        const text = Buffer.concat(stdoutChunks).toString("utf8");
        resolve(JSON.parse(text) as T);
      } catch (err) {
        reject(err as Error);
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

describe("parse-expressions CLI", () => {
  test("round-trips a batched request through stdin/stdout", async () => {
    const request: ExpressionRequest = {
      operations: [
        { kind: "identifiers", id: "x", expression: "ttl > 0" },
        { kind: "call_target", id: "y", expression: 'parsePort("80")' },
      ],
    };
    const response = await callBin<ExpressionResponse>(expressionsBin, request);
    expect(response.results).toHaveLength(2);
    expect(response.results[0]).toMatchObject({
      id: "x",
      kind: "identifiers",
      identifiers: ["ttl"],
    });
    expect(response.results[1]).toMatchObject({
      id: "y",
      kind: "call_target",
      call_target: "parsePort",
    });
  });
});

describe("parse-source CLI", () => {
  test("round-trips a TS source through stdin/stdout", async () => {
    const request: SourceRequest = {
      source: `
/** @generate
 * behavior:
 *   return value
 *
 * examples:
 *   identity(1) == 1
 */
export function identity(value: number): number { return value; }
`.trim(),
      filename: "demo.ts",
    };
    const response = await callBin<SourceResponse>(sourceBin, request);
    expect(response.errors).toEqual([]);
    expect(response.functions).toHaveLength(1);
    expect(response.functions[0]?.name).toBe("identity");
    expect(response.functions[0]?.dsl_body).toContain("behavior:");
  });
});
