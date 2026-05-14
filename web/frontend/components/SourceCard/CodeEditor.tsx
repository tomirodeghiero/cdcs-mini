"use client";

import type { Monaco } from "@monaco-editor/react";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import { useTheme } from "@/lib/theme";

// Monaco touches window/document, so render it on the client only.
// Dynamic import keeps the initial SSR bundle slim and avoids hydration mismatches.
const Editor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <EditorSkeleton />,
});

type Props = {
  value: string;
  onChange: (value: string) => void;
  language?: string;
  height?: string;
  onSubmit?: () => void;
};

const DARK_THEME = "cdcs-night";
const LIGHT_THEME = "cdcs-day";

export function CodeEditor({
  value,
  onChange,
  language = "python",
  height = "20rem",
  onSubmit,
}: Props) {
  const [theme] = useTheme();
  const monacoRef = useRef<Monaco | null>(null);
  // Latest onSubmit lives in a ref so the Monaco action keeps calling the
  // current handler even when props change (state-dependent guards, etc.)
  const onSubmitRef = useRef(onSubmit);
  useEffect(() => {
    onSubmitRef.current = onSubmit;
  }, [onSubmit]);

  // Push the theme imperatively the moment it changes — no waiting for React's
  // next paint or Monaco's prop reconciliation. Makes the toggle feel instant.
  useEffect(() => {
    monacoRef.current?.editor.setTheme(theme === "dark" ? DARK_THEME : LIGHT_THEME);
  }, [theme]);

  return (
    <div style={{ height }}>
      <Editor
        height={height}
        value={value}
        onChange={(next) => onChange(next ?? "")}
        language={language}
        theme={theme === "dark" ? DARK_THEME : LIGHT_THEME}
        // Suppress Monaco's default "Loading…" overlay; show nothing instead
        loading={<EditorSkeleton />}
        beforeMount={(monaco) => {
          monacoRef.current = monaco;
          registerThemes(monaco);
        }}
        onMount={(editor, monaco) => {
          // Cmd/Ctrl + Enter inside the editor = same as clicking Generate
          editor.addAction({
            id: "cdcs-mini.generate",
            label: "Generate report",
            keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter],
            run: () => {
              onSubmitRef.current?.();
            },
          });
        }}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily:
            'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Monaco, "Cascadia Code", monospace',
          fontLigatures: true,
          lineNumbers: "on",
          lineNumbersMinChars: 3,
          renderLineHighlight: "line",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 4,
          insertSpaces: true,
          wordWrap: "off",
          padding: { top: 14, bottom: 14 },
          smoothScrolling: true,
          cursorBlinking: "smooth",
          cursorSmoothCaretAnimation: "on",
          bracketPairColorization: { enabled: true },
          guides: { indentation: true, bracketPairs: true },
          scrollbar: {
            verticalScrollbarSize: 10,
            horizontalScrollbarSize: 10,
            useShadows: false,
          },
          // Disable IDE-ish features — this is an input box, not a project editor
          quickSuggestions: false,
          suggestOnTriggerCharacters: false,
          parameterHints: { enabled: false },
          hover: { enabled: false },
          links: false,
          contextmenu: false,
          overviewRulerLanes: 0,
          overviewRulerBorder: false,
          renderWhitespace: "none",
          stickyScroll: { enabled: false },
        }}
      />
    </div>
  );
}

// Cache so we only register the themes once per Monaco instance
const REGISTERED = new WeakSet<Monaco>();

function registerThemes(monaco: Monaco): void {
  if (REGISTERED.has(monaco)) return;
  REGISTERED.add(monaco);

  // Tokyo Night Storm — purple keywords, blue functions, green strings
  monaco.editor.defineTheme(DARK_THEME, {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "", foreground: "c0caf5" },
      { token: "comment", foreground: "565f89", fontStyle: "italic" },
      { token: "keyword", foreground: "bb9af7" },
      { token: "keyword.flow", foreground: "bb9af7" },
      { token: "keyword.json", foreground: "bb9af7" },
      { token: "operator", foreground: "89ddff" },
      { token: "delimiter", foreground: "a9b1d6" },
      { token: "delimiter.parenthesis", foreground: "a9b1d6" },
      { token: "delimiter.bracket", foreground: "a9b1d6" },
      { token: "delimiter.square", foreground: "a9b1d6" },
      { token: "number", foreground: "ff9e64" },
      { token: "number.hex", foreground: "ff9e64" },
      { token: "string", foreground: "9ece6a" },
      { token: "string.escape", foreground: "2ac3de" },
      { token: "string.quote", foreground: "9ece6a" },
      { token: "string.invalid", foreground: "f7768e" },
      { token: "regexp", foreground: "b4f9f8" },
      { token: "type", foreground: "2ac3de" },
      { token: "type.identifier", foreground: "2ac3de" },
      { token: "identifier", foreground: "c0caf5" },
      { token: "tag", foreground: "f7768e" },
      { token: "attribute.name", foreground: "7aa2f7" },
      { token: "attribute.value", foreground: "9ece6a" },
      { token: "variable", foreground: "c0caf5" },
      { token: "variable.parameter", foreground: "e0af68" },
      { token: "variable.predefined", foreground: "f7768e" },
      { token: "constant", foreground: "ff9e64" },
      { token: "constant.language", foreground: "ff9e64" },
    ],
    colors: {
      "editor.background": "#1a1b26",
      "editor.foreground": "#c0caf5",
      "editorLineNumber.foreground": "#3b4261",
      "editorLineNumber.activeForeground": "#7aa2f7",
      "editor.lineHighlightBackground": "#1f2335",
      "editor.lineHighlightBorder": "#1f2335",
      "editor.selectionBackground": "#33467c",
      "editor.inactiveSelectionBackground": "#2a3160",
      "editor.selectionHighlightBackground": "#28344a",
      "editor.findMatchBackground": "#3d59a1",
      "editor.findMatchHighlightBackground": "#3d59a166",
      "editorCursor.foreground": "#c0caf5",
      "editorIndentGuide.background": "#272a3f",
      "editorIndentGuide.activeBackground": "#3b4261",
      "editorBracketMatch.background": "#1a1b2600",
      "editorBracketMatch.border": "#545c7e",
      "editorBracketHighlight.foreground1": "#7aa2f7",
      "editorBracketHighlight.foreground2": "#bb9af7",
      "editorBracketHighlight.foreground3": "#2ac3de",
      "editorBracketHighlight.foreground4": "#9ece6a",
      "editorBracketHighlight.foreground5": "#e0af68",
      "editorBracketHighlight.foreground6": "#f7768e",
      "editorWhitespace.foreground": "#3b4261",
      "scrollbarSlider.background": "#3b426180",
      "scrollbarSlider.hoverBackground": "#414868",
      "scrollbarSlider.activeBackground": "#565f89",
      "editorWidget.background": "#1f2335",
      "editorWidget.border": "#2a2e44",
      "editorGutter.background": "#1a1b26",
    },
  });

  // Light variant — same role-coding, but rebalanced for a white surface
  monaco.editor.defineTheme(LIGHT_THEME, {
    base: "vs",
    inherit: true,
    rules: [
      { token: "", foreground: "343b59" },
      { token: "comment", foreground: "9699a3", fontStyle: "italic" },
      { token: "keyword", foreground: "5a3e8e" },
      { token: "keyword.flow", foreground: "5a3e8e" },
      { token: "operator", foreground: "006c86" },
      { token: "number", foreground: "965027" },
      { token: "string", foreground: "485e30" },
      { token: "string.escape", foreground: "166775" },
      { token: "type", foreground: "166775" },
      { token: "variable.parameter", foreground: "8f5e15" },
      { token: "variable.predefined", foreground: "b15c00" },
      { token: "constant", foreground: "965027" },
      { token: "constant.language", foreground: "965027" },
    ],
    colors: {
      "editor.background": "#ffffff",
      "editor.foreground": "#343b59",
      "editorLineNumber.foreground": "#cbd5e1",
      "editorLineNumber.activeForeground": "#6366f1",
      "editor.lineHighlightBackground": "#f1f5ff",
      "editor.lineHighlightBorder": "#f1f5ff",
      "editor.selectionBackground": "#c7d2fe",
      "editor.inactiveSelectionBackground": "#e0e7ff",
      "editorCursor.foreground": "#343b59",
      "editorIndentGuide.background": "#eef0f6",
      "editorIndentGuide.activeBackground": "#c7d2fe",
      "editorBracketHighlight.foreground1": "#5a3e8e",
      "editorBracketHighlight.foreground2": "#006c86",
      "editorBracketHighlight.foreground3": "#965027",
      "scrollbarSlider.background": "#cbd5e180",
      "scrollbarSlider.hoverBackground": "#94a3b8",
      "scrollbarSlider.activeBackground": "#64748b",
    },
  });
}

function EditorSkeleton() {
  return <div className="h-full w-full animate-pulse bg-slate-100 dark:bg-slate-900/40" />;
}
