"use client";

import Image from "next/image";
import { useState } from "react";

import { Navbar } from "@/components/Navbar";
import { ResultsCard } from "@/components/ResultsCard";
import {
  PYTHON_SAMPLE,
  SourceCard,
  TS_SAMPLE,
  swapFilenameExtension,
  type ActionMode,
  type SourceLanguage,
} from "@/components/SourceCard";
import { SynthesisCard } from "@/components/SynthesisCard";
import {
  ApiError,
  generateFromSource,
  synthesizeFromSource,
  type ReportPayload,
  type SynthesizePayload,
} from "@/lib/api";

const DEFAULT_FILENAME = "input.py";

function detectLanguage(filename: string): SourceLanguage {
  const lower = filename.toLowerCase();
  if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "typescript";
  return "python";
}

export default function HomePage() {
  const [source, setSource] = useState("");
  const [filename, setFilename] = useState(DEFAULT_FILENAME);
  const [language, setLanguage] = useState<SourceLanguage>("python");
  const [actionMode, setActionMode] = useState<ActionMode>("analyze");
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [synthesis, setSynthesis] = useState<SynthesizePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function handleFileLoaded(file: File, contents: string) {
    setSource(contents);
    setFilename(file.name);
    setLanguage(detectLanguage(file.name));
  }

  function handleLanguageChange(next: SourceLanguage) {
    if (next === language) return;
    setLanguage(next);
    setFilename((current) => swapFilenameExtension(current, next));
    // If the editor still holds the *other* language's stock sample, swap
    // it for this language's sample so the example stays useful after the
    // toggle. Anything the user actually typed stays put.
    setSource((current) => {
      const trimmed = current.trim();
      if (trimmed.length === 0) return current;
      if (current === PYTHON_SAMPLE || current === TS_SAMPLE) {
        return next === "typescript" ? TS_SAMPLE : PYTHON_SAMPLE;
      }
      return current;
    });
  }

  async function handleSubmit() {
    setLoading(true);
    setError(null);
    const name = filename || DEFAULT_FILENAME;
    try {
      if (actionMode === "analyze") {
        const next = await generateFromSource(source, name);
        setReport(next);
      } else {
        const next = await synthesizeFromSource(source, name);
        setSynthesis(next);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
      if (actionMode === "analyze") setReport(null);
      else setSynthesis(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    // Mobile/tablet: natural-height stacked layout that scrolls the page
    // lg+: lock to viewport so the editor and JSON panes scroll inside their cards
    <div className="flex min-h-screen flex-col lg:h-screen">
      <Navbar />
      <main className="flex-1 lg:overflow-hidden">
        <div className="mx-auto flex h-full max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 sm:py-5">
          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-200">
              {error}
            </div>
          )}
          {/* min-h-0 lets the grid shrink so the cards' internal flex layouts get a finite height */}
          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
            <SourceCard
              source={source}
              filename={filename}
              language={language}
              loading={loading}
              actionMode={actionMode}
              onSourceChange={setSource}
              onFilenameChange={(value) => {
                setFilename(value);
                setLanguage(detectLanguage(value));
              }}
              onFileLoaded={handleFileLoaded}
              onLanguageChange={handleLanguageChange}
              onActionModeChange={setActionMode}
              onSubmit={handleSubmit}
            />
            {actionMode === "analyze" ? (
              <ResultsCard report={report} />
            ) : (
              <SynthesisCard result={synthesis} />
            )}
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function Footer() {
  return (
    <footer className="shrink-0 border-t border-slate-200 bg-white/70 backdrop-blur dark:border-white/5 dark:bg-slate-950/70">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:px-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="leading-tight">
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            CDCS
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400">
            Deterministic JSON reports from{" "}
            <code className="rounded bg-indigo-50 px-1 py-0.5 font-mono text-[10px] text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
              @generate
            </code>{" "}
            contracts
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Image
            src="/unrc_logo.png"
            alt="Universidad Nacional de Río Cuarto"
            width={24}
            height={32}
            className="h-9 w-auto shrink-0"
          />
          <div className="min-w-0 leading-tight">
            <div className="truncate text-xs font-medium text-slate-700 dark:text-slate-200">
              Universidad Nacional de Río Cuarto
            </div>
            <div className="truncate text-[11px] text-slate-400 dark:text-slate-500">
              Tomás Rodeghiero · challenge by Daniel Gutson
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
