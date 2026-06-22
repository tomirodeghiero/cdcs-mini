"use client";

import dynamic from "next/dynamic";

import { useTheme } from "@/lib/theme";

const Editor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => <div className="h-64 w-full animate-pulse bg-slate-100 dark:bg-slate-900/40" />,
});

type Props = {
  value: string;
  language?: string;
};

const DARK_THEME = "cdcs-night";
const LIGHT_THEME = "cdcs-day";

export function ReadOnlyCode({ value, language = "python" }: Props) {
  const [theme] = useTheme();
  // Monaco needs a definite height; pick a comfortable max with internal scroll.
  const lineCount = Math.min(28, Math.max(8, value.split("\n").length));
  const height = `${lineCount * 20 + 32}px`;

  return (
    <div style={{ height }}>
      <Editor
        height={height}
        value={value}
        language={language}
        theme={theme === "dark" ? DARK_THEME : LIGHT_THEME}
        options={{
          readOnly: true,
          domReadOnly: true,
          minimap: { enabled: false },
          fontSize: 12.5,
          fontFamily:
            'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Monaco, "Cascadia Code", monospace',
          fontLigatures: true,
          lineNumbers: "on",
          lineNumbersMinChars: 3,
          renderLineHighlight: "none",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          wordWrap: "off",
          padding: { top: 10, bottom: 10 },
          smoothScrolling: true,
          quickSuggestions: false,
          suggestOnTriggerCharacters: false,
          parameterHints: { enabled: false },
          hover: { enabled: false },
          links: false,
          contextmenu: false,
          overviewRulerLanes: 0,
          overviewRulerBorder: false,
          stickyScroll: { enabled: false },
          scrollbar: {
            verticalScrollbarSize: 8,
            horizontalScrollbarSize: 8,
            useShadows: false,
          },
        }}
      />
    </div>
  );
}
