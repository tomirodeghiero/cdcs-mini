"use client";

import { useState } from "react";

import { CopyIcon } from "@/components/icons";
import { highlightJson } from "@/lib/highlightJson";

export function JsonViewer({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const lines = text.split("\n");

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-950 dark:border-white/10">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900 px-3 py-2">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <WindowDots />
          <span className="ml-2 font-mono">report.json</span>
        </div>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-slate-600 hover:bg-slate-700"
        >
          <CopyIcon />
          {copied ? "Copied" : "Copy JSON"}
        </button>
      </div>
      <div className="scrollbar-soft min-h-0 flex-1 overflow-auto">
        <pre className="grid grid-cols-[3.5rem_1fr] font-mono text-xs leading-6">
          <code className="select-none border-r border-slate-800 bg-slate-900/60 py-3 text-right text-slate-500">
            {lines.map((_, idx) => (
              <div key={idx} className="px-2">
                {idx + 1}
              </div>
            ))}
          </code>
          <code className="py-3 pl-4 pr-4 text-slate-200">
            {lines.map((line, idx) => (
              <div key={idx}>{highlightJson(line)}</div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}

function WindowDots() {
  return (
    <>
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-rose-400" />
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-amber-400" />
      <span className="inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
    </>
  );
}
