"use client";

import Image from "next/image";
import { useState } from "react";

import { Navbar } from "@/components/Navbar";
import { ResultsCard } from "@/components/ResultsCard";
import { SourceCard } from "@/components/SourceCard";
import { ApiError, generateFromSource, type ReportPayload } from "@/lib/api";

const DEFAULT_FILENAME = "input.py";

export default function HomePage() {
  const [source, setSource] = useState("");
  const [filename, setFilename] = useState(DEFAULT_FILENAME);
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function handleFileLoaded(file: File, contents: string) {
    setSource(contents);
    setFilename(file.name);
  }

  async function handleSubmit() {
    setLoading(true);
    setError(null);
    try {
      const next = await generateFromSource(source, filename || DEFAULT_FILENAME);
      setReport(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
      setReport(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    // h-screen + flex-col: Navbar / main / Footer stack to the viewport
    <div className="flex h-screen flex-col">
      <Navbar />
      <main className="flex-1 overflow-hidden">
        <div className="mx-auto flex h-full max-w-7xl flex-col gap-4 px-6 py-5">
          {error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-200">
              {error}
            </div>
          )}
          {/* min-h-0 lets the grid shrink so the cards' internal flex layouts get a finite height */}
          <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 lg:grid-cols-2">
            <SourceCard
              source={source}
              filename={filename}
              loading={loading}
              onSourceChange={setSource}
              onFilenameChange={setFilename}
              onFileLoaded={handleFileLoaded}
              onSubmit={handleSubmit}
            />
            <ResultsCard report={report} />
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
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="leading-tight">
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            CDCS Mini
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
            className="h-9 w-auto"
          />
          <div className="leading-tight">
            <div className="text-xs font-medium text-slate-700 dark:text-slate-200">
              Universidad Nacional de Río Cuarto
            </div>
            <div className="text-[11px] text-slate-400 dark:text-slate-500">
              Tomás Rodeghiero · challenge by Daniel Gutson
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
