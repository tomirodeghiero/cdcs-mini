"use client";

import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";

import {
  BookIcon,
  CloudUploadIcon,
  CodeIcon,
  InfoIcon,
  SparkIcon,
  Spinner,
  UploadIcon,
} from "@/components/icons";
import { SyntaxHelp } from "@/components/SyntaxHelp";

import { CodeEditor } from "./CodeEditor";
import { PYTHON_SAMPLE, TS_SAMPLE } from "./samples";

type Mode = "upload" | "paste";
export type ActionMode = "analyze" | "synthesize";
export type SourceLanguage = "python" | "typescript";

type Props = {
  source: string;
  filename: string;
  language: SourceLanguage;
  loading: boolean;
  actionMode: ActionMode;
  onSourceChange: (value: string) => void;
  onFilenameChange: (value: string) => void;
  onFileLoaded: (file: File, contents: string) => void;
  onLanguageChange: (next: SourceLanguage) => void;
  onActionModeChange: (mode: ActionMode) => void;
  onSubmit: () => void;
};

// Swap the file extension (if any) when the user flips languages. Keeps
// the stem (``parse_port``) intact so people who renamed the file don't
// lose context.
export function swapFilenameExtension(filename: string, next: SourceLanguage): string {
  const stem = filename.replace(/\.(py|ts|tsx)$/i, "");
  const base = stem.length > 0 ? stem : "input";
  return next === "typescript" ? `${base}.ts` : `${base}.py`;
}

export function SourceCard(props: Props) {
  const { source, filename, language, loading, actionMode } = props;
  const [mode, setMode] = useState<Mode>("paste");
  const [helpOpen, setHelpOpen] = useState(false);
  const cmdKey = useCmdKey();

  const canSubmit = source.trim().length > 0;
  const isSynthesize = actionMode === "synthesize";
  const buttonLabel = loading
    ? isSynthesize
      ? "Synthesizing"
      : "Generating"
    : isSynthesize
      ? "Synthesize impl + tests"
      : "Generate report";

  return (
    <section className="flex h-full min-h-[28rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:min-h-0 dark:border-white/10 dark:bg-slate-900/60 dark:shadow-none">
      <Tabs mode={mode} onChange={setMode} />

      <div className="flex min-h-0 flex-1 flex-col gap-4 p-4 sm:p-5">
        <DropZone onFileLoaded={props.onFileLoaded} />

        <div className="flex min-h-[18rem] flex-1 flex-col sm:min-h-0">
          {/* Monaco stays mounted across tabs; we toggle visibility so the
              editor never re-initializes and never flashes "Loading…" */}
          <div className={mode === "paste" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
            <CodeArea
              value={source}
              onChange={props.onSourceChange}
              filename={filename}
              onFilenameChange={props.onFilenameChange}
              language={language}
              onLanguageChange={props.onLanguageChange}
              onLoadExample={() =>
                props.onSourceChange(language === "typescript" ? TS_SAMPLE : PYTHON_SAMPLE)
              }
              onOpenHelp={() => setHelpOpen(true)}
              onSubmit={props.onSubmit}
            />
          </div>
          {mode === "upload" && <UploadInstructions />}
        </div>

        <div className="flex flex-col-reverse items-stretch justify-between gap-3 border-t border-slate-200/60 pt-4 sm:flex-row sm:items-center dark:border-white/5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <ActionToggle
              value={actionMode}
              onChange={props.onActionModeChange}
              disabled={loading}
            />
            <p className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 self-center text-xs text-slate-500 sm:self-auto dark:text-slate-400">
              <span className="inline-flex items-center gap-2">
                <InfoIcon className="h-3.5 w-3.5 shrink-0" />
                {isSynthesize ? "LLM-backed synthesis" : "Deterministic analysis"}
              </span>
              {cmdKey && (
                <span className="inline-flex items-center gap-1">
                  <span className="text-slate-400 dark:text-slate-500">·</span>
                  <Kbd>{cmdKey}</Kbd>
                  <Kbd>↵</Kbd>
                  <span>to run</span>
                </span>
              )}
            </p>
          </div>
          <button
            type="button"
            disabled={!canSubmit || loading}
            onClick={props.onSubmit}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:from-slate-300 disabled:to-slate-300 disabled:text-white/80 dark:disabled:from-slate-700 dark:disabled:to-slate-700 dark:disabled:text-slate-400"
          >
            {loading ? <Spinner /> : <SparkIcon className="h-4 w-4" />}
            <span>{buttonLabel}</span>
          </button>
        </div>
      </div>
      <SyntaxHelp
        open={helpOpen}
        language={language}
        onClose={() => setHelpOpen(false)}
        onLoadSnippet={props.onSourceChange}
      />
    </section>
  );
}

function Tabs({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  return (
    <div className="flex items-center gap-1 border-b border-slate-200 px-2 pt-2 sm:px-3 sm:pt-3 dark:border-white/10">
      <Tab active={mode === "upload"} onClick={() => onChange("upload")} icon={<UploadIcon />}>
        <span className="sm:hidden">Upload</span>
        <span className="hidden sm:inline">Upload .py file</span>
      </Tab>
      <Tab active={mode === "paste"} onClick={() => onChange("paste")} icon={<CodeIcon />}>
        <span className="sm:hidden">Paste</span>
        <span className="hidden sm:inline">Paste source code</span>
      </Tab>
    </div>
  );
}

function Tab({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 border-b-2 px-4 py-3 text-sm transition ${
        active
          ? "border-indigo-500 font-medium text-slate-900 dark:text-slate-50"
          : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      }`}
    >
      <span className={active ? "text-indigo-500" : "text-slate-400 dark:text-slate-500"}>
        {icon}
      </span>
      {children}
    </button>
  );
}

function DropZone({ onFileLoaded }: { onFileLoaded: Props["onFileLoaded"] }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [hovered, setHovered] = useState(false);

  async function ingest(file: File) {
    onFileLoaded(file, await file.text());
  }

  function handlePick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void ingest(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setHovered(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void ingest(file);
  }

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragEnter={(e) => {
        e.preventDefault();
        setHovered(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={(e) => {
        e.preventDefault();
        setHovered(false);
      }}
      onDrop={handleDrop}
      className={`flex cursor-pointer items-center gap-3 rounded-xl border border-dashed px-4 py-4 transition sm:gap-4 sm:px-5 sm:py-5 ${
        hovered
          ? "border-indigo-400 bg-indigo-50/50 dark:border-indigo-400/60 dark:bg-indigo-500/10"
          : "border-slate-200 bg-slate-50/60 hover:border-indigo-300 hover:bg-indigo-50/40 dark:border-white/10 dark:bg-white/[0.02] dark:hover:border-indigo-400/40 dark:hover:bg-indigo-500/5"
      }`}
    >
      <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow shadow-indigo-200 dark:shadow-indigo-500/30">
        <CloudUploadIcon />
      </span>
      <div className="min-w-0 text-sm leading-relaxed">
        <div className="text-slate-700 dark:text-slate-200">
          <span className="font-medium text-slate-900 dark:text-slate-50">
            <span className="sm:hidden">Tap to upload a .py / .ts file</span>
            <span className="hidden sm:inline">Drag and drop a .py or .ts file here</span>
          </span>
          <span className="hidden sm:inline">
            , or{" "}
            <span className="text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-300">
              click to browse
            </span>
          </span>
        </div>
        <div className="text-xs text-slate-500 dark:text-slate-400">
          Python (.py) and TypeScript (.ts / .tsx) sources are supported.
        </div>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".py,.ts,.tsx,text/x-python,application/typescript"
        className="hidden"
        onChange={handlePick}
      />
    </div>
  );
}

function CodeArea({
  value,
  onChange,
  filename,
  onFilenameChange,
  language,
  onLanguageChange,
  onLoadExample,
  onOpenHelp,
  onSubmit,
}: {
  value: string;
  onChange: (next: string) => void;
  filename: string;
  onFilenameChange: (next: string) => void;
  language: SourceLanguage;
  onLanguageChange: (next: SourceLanguage) => void;
  onLoadExample: () => void;
  onOpenHelp: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/60 dark:shadow-none">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50/80 px-3 py-2 dark:border-white/10 dark:bg-slate-900/60">
        <div className="flex min-w-0 flex-1 items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span
            className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"
            aria-hidden
          />
          <input
            value={filename}
            onChange={(e) => onFilenameChange(e.target.value)}
            spellCheck={false}
            className="w-full min-w-0 max-w-[14rem] bg-transparent font-mono text-xs text-slate-700 focus:outline-none dark:text-slate-200"
          />
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <LanguageToggle value={language} onChange={onLanguageChange} />
          <button
            type="button"
            onClick={onOpenHelp}
            title="Syntax reference & loadable examples"
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-600 dark:border-white/10 dark:bg-slate-900/60 dark:text-slate-300 dark:hover:border-indigo-400/40 dark:hover:text-indigo-300"
          >
            <BookIcon className="h-3.5 w-3.5" />
            <span>Syntax</span>
          </button>
          <button
            type="button"
            onClick={onLoadExample}
            className="text-xs text-slate-500 underline-offset-2 transition hover:text-indigo-600 hover:underline dark:text-slate-400 dark:hover:text-indigo-300"
          >
            load example
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <CodeEditor
          value={value}
          onChange={onChange}
          height="100%"
          onSubmit={onSubmit}
          language={language}
        />
      </div>
    </div>
  );
}

function LanguageToggle({
  value,
  onChange,
}: {
  value: SourceLanguage;
  onChange: (next: SourceLanguage) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Source language"
      title="Toggle the source language (filename + editor follow)"
      className="inline-flex rounded-md border border-slate-200 bg-white p-0.5 text-[10px] font-semibold uppercase tracking-wide dark:border-white/10 dark:bg-slate-900/60"
    >
      <LanguageTab
        active={value === "python"}
        accent="amber"
        onClick={() => onChange("python")}
      >
        PY
      </LanguageTab>
      <LanguageTab
        active={value === "typescript"}
        accent="blue"
        onClick={() => onChange("typescript")}
      >
        TS
      </LanguageTab>
    </div>
  );
}

function LanguageTab({
  active,
  accent,
  onClick,
  children,
}: {
  active: boolean;
  accent: "amber" | "blue";
  onClick: () => void;
  children: React.ReactNode;
}) {
  const activeClass =
    accent === "amber"
      ? "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300"
      : "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300";
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`rounded-[5px] px-1.5 py-0.5 transition ${
        active
          ? activeClass
          : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

function UploadInstructions() {
  return (
    <div className="h-full rounded-xl border border-slate-200 bg-slate-50/40 p-6 text-sm text-slate-500 dark:border-white/10 dark:bg-white/[0.02] dark:text-slate-400">
      <p className="text-slate-600 dark:text-slate-300">
        Drop a Python file in the area above. The contents are sent to the{" "}
        <span className="font-mono text-slate-800 dark:text-slate-100">cdcs-mini</span> backend;
        nothing is stored.
      </p>
      <ul className="mt-3 space-y-1.5 text-xs">
        <li>• File size limit: 1 MB</li>
        <li>• UTF-8 encoded source</li>
        <li>• Switch to “Paste source code” to edit inline</li>
      </ul>
    </div>
  );
}

function ActionToggle({
  value,
  onChange,
  disabled,
}: {
  value: ActionMode;
  onChange: (next: ActionMode) => void;
  disabled: boolean;
}) {
  return (
    <div
      role="tablist"
      aria-label="Choose action"
      className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs font-medium dark:border-white/10 dark:bg-white/5"
    >
      <ActionTab
        active={value === "analyze"}
        onClick={() => onChange("analyze")}
        disabled={disabled}
      >
        Analyze
      </ActionTab>
      <ActionTab
        active={value === "synthesize"}
        onClick={() => onChange("synthesize")}
        disabled={disabled}
      >
        Synthesize
      </ActionTab>
    </div>
  );
}

function ActionTab({
  active,
  onClick,
  disabled,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-3 py-1.5 transition disabled:cursor-not-allowed disabled:opacity-60 ${
        active
          ? "bg-white text-slate-900 shadow-sm dark:bg-slate-900 dark:text-slate-50"
          : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
      }`}
    >
      {children}
    </button>
  );
}

// Tiny keyboard chip — looks like an actual key cap
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-md border border-slate-200 bg-slate-50 px-1.5 font-mono text-[10px] font-medium text-slate-600 shadow-[0_1px_0_rgb(0_0_0_/_0.04)] dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:shadow-none">
      {children}
    </kbd>
  );
}

// Returns "⌘" on macOS/iOS, "Ctrl" elsewhere — null until we've actually checked,
// so the hint mounts with the correct symbol instead of flashing Ctrl → ⌘
function useCmdKey(): string | null {
  const [key, setKey] = useState<string | null>(null);
  useEffect(() => {
    const isMac = /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent);
    setKey(isMac ? "⌘" : "Ctrl");
  }, []);
  return key;
}
