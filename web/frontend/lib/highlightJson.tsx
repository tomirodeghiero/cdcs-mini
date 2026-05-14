import { Fragment, type ReactNode } from "react";

// Tiny JSON syntax highlighter, no deps. Walks the pretty-printed string
// and emits a <span> per token. Keys are spotted by peeking ahead for ":"
export function highlightJson(json: string): ReactNode {
  const tokens: { text: string; cls: string }[] = [];
  let i = 0;
  const len = json.length;

  while (i < len) {
    const ch = json[i];

    if (ch === '"') {
      let j = i + 1;
      while (j < len) {
        if (json[j] === "\\") {
          j += 2;
          continue;
        }
        if (json[j] === '"') break;
        j += 1;
      }
      const end = Math.min(j + 1, len);
      const lexeme = json.slice(i, end);
      let k = end;
      while (k < len && /\s/.test(json[k])) k += 1;
      const isKey = json[k] === ":";
      tokens.push({ text: lexeme, cls: isKey ? "text-indigo-300" : "text-emerald-300" });
      i = end;
      continue;
    }

    if (/[-0-9]/.test(ch)) {
      let j = i + 1;
      while (j < len && /[0-9eE+\-.]/.test(json[j])) j += 1;
      tokens.push({ text: json.slice(i, j), cls: "text-amber-300" });
      i = j;
      continue;
    }

    if (json.startsWith("true", i) || json.startsWith("false", i)) {
      const word = json.startsWith("true", i) ? "true" : "false";
      tokens.push({ text: word, cls: "text-sky-300 font-medium" });
      i += word.length;
      continue;
    }

    if (json.startsWith("null", i)) {
      tokens.push({ text: "null", cls: "text-slate-400 italic" });
      i += 4;
      continue;
    }

    if (/[{}[\],:]/.test(ch)) {
      tokens.push({ text: ch, cls: "text-slate-500" });
      i += 1;
      continue;
    }

    tokens.push({ text: ch, cls: "text-slate-300" });
    i += 1;
  }

  return tokens.map((t, idx) => (
    <Fragment key={idx}>
      <span className={t.cls}>{t.text}</span>
    </Fragment>
  ));
}
