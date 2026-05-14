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

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

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
