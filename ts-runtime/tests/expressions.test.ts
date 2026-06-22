import { describe, expect, test } from "vitest";
import {
  extractCallTarget,
  extractIdentifiers,
  isValidAnnotation,
  parseParameterList,
  runExpressionOps,
} from "../src/expressions.js";
import type {
  AnnotationResult,
  CallTargetResult,
  IdentifiersResult,
  ParameterListResult,
} from "../src/types.js";

describe("extractIdentifiers", () => {
  test("returns referenced names in a sorted list, callees excluded", () => {
    expect(extractIdentifiers("a + b * c")).toEqual(["a", "b", "c"]);
  });

  test("excludes call targets, keeps argument identifiers", () => {
    expect(extractIdentifiers("strip(value)")).toEqual(["value"]);
  });

  test("nested calls are handled", () => {
    expect(extractIdentifiers("parseInt(strip(value), radix)")).toEqual(["radix", "value"]);
  });

  test("returns null for unparseable garbage", () => {
    expect(extractIdentifiers("@@@ not an expression @@@")).toBeNull();
  });

  test("returns null for empty / whitespace-only", () => {
    expect(extractIdentifiers("")).toBeNull();
    expect(extractIdentifiers("   ")).toBeNull();
  });

  test("comparison expressions extract both sides", () => {
    expect(extractIdentifiers("ttl > 0")).toEqual(["ttl"]);
    expect(extractIdentifiers("board[position] === ''")).toEqual(["board", "position"]);
  });

  test("excludes property names in member-access (obj.attr)", () => {
    // ``length`` is a property, not a parameter — mirrors Python where
    // ``obj.attr`` stores ``attr`` as a string, never as an identifier.
    expect(extractIdentifiers("value.length > 0")).toEqual(["value"]);
    expect(extractIdentifiers("user.profile.name")).toEqual(["user"]);
  });
});

describe("extractCallTarget", () => {
  test("returns the callee name for a bare call", () => {
    expect(extractCallTarget('parsePort("80")')).toBe("parsePort");
  });

  test("returns null for method calls", () => {
    expect(extractCallTarget("obj.method(x)")).toBeNull();
  });

  test("returns null for non-call expressions", () => {
    expect(extractCallTarget("a + b")).toBeNull();
    expect(extractCallTarget("42")).toBeNull();
  });

  test("returns null for unparseable input", () => {
    expect(extractCallTarget("@@@")).toBeNull();
  });
});

describe("isValidAnnotation", () => {
  test("accepts primitive types", () => {
    expect(isValidAnnotation("string")).toBe(true);
    expect(isValidAnnotation("number")).toBe(true);
    expect(isValidAnnotation("boolean")).toBe(true);
  });

  test("accepts generics and unions", () => {
    expect(isValidAnnotation("Array<number>")).toBe(true);
    expect(isValidAnnotation("string | null")).toBe(true);
    expect(isValidAnnotation("{ x: number; y: string }")).toBe(true);
    expect(isValidAnnotation("readonly number[]")).toBe(true);
  });

  test("rejects empty or whitespace input", () => {
    expect(isValidAnnotation("")).toBe(false);
    expect(isValidAnnotation("   ")).toBe(false);
  });

  test("rejects pure-garbage input", () => {
    expect(isValidAnnotation("not a type at all !")).toBe(false);
    expect(isValidAnnotation("@@@")).toBe(false);
  });
});

describe("parseParameterList", () => {
  test("empty list yields no parameters", () => {
    expect(parseParameterList("")).toEqual([]);
  });

  test("required parameters with annotations", () => {
    expect(parseParameterList("name: string, count: number")).toEqual([
      { name: "name", annotation: "string", kind: "required" },
      { name: "count", annotation: "number", kind: "required" },
    ]);
  });

  test("optional and default parameters become 'optional'", () => {
    const parsed = parseParameterList("name?: string, count: number = 0");
    expect(parsed).toEqual([
      { name: "name", annotation: "string", kind: "optional" },
      { name: "count", annotation: "number", kind: "optional" },
    ]);
  });

  test("rest parameters become 'rest'", () => {
    const parsed = parseParameterList("...items: number[]");
    expect(parsed).toEqual([{ name: "items", annotation: "number[]", kind: "rest" }]);
  });

  test("returns null for unparseable lists", () => {
    expect(parseParameterList("name string,")).toBeNull();
  });
});

describe("runExpressionOps batched protocol", () => {
  test("returns one result per operation, in order, keyed by id", () => {
    const results = runExpressionOps([
      { kind: "identifiers", id: "0", expression: "a + b" },
      { kind: "call_target", id: "1", expression: "foo(x)" },
      { kind: "annotation", id: "2", expression: "number" },
      { kind: "param_list", id: "3", expression: "x: number" },
    ]);
    expect(results).toHaveLength(4);

    const idents = results[0] as IdentifiersResult;
    expect(idents.id).toBe("0");
    expect(idents.kind).toBe("identifiers");
    expect(idents.identifiers).toEqual(["a", "b"]);

    const target = results[1] as CallTargetResult;
    expect(target.kind).toBe("call_target");
    expect(target.call_target).toBe("foo");

    const annotation = results[2] as AnnotationResult;
    expect(annotation.kind).toBe("annotation");
    expect(annotation.valid_annotation).toBe(true);

    const params = results[3] as ParameterListResult;
    expect(params.kind).toBe("param_list");
    expect(params.parameters).toEqual([{ name: "x", annotation: "number", kind: "required" }]);
  });

  test("an unparseable operation becomes null in its result slot", () => {
    const results = runExpressionOps([{ kind: "identifiers", id: "0", expression: "@@@" }]);
    const idents = results[0] as IdentifiersResult;
    expect(idents.identifiers).toBeNull();
  });
});
