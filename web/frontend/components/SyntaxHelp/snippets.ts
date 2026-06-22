import type { SourceLanguage } from "@/components/SourceCard";

export type Snippet = {
  id: string;
  title: string;
  blurb: string;
  code: string;
};

const PY_PARSE_PORT = `def parse_port(value: str) -> int:
    """@generate
    behavior:
      strip(value)
      require value matches digits
      require 1 <= int(value) <= 65535
      return int(value)
    examples:
      parse_port("80") == 80
      parse_port("443") == 443
      parse_port("0") raises ValueError
    constraints:
      no_imports
      no_network
      no_filesystem
    """
`;

const PY_SLUGIFY = `def slugify(text: str) -> str:
    """@generate
    behavior:
      strip(text)
      require len(text) > 0
      return text.lower().replace(" ", "-")
    examples:
      slugify("Hello World") == "hello-world"
      slugify("foo") == "foo"
      slugify("") raises ValueError
    constraints:
      no_imports
      no_network
      no_filesystem
    """
`;

const PY_CLAMP = `def clamp(value: int, lo: int, hi: int) -> int:
    """@generate
    behavior:
      require lo <= hi
      return min(max(value, lo), hi)
    examples:
      clamp(5, 0, 10) == 5
      clamp(-3, 0, 10) == 0
      clamp(99, 0, 10) == 10
    constraints:
      no_imports
      no_network
      no_filesystem
    """
`;

const PY_PARSE_BOOL = `def parse_bool(value: str) -> bool:
    """@generate
    behavior:
      strip(value)
      require len(value) > 0
      return value.lower() == "true"
    examples:
      parse_bool("true") == True
      parse_bool("FALSE") == False
      parse_bool("") raises ValueError
    constraints:
      no_imports
      no_network
      no_filesystem
    """
`;

const PY_TOKEN_ISSUE = `def issue(self, user_id: int, ttl_seconds: int) -> str:
    """@generate
    behavior:
      require ttl_seconds > 0
      return self._sign(str(user_id))
    examples:
      issue(42, 60) == "signed:42"
      issue(1, 0) raises ValueError
    calls:
      self._sign(payload: str) -> str
      self._now() -> int
    reads:
      self.secret_key: bytes
    constraints:
      no_imports
    """
`;

const TS_PARSE_PORT = `/**
 * @generate
 * behavior:
 *   strip(value)
 *   require value matches digits
 *   require 1 <= parseInt(value) <= 65535
 *   return parseInt(value)
 *
 * examples:
 *   parsePort("80") == 80
 *   parsePort("443") == 443
 *   parsePort("0") raises ValueError
 *
 * constraints:
 *   no_imports
 *   no_network
 *   no_filesystem
 */
export function parsePort(value: string): number {
  return 0;
}
`;

const TS_SLUGIFY = `/**
 * @generate
 * behavior:
 *   strip(text)
 *   require text.length > 0
 *   return text.toLowerCase().replace(" ", "-")
 *
 * examples:
 *   slugify("Hello World") == "hello-world"
 *   slugify("foo") == "foo"
 *   slugify("") raises ValueError
 *
 * constraints:
 *   no_imports
 *   no_network
 *   no_filesystem
 */
export function slugify(text: string): string {
  return "";
}
`;

const TS_CLAMP = `/**
 * @generate
 * behavior:
 *   require lo <= hi
 *   return Math.min(Math.max(value, lo), hi)
 *
 * examples:
 *   clamp(5, 0, 10) == 5
 *   clamp(-3, 0, 10) == 0
 *   clamp(99, 0, 10) == 10
 *
 * constraints:
 *   no_imports
 *   no_network
 *   no_filesystem
 */
export function clamp(value: number, lo: number, hi: number): number {
  return 0;
}
`;

const TS_PARSE_BOOL = `/**
 * @generate
 * behavior:
 *   strip(value)
 *   require value.length > 0
 *   return value.toLowerCase() === "true"
 *
 * examples:
 *   parseBool("true") == true
 *   parseBool("FALSE") == false
 *   parseBool("") raises ValueError
 *
 * constraints:
 *   no_imports
 *   no_network
 *   no_filesystem
 */
export function parseBool(value: string): boolean {
  return false;
}
`;

const TS_TOKEN_ISSUE = `/**
 * @generate
 * behavior:
 *   require ttlSeconds > 0
 *   return this._sign(String(userId))
 *
 * examples:
 *   issue(42, 60) == "signed:42"
 *   issue(1, 0) raises ValueError
 *
 * calls:
 *   self._sign(payload: string) -> string
 *   self._now() -> number
 *
 * reads:
 *   self.secretKey: Uint8Array
 *
 * constraints:
 *   no_imports
 */
export function issue(this: TokenService, userId: number, ttlSeconds: number): string {
  return "";
}
`;

const PYTHON_SNIPPETS: readonly Snippet[] = [
  {
    id: "parse_port",
    title: "parse_port",
    blurb: "Numeric validation with require + return",
    code: PY_PARSE_PORT,
  },
  {
    id: "slugify",
    title: "slugify",
    blurb: "String manipulation with non-empty guard",
    code: PY_SLUGIFY,
  },
  {
    id: "clamp",
    title: "clamp",
    blurb: "Multi-arg precondition (lo <= hi)",
    code: PY_CLAMP,
  },
  {
    id: "parse_bool",
    title: "parse_bool",
    blurb: "Boolean coercion with raises example",
    code: PY_PARSE_BOOL,
  },
  {
    id: "token_issue",
    title: "TokenService.issue",
    blurb: "Class method using calls: + reads:",
    code: PY_TOKEN_ISSUE,
  },
];

const TYPESCRIPT_SNIPPETS: readonly Snippet[] = [
  {
    id: "parse_port",
    title: "parsePort",
    blurb: "Numeric validation with require + return",
    code: TS_PARSE_PORT,
  },
  {
    id: "slugify",
    title: "slugify",
    blurb: "String manipulation with non-empty guard",
    code: TS_SLUGIFY,
  },
  {
    id: "clamp",
    title: "clamp",
    blurb: "Multi-arg precondition (lo <= hi)",
    code: TS_CLAMP,
  },
  {
    id: "parse_bool",
    title: "parseBool",
    blurb: "Boolean coercion with raises example",
    code: TS_PARSE_BOOL,
  },
  {
    id: "token_issue",
    title: "TokenService.issue",
    blurb: "Class method using calls: + reads:",
    code: TS_TOKEN_ISSUE,
  },
];

export function snippetsFor(language: SourceLanguage): readonly Snippet[] {
  return language === "typescript" ? TYPESCRIPT_SNIPPETS : PYTHON_SNIPPETS;
}
