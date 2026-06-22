import { describe, expect, test } from "vitest";
import { parseSource } from "../src/source.js";

const SAMPLE = `
/**
 * @generate
 * behavior:
 *   require value.length > 0
 *   return parseInt(value, 10)
 *
 * examples:
 *   parsePort("80") == 80
 *   parsePort("0") raises ValueError
 *
 * constraints:
 *   no_imports
 */
export function parsePort(value: string): number {
  return 0;
}

export const newBoard = (): readonly string[] => [];

export class Helper {
  /** @generate behavior: return 1 */
  doStuff(): number {
    return 0;
  }
}
`.trim();

describe("parseSource", () => {
  test("extracts top-level function declarations", () => {
    const result = parseSource(SAMPLE, "sample.ts");
    expect(result.errors).toEqual([]);
    const names = result.functions.map((f) => f.name);
    expect(names).toContain("parsePort");
  });

  test("extracts top-level arrow-function consts", () => {
    const result = parseSource(SAMPLE, "sample.ts");
    const names = result.functions.map((f) => f.name);
    expect(names).toContain("newBoard");
  });

  test("ignores methods inside classes", () => {
    const result = parseSource(SAMPLE, "sample.ts");
    const names = result.functions.map((f) => f.name);
    expect(names).not.toContain("doStuff");
  });

  test("attaches @generate JSDoc body to the function it precedes", () => {
    const result = parseSource(SAMPLE, "sample.ts");
    const parsePort = result.functions.find((f) => f.name === "parsePort");
    expect(parsePort).toBeDefined();
    expect(parsePort?.dsl_body).toContain("behavior:");
    expect(parsePort?.dsl_body).toContain("require value.length > 0");
    expect(parsePort?.dsl_line).toBeGreaterThan(0);
  });

  test("captures parameter shape and return type", () => {
    const result = parseSource(SAMPLE, "sample.ts");
    const parsePort = result.functions.find((f) => f.name === "parsePort");
    expect(parsePort?.parameters).toEqual([
      { name: "value", annotation: "string", kind: "required" },
    ]);
    expect(parsePort?.returns).toBe("number");
    expect(parsePort?.has_variadic).toBe(false);
  });

  test("functions without @generate JSDoc have null dsl fields", () => {
    const result = parseSource(SAMPLE, "sample.ts");
    const newBoard = result.functions.find((f) => f.name === "newBoard");
    expect(newBoard?.dsl_body).toBeNull();
    expect(newBoard?.dsl_line).toBeNull();
  });

  test("reports syntax errors instead of returning malformed functions", () => {
    const broken = "function broken(x: \nreturn x;";
    const result = parseSource(broken, "broken.ts");
    expect(result.functions).toEqual([]);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors[0]?.code).toBe("SyntaxError");
  });

  test("detects rest parameters as variadic", () => {
    const source = `
/** @generate
 * behavior:
 *   return items.length
 *
 * examples:
 *   sumAll(1, 2, 3) == 6
 */
export function sumAll(...items: number[]): number {
  return 0;
}
`.trim();
    const result = parseSource(source, "rest.ts");
    expect(result.functions[0]?.has_variadic).toBe(true);
    expect(result.functions[0]?.parameters[0]?.kind).toBe("rest");
  });
});
