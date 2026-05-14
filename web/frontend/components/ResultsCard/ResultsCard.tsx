"use client";

import { useEffect, useState } from "react";

import { FunctionIcon, HashIcon, ShieldIcon, WarningIcon } from "@/components/icons";
import { JsonViewer } from "@/components/JsonViewer";
import type { ReportPayload } from "@/lib/api";
import { sha256Hex } from "@/lib/hash";

type Props = { report: ReportPayload | null };

type Tone = "indigo" | "amber" | "emerald";

const REPORT_ID_LENGTH = 32;

export function ResultsCard({ report }: Props) {
  const json = report ? JSON.stringify(report, null, 2) : "";
  const stats = computeStats(report);
  const reportId = useReportId(json);

  return (
    <section className="flex h-full min-h-0 flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-900/60 dark:shadow-none">
      <Header
        status={report ? (stats.diagnostics === 0 ? "clean" : "issues") : "idle"}
        diagnostics={stats.diagnostics}
      />

      <div className="grid shrink-0 grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricCard
          tone="indigo"
          label="Functions"
          value={stats.functions}
          caption="@generate contracts"
          icon={<FunctionIcon />}
        />
        <MetricCard
          tone="amber"
          label="Diagnostics"
          value={stats.diagnostics}
          caption={stats.diagnostics === 0 ? "No issues found" : "Issues detected"}
          icon={<WarningIcon />}
        />
        <MetricCard
          tone="emerald"
          label="Constraints"
          value={stats.constraints}
          caption="Declared per contract"
          icon={<ShieldIcon />}
        />
      </div>

      <DiagnosticsList report={report} />

      <div className="flex min-h-0 flex-1 flex-col">
        <h3 className="mb-2 shrink-0 text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          JSON report
        </h3>
        <div className="min-h-0 flex-1">
          {report ? <JsonViewer text={json} /> : <EmptyJson />}
        </div>
      </div>

      <footer className="flex shrink-0 items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        <HashIcon />
        <span>Deterministic report ID:</span>
        <code className="font-mono text-slate-700 dark:text-slate-200">{reportId}</code>
      </footer>
    </section>
  );
}

type Stats = { functions: number; diagnostics: number; constraints: number };

function computeStats(report: ReportPayload | null): Stats {
  if (!report) return { functions: 0, diagnostics: 0, constraints: 0 };
  const diagnostics =
    report.errors.length +
    report.functions.reduce((acc, fn) => acc + (fn.diagnostics?.length ?? 0), 0);
  const constraints = report.functions.reduce((acc, fn) => acc + fn.constraints.length, 0);
  return { functions: report.functions.length, diagnostics, constraints };
}

// SHA-256 the JSON every time it changes. Keeps the id in sync with what
// the user sees and lets two identical reports collide on purpose
function useReportId(json: string): string {
  const [id, setId] = useState("—");
  useEffect(() => {
    if (!json) {
      setId("—");
      return;
    }
    let active = true;
    sha256Hex(json).then((hex) => {
      if (active) setId(hex.slice(0, REPORT_ID_LENGTH));
    });
    return () => {
      active = false;
    };
  }, [json]);
  return id;
}

function Header({
  status,
  diagnostics,
}: {
  status: "idle" | "clean" | "issues";
  diagnostics: number;
}) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
        Report summary
      </h2>
      {status !== "idle" && (
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
            status === "clean"
              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
              : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              status === "clean" ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
          {status === "clean"
            ? "All clear"
            : `${diagnostics} diagnostic${diagnostics > 1 ? "s" : ""}`}
        </span>
      )}
    </div>
  );
}

function MetricCard({
  tone,
  label,
  value,
  caption,
  icon,
}: {
  tone: Tone;
  label: string;
  value: number;
  caption: string;
  icon: React.ReactNode;
}) {
  const palette: Record<Tone, string> = {
    indigo: "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300",
    amber: "bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-300",
    emerald: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-300",
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex items-center gap-3">
        <span className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${palette[tone]}`}>
          {icon}
        </span>
        <div className="flex flex-col gap-1">
          <div className="text-xs font-medium uppercase leading-none tracking-wide text-slate-500 dark:text-slate-400">
            {label}
          </div>
          <div className="text-2xl font-semibold leading-none tabular-nums text-slate-900 dark:text-slate-50">
            {value}
          </div>
        </div>
      </div>
      <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">{caption}</div>
    </div>
  );
}

function DiagnosticsList({ report }: { report: ReportPayload | null }) {
  if (!report) return null;
  const fileErrors = report.errors;
  const fnDiagnostics = report.functions.flatMap((fn) =>
    (fn.diagnostics ?? []).map((d) => ({ ...d, fn: fn.name })),
  );
  if (fileErrors.length === 0 && fnDiagnostics.length === 0) return null;

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-500/20 dark:bg-amber-500/5">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
        Diagnostics
      </div>
      <ul className="space-y-1 font-mono text-xs text-amber-900 dark:text-amber-100">
        {fileErrors.map((d, i) => (
          <li key={`fe-${i}`}>
            <strong>{d.code}</strong>
            {d.line !== null && <> · line {d.line}</>}: {d.message}
          </li>
        ))}
        {fnDiagnostics.map((d, i) => (
          <li key={`fd-${i}`}>
            <strong>{d.code}</strong>
            {d.line !== null && <> · line {d.line}</>}: {d.message}{" "}
            <span className="text-amber-700 dark:text-amber-300/70">in {d.fn}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyJson() {
  return (
    <div className="grid h-full place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50/50 px-6 py-10 text-center dark:border-white/10 dark:bg-white/[0.02]">
      <div className="space-y-1 text-sm text-slate-500 dark:text-slate-400">
        <div className="text-slate-700 dark:text-slate-200">No report yet</div>
        <div className="text-xs">Paste code or upload a file, then press Generate report.</div>
      </div>
    </div>
  );
}
