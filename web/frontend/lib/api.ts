// HTTP client. Both endpoints return { report: ReportPayload } and the
// same error envelope, so most of the work is shared in postReport()

export type Diagnostic = {
  code: string;
  message: string;
  line: number | null;
};

export type FunctionReport = {
  name: string;
  status: "ok" | "error";
  parameters: Record<string, string | null>;
  returns: string | null;
  examples: number;
  constraints: string[];
  diagnostics?: Diagnostic[];
};

export type ReportPayload = {
  functions: FunctionReport[];
  errors: Diagnostic[];
};

// Resolves the API base URL at build time.
//   - `NEXT_PUBLIC_API_URL` wins when set, EXCEPT if it points at the
//     "cdcs-mini-api.vercel.app" alias — that's a stale sibling Vercel
//     project (missing the /synthesize router). Remap defensively so the
//     UI keeps working even if the env var in the dashboard is out of date.
//   - `next dev`   → local FastAPI on 127.0.0.1:8000
//   - `next build` → the fresh backend at cdcs-mini.vercel.app
const CORRECT_PROD_API = "https://cdcs-mini.vercel.app";
const STALE_PROD_API = "https://cdcs-mini-api.vercel.app";

function resolveApiUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (explicit) return explicit === STALE_PROD_API ? CORRECT_PROD_API : explicit;
  if (process.env.NODE_ENV === "production") return CORRECT_PROD_API;
  return "http://127.0.0.1:8000";
}

export const API_URL = resolveApiUrl();

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function generateFromSource(source: string, filename = "input.py"): Promise<ReportPayload> {
  return postReport("/reports/from-source", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, source }),
  });
}

export function generateFromFile(file: File): Promise<ReportPayload> {
  const form = new FormData();
  form.append("file", file);
  return postReport("/reports/from-file", { method: "POST", body: form });
}

async function postReport(path: string, init: RequestInit): Promise<ReportPayload> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    throw new ApiError(await extractErrorDetail(response), response.status);
  }
  const data = (await response.json()) as { report: ReportPayload };
  return data.report;
}

async function extractErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // body wasn't JSON; fall through to the generic message
  }
  return `Request failed with status ${response.status}`;
}

// --- synthesis endpoint ---------------------------------------------

export type SynthesisFailure = {
  code: string;
  message: string;
  detail: string[];
  partial_implementation?: string | null;
};

export type DiagnosticInfo = {
  code: string;
  message: string;
  line: number | null;
};

export type SynthesizedFunction = {
  name: string;
  line: number;
  status: "ok" | "error" | "skipped";
  implementation: string | null;
  test: string | null;
  contract_hash: string | null;
  model: string | null;
  llm_calls: number | null;
  repair_attempts: number | null;
  failure: SynthesisFailure | null;
  upstream_diagnostics: DiagnosticInfo[];
};

export type SynthesisLanguage = "python" | "typescript";

export type SynthesizePayload = {
  source_filename: string;
  language: SynthesisLanguage;
  impl_filename: string;
  test_filename: string;
  functions: SynthesizedFunction[];
  errors: DiagnosticInfo[];
};

export async function synthesizeFromSource(
  source: string,
  filename = "input.py",
): Promise<SynthesizePayload> {
  const response = await fetch(`${API_URL}/synthesize/from-source`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, source }),
  });
  if (!response.ok) {
    throw new ApiError(await extractErrorDetail(response), response.status);
  }
  return (await response.json()) as SynthesizePayload;
}
