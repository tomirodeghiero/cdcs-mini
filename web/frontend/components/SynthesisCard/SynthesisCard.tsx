"use client";

import { useState } from "react";

import { CheckCircleIcon, FunctionIcon, HashIcon, WarningIcon, XIcon } from "@/components/icons";
import type { SynthesizedFunction, SynthesizePayload } from "@/lib/api";

import { ReadOnlyCode } from "./ReadOnlyCode";

type Props = { result: SynthesizePayload | null };

export function SynthesisCard({ result }: Props) {
  return (
    <section className="flex h-full min-h-[28rem] flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5 lg:min-h-0 dark:border-white/10 dark:bg-slate-900/60 dark:shadow-none">
      <Header result={result} />
      {result === null ? (
        <EmptyState />
      ) : result.errors.length > 0 ? (
        <SourceErrorsList errors={result.errors} />
      ) : result.functions.length === 0 ? (
        <NoFunctionsState />
      ) : (
        <FunctionsList functions={result.functions} language={result.language} />
      )}
    </section>
  );
}

function Header({ result }: { result: SynthesizePayload | null }) {
  const summary = computeSummary(result);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Synthesis results
        </h2>
        {summary !== null && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${summary.tone}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${summary.dot}`} />
            {summary.label}
          </span>
        )}
      </div>
      {result !== null && result.functions.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
          <LanguagePill language={result.language} />
          <span className="font-mono text-slate-600 dark:text-slate-300">
            {result.impl_filename}
          </span>
          <span className="text-slate-300 dark:text-slate-600">+</span>
          <span className="font-mono text-slate-600 dark:text-slate-300">
            {result.test_filename}
          </span>
        </div>
      )}
    </div>
  );
}

function LanguagePill({ language }: { language: "python" | "typescript" }) {
  const isTs = language === "typescript";
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        isTs
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
      }`}
    >
      {isTs ? "TS" : "PY"}
    </span>
  );
}

type Summary = { label: string; tone: string; dot: string };

function computeSummary(result: SynthesizePayload | null): Summary | null {
  if (result === null) return null;
  if (result.errors.length > 0) {
    return {
      label: `${result.errors.length} source error${result.errors.length > 1 ? "s" : ""}`,
      tone: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
      dot: "bg-rose-500",
    };
  }
  const ok = result.functions.filter((f) => f.status === "ok").length;
  const error = result.functions.filter((f) => f.status === "error").length;
  if (error === 0) {
    return {
      label: `${ok} synthesized`,
      tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
      dot: "bg-emerald-500",
    };
  }
  return {
    label: `${ok} ok · ${error} error${error > 1 ? "s" : ""}`,
    tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    dot: "bg-amber-500",
  };
}

function FunctionsList({
  functions,
  language,
}: {
  functions: SynthesizedFunction[];
  language: "python" | "typescript";
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
      {functions.map((fn) => (
        <FunctionPanel key={`${fn.name}-${fn.line}`} fn={fn} language={language} />
      ))}
    </div>
  );
}

function FunctionPanel({
  fn,
  language,
}: {
  fn: SynthesizedFunction;
  language: "python" | "typescript";
}) {
  const [tab, setTab] = useState<"impl" | "test">("impl");
  const ok = fn.status === "ok";
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50/70 px-3 py-2 dark:border-white/10 dark:bg-slate-900/40">
        <div className="flex items-center gap-2 text-sm">
          <span className={ok ? "text-emerald-500" : "text-rose-500"}>
            {ok ? <CheckCircleIcon className="h-4 w-4" /> : <XIcon className="h-4 w-4" />}
          </span>
          <FunctionIcon className="h-3.5 w-3.5 text-indigo-500" />
          <span className="font-mono font-medium text-slate-900 dark:text-slate-100">{fn.name}</span>
          <span className="text-xs text-slate-400 dark:text-slate-500">line {fn.line}</span>
        </div>
        <ProvenanceBadges fn={fn} />
      </div>

      {ok && fn.implementation && fn.test ? (
        <>
          <CodeTabs tab={tab} onChange={setTab} />
          <div className="border-t border-slate-100 dark:border-white/5">
            {tab === "impl" ? (
              <ReadOnlyCode value={fn.implementation} language={language} />
            ) : (
              <ReadOnlyCode value={fn.test} language={language} />
            )}
          </div>
        </>
      ) : (
        <FailureBody fn={fn} language={language} />
      )}
    </div>
  );
}

function CodeTabs({
  tab,
  onChange,
}: {
  tab: "impl" | "test";
  onChange: (next: "impl" | "test") => void;
}) {
  return (
    <div className="flex gap-1 border-b border-slate-200 bg-slate-50/40 px-3 pt-2 dark:border-white/10 dark:bg-slate-900/30">
      <CodeTab active={tab === "impl"} onClick={() => onChange("impl")}>
        impl
      </CodeTab>
      <CodeTab active={tab === "test"} onClick={() => onChange("test")}>
        tests
      </CodeTab>
    </div>
  );
}

function CodeTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`border-b-2 px-3 py-1.5 text-xs font-medium transition ${
        active
          ? "border-indigo-500 text-slate-900 dark:text-slate-50"
          : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

function ProvenanceBadges({ fn }: { fn: SynthesizedFunction }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
      {fn.model && (
        <Badge tone="indigo">
          <span className="font-mono">{fn.model}</span>
        </Badge>
      )}
      {fn.llm_calls !== null && fn.llm_calls !== undefined && (
        <Badge tone="slate">
          {fn.llm_calls} LLM call{fn.llm_calls === 1 ? "" : "s"}
        </Badge>
      )}
      {fn.repair_attempts !== null &&
        fn.repair_attempts !== undefined &&
        fn.repair_attempts > 0 && (
          <Badge tone="amber">
            {fn.repair_attempts} repair{fn.repair_attempts === 1 ? "" : "s"}
          </Badge>
        )}
      {fn.contract_hash && (
        <Badge tone="slate">
          <HashIcon className="h-3 w-3" />
          <span className="font-mono">{fn.contract_hash.slice(0, 10)}</span>
        </Badge>
      )}
    </div>
  );
}

type Tone = "indigo" | "amber" | "rose" | "slate" | "emerald";

function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const palette: Record<Tone, string> = {
    indigo: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300",
    amber: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    rose: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
    slate: "bg-slate-100 text-slate-600 dark:bg-white/5 dark:text-slate-300",
    emerald: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium ${palette[tone]}`}
    >
      {children}
    </span>
  );
}

function FailureBody({
  fn,
  language,
}: {
  fn: SynthesizedFunction;
  language: "python" | "typescript";
}) {
  return (
    <div className="space-y-2 p-3">
      {fn.failure && (
        <div className="rounded-lg border border-rose-200 bg-rose-50/60 p-3 text-xs dark:border-rose-500/20 dark:bg-rose-500/5">
          <div className="flex items-center gap-2 font-mono text-rose-800 dark:text-rose-200">
            <WarningIcon className="h-3.5 w-3.5" />
            <strong>{fn.failure.code}</strong>
          </div>
          <p className="mt-1 text-rose-700 dark:text-rose-300">{fn.failure.message}</p>
          {fn.failure.detail.length > 0 && (
            <ul className="mt-2 list-disc pl-4 font-mono text-[11px] text-rose-700 dark:text-rose-300">
              {fn.failure.detail.map((d, i) => (
                <li key={i}>{d}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {fn.failure?.partial_implementation && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/40 dark:border-amber-500/20 dark:bg-amber-500/[0.04]">
          <div className="px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-amber-800 dark:text-amber-300">
            Partial result — impl synthesized OK, test loop bailed
          </div>
          <ReadOnlyCode value={fn.failure.partial_implementation} language={language} />
        </div>
      )}
      {fn.upstream_diagnostics.length > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3 text-xs dark:border-amber-500/20 dark:bg-amber-500/5">
          <div className="mb-1 font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
            Upstream diagnostics
          </div>
          <ul className="space-y-1 font-mono text-amber-900 dark:text-amber-100">
            {fn.upstream_diagnostics.map((d, i) => (
              <li key={i}>
                <strong>{d.code}</strong>
                {d.line !== null && <> · line {d.line}</>}: {d.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {fn.status === "skipped" && !fn.failure && fn.upstream_diagnostics.length === 0 && (
        <p className="text-xs italic text-slate-500 dark:text-slate-400">
          Skipped — function has no @generate contract.
        </p>
      )}
    </div>
  );
}

function SourceErrorsList({ errors }: { errors: SynthesizePayload["errors"] }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-4 dark:border-rose-500/20 dark:bg-rose-500/5">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-800 dark:text-rose-300">
        Source errors
      </div>
      <ul className="space-y-1 font-mono text-xs text-rose-900 dark:text-rose-100">
        {errors.map((d, i) => (
          <li key={i}>
            <strong>{d.code}</strong>
            {d.line !== null && <> · line {d.line}</>}: {d.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="grid flex-1 place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center dark:border-white/10 dark:bg-white/[0.02]">
      <div className="space-y-2 text-sm text-slate-500 dark:text-slate-400">
        <div className="text-slate-700 dark:text-slate-200">No synthesis yet</div>
        <div className="text-xs">
          Paste a contract on the left, switch to <strong>Synthesize</strong>, then press Generate.
        </div>
        <div className="pt-1 text-[11px] text-slate-400">
          Backend resolves: <code className="font-mono">CDCS_LLM_PROVIDER</code> →{" "}
          Anthropic (if key) → Ollama (if running) → Pollinations (keyless fallback).
        </div>
      </div>
    </div>
  );
}

function NoFunctionsState() {
  return (
    <div className="grid flex-1 place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-8 text-center text-sm text-slate-500 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-400">
      No @generate functions found in the source.
    </div>
  );
}
