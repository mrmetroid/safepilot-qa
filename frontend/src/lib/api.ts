import type { BoxId, CreateRunResponse, HealthResponse } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

/** Health may return non-2xx with a useful body (e.g. docker down). Prefer the body when it parses. */
export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  try {
    return (await res.json()) as HealthResponse;
  } catch {
    throw new Error(`${res.status} ${res.statusText}`);
  }
}

export async function createRun(
  body: { mode: "adversarial_preset" } | { mode: "custom"; url: string },
): Promise<CreateRunResponse> {
  return json(
    await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function getRun(runId: string): Promise<Record<string, unknown>> {
  return json(await fetch(`/api/runs/${encodeURIComponent(runId)}`));
}

export async function decide(runId: string, boxId: BoxId, decision: "approve" | "block") {
  return json<{ accepted: boolean; decision: string }>(
    await fetch(`/api/runs/${encodeURIComponent(runId)}/boxes/${boxId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    }),
  );
}

/** Client-side mirror of the Section 5.5 checks. The API is still the source of truth. */
export function validatePublicUrl(raw: string): string | null {
  let u: URL;
  try {
    u = new URL(raw.trim());
  } catch {
    return "Enter a full URL, for example https://example.com";
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return "Only http and https URLs can be swept.";
  const h = u.hostname.toLowerCase();
  if (
    h === "localhost" ||
    h.endsWith(".local") ||
    h.endsWith(".internal") ||
    /^127\./.test(h) ||
    /^10\./.test(h) ||
    /^192\.168\./.test(h) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(h) ||
    /^169\.254\./.test(h) ||
    h === "0.0.0.0" ||
    h.startsWith("[")
  ) {
    return "Local, private and metadata hosts are blocked. Use a public URL.";
  }
  return null;
}

/** Clipboard API needs a secure context. The VM may be served over plain HTTP, so fall back. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* fall through */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}
