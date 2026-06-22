import type { SourceLanguage } from "@/components/SourceCard";

type Props = { language: SourceLanguage };

export function Cheatsheet({ language }: Props) {
  const isTs = language === "typescript";
  return (
    <div className="space-y-5 text-sm text-slate-700 dark:text-slate-300">
      <Intro language={language} />

      <Section title="1. Wrap the contract">
        <p>
          The contract lives inside a {isTs ? "JSDoc block" : "docstring"} that starts with{" "}
          <Mono>@generate</Mono>. Anything outside it is plain {isTs ? "TypeScript" : "Python"} —
          the analyzer ignores it.
        </p>
        <CodeBox>{isTs ? TS_WRAPPER : PY_WRAPPER}</CodeBox>
      </Section>

      <Section title="2. behavior: — what the function does">
        <p>Each line is one step. The analyzer classifies it as:</p>
        <ul className="ml-4 list-disc space-y-1">
          <li>
            <Mono>require &lt;cond&gt;</Mono> — precondition (guard).
          </li>
          <li>
            <Mono>return &lt;expr&gt;</Mono> — the value the function produces.
          </li>
          <li>
            <Mono>operation</Mono> — anything else (a side-effect-free helper call like{" "}
            <Mono>strip(value)</Mono>).
          </li>
        </ul>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Every identifier you mention must exist in the signature, otherwise{" "}
          <Mono>InconsistentPromptError</Mono>.
        </p>
      </Section>

      <Section title="3. examples: — required">
        <p>One example per line, in one of two forms:</p>
        <CodeBox>{isTs ? TS_EXAMPLES : PY_EXAMPLES}</CodeBox>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Without this section the analyzer fires <Mono>MissingSamplesError</Mono>. For
          container params (string / list / dict) include an empty-case example or you'll get{" "}
          <Mono>IncompletePromptError</Mono>.
        </p>
      </Section>

      <Section title="4. constraints: — optional">
        <p>A free-form list of hard rules the synthesizer must obey:</p>
        <CodeBox>{CONSTRAINTS}</CodeBox>
      </Section>

      <Section title="5. calls: / reads: — only for class methods">
        <p>
          When the function uses <Mono>{isTs ? "this.X" : "self.X"}</Mono>, every callee and
          attribute must be declared. The list doubles as the AST allow-list at synthesis time.
        </p>
        <CodeBox>{isTs ? TS_CALLS : PY_CALLS}</CodeBox>
      </Section>

      <Section title="Common errors at a glance">
        <ul className="ml-4 list-disc space-y-1 text-xs">
          <li>
            <Mono>MissingGenerateError</Mono> — no <Mono>@generate</Mono> marker.
          </li>
          <li>
            <Mono>MissingSamplesError</Mono> — no <Mono>examples:</Mono> section.
          </li>
          <li>
            <Mono>InconsistentPromptError</Mono> — referenced a name the signature doesn't expose.
          </li>
          <li>
            <Mono>UnsupportedSignatureError</Mono> — used{" "}
            <Mono>{isTs ? "...rest" : "*args / **kwargs"}</Mono>.
          </li>
          <li>
            <Mono>InvalidExampleError</Mono> — example missing <Mono>==</Mono> /{" "}
            <Mono>raises</Mono>.
          </li>
          <li>
            <Mono>UndeclaredCalleeError</Mono> — used <Mono>{isTs ? "this.X" : "self.X"}</Mono>{" "}
            not listed in <Mono>calls:</Mono>/<Mono>reads:</Mono>.
          </li>
        </ul>
      </Section>
    </div>
  );
}

function Intro({ language }: { language: SourceLanguage }) {
  const isTs = language === "typescript";
  return (
    <p>
      A CDCS contract is five sections embedded in a{" "}
      {isTs ? "JSDoc block above a function" : "function docstring"}.{" "}
      <Mono>behavior</Mono> and <Mono>examples</Mono> are required;{" "}
      <Mono>constraints</Mono>, <Mono>calls</Mono> and <Mono>reads</Mono> are optional.
    </p>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {title}
      </h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return (
    <code className="rounded bg-indigo-50 px-1 py-0.5 font-mono text-[11px] text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
      {children}
    </code>
  );
}

function CodeBox({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-[11.5px] leading-snug text-slate-700 dark:border-white/10 dark:bg-slate-950/60 dark:text-slate-300">
      {children}
    </pre>
  );
}

const PY_WRAPPER = `def parse_port(value: str) -> int:
    """@generate
    behavior:
      ...
    examples:
      ...
    """`;

const TS_WRAPPER = `/**
 * @generate
 * behavior:
 *   ...
 * examples:
 *   ...
 */
export function parsePort(value: string): number { ... }`;

const PY_EXAMPLES = `parse_port("80") == 80          # equality
parse_port("0") raises ValueError  # error case`;

const TS_EXAMPLES = `parsePort("80") == 80              // equality
parsePort("0") raises ValueError   // error case`;

const CONSTRAINTS = `constraints:
  no_imports
  no_network
  no_filesystem`;

const PY_CALLS = `calls:
  self._sign(payload: str) -> str
  self._now() -> int

reads:
  self.secret_key: bytes`;

const TS_CALLS = `calls:
  self._sign(payload: string) -> string
  self._now() -> number

reads:
  self.secretKey: Uint8Array`;
