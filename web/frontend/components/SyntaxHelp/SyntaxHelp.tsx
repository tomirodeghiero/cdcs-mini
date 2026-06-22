"use client";

import { useEffect, useState } from "react";

import { XIcon } from "@/components/icons";
import type { SourceLanguage } from "@/components/SourceCard";

import { Cheatsheet } from "./Cheatsheet";
import { snippetsFor, type Snippet } from "./snippets";

type Tab = "syntax" | "examples";

type Props = {
  open: boolean;
  language: SourceLanguage;
  onClose: () => void;
  onLoadSnippet: (code: string) => void;
};

export function SyntaxHelp({ open, language, onClose, onLoadSnippet }: Props) {
  const [tab, setTab] = useState<Tab>("syntax");

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="syntax-help-title"
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 backdrop-blur-sm sm:items-center"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-2xl border border-slate-200 bg-white shadow-xl sm:h-[80vh] sm:rounded-2xl dark:border-white/10 dark:bg-slate-900"
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-5 py-3 dark:border-white/10">
          <div className="min-w-0">
            <h2
              id="syntax-help-title"
              className="text-sm font-semibold text-slate-900 dark:text-slate-50"
            >
              Syntax &amp; examples
            </h2>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              How to write a CDCS <code className="font-mono">@generate</code> contract — for{" "}
              {language === "typescript" ? "TypeScript" : "Python"}.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-200"
          >
            <XIcon />
          </button>
        </header>

        <nav className="flex shrink-0 items-center gap-1 border-b border-slate-200 px-3 dark:border-white/10">
          <TabButton active={tab === "syntax"} onClick={() => setTab("syntax")}>
            Syntax
          </TabButton>
          <TabButton active={tab === "examples"} onClick={() => setTab("examples")}>
            Examples
          </TabButton>
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {tab === "syntax" ? (
            <Cheatsheet language={language} />
          ) : (
            <ExampleList
              language={language}
              onPick={(code) => {
                onLoadSnippet(code);
                onClose();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function TabButton({
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
      className={`border-b-2 px-4 py-2.5 text-xs font-medium transition ${
        active
          ? "border-indigo-500 text-slate-900 dark:text-slate-50"
          : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

function ExampleList({
  language,
  onPick,
}: {
  language: SourceLanguage;
  onPick: (code: string) => void;
}) {
  const snippets = snippetsFor(language);
  return (
    <ul className="space-y-2">
      {snippets.map((s) => (
        <li key={s.id}>
          <ExampleRow snippet={s} onPick={() => onPick(s.code)} />
        </li>
      ))}
    </ul>
  );
}

function ExampleRow({ snippet, onPick }: { snippet: Snippet; onPick: () => void }) {
  return (
    <button
      type="button"
      onClick={onPick}
      className="group flex w-full items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-left transition hover:border-indigo-300 hover:bg-indigo-50/40 dark:border-white/10 dark:bg-slate-950/40 dark:hover:border-indigo-400/40 dark:hover:bg-indigo-500/10"
    >
      <div className="min-w-0">
        <div className="truncate font-mono text-sm text-slate-900 dark:text-slate-50">
          {snippet.title}
        </div>
        <div className="truncate text-xs text-slate-500 dark:text-slate-400">{snippet.blurb}</div>
      </div>
      <span className="shrink-0 text-[11px] font-medium text-indigo-600 opacity-0 transition group-hover:opacity-100 dark:text-indigo-300">
        Load →
      </span>
    </button>
  );
}
