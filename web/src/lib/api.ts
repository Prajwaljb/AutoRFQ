import type { Crossref, DbProduct, DbStats, Health, PipelineEvent, ReviewState, RunDetail, RunSummary, Sample } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  runs: () => request<{ runs: RunSummary[] }>("/api/runs").then((r) => r.runs),
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  health: () => request<Health>("/api/health"),
  samples: () => request<{ samples: Sample[] }>("/api/samples").then((r) => r.samples),
  email: (id: string) =>
    request<{
      subject: string;
      sender: string;
      sender_name: string;
      date: string;
      texts: { label: string; text: string }[];
      attachments: { name: string; bytes: number }[];
    }>(`/api/runs/${encodeURIComponent(id)}/email`),
  preview: (id: string) =>
    request<{ to: string; subject: string; text: string; html: string; attachments: string[] }>(
      `/api/runs/${encodeURIComponent(id)}/preview`,
    ),
  start: (form: FormData) =>
    request<{ id: string; mode: string }>("/api/runs", { method: "POST", body: form }),
  decide: (id: string, body: { flag_id: string; action: string; reviewer: string; value?: string; version: number }) =>
    request<ReviewState>(`/api/runs/${encodeURIComponent(id)}/review`, json(body)),
  undo: (id: string, version: number) =>
    request<ReviewState>(`/api/runs/${encodeURIComponent(id)}/review/undo`, json({ version })),
  approve: (id: string, reviewer: string, send: boolean) =>
    request<{ status: string; sent_to: string | null; send_error?: string }>(
      `/api/runs/${encodeURIComponent(id)}/approve`,
      json({ reviewer, send }),
    ),
  substitute: (id: string, requested: string, alternative: string, reviewer: string) =>
    request<{ ok: boolean }>(`/api/runs/${encodeURIComponent(id)}/substitute`, json({ requested, alternative, reviewer })),
  send: (id: string) =>
    request<{ status: string; sent_to: string }>(`/api/runs/${encodeURIComponent(id)}/send`, { method: "POST" }),
  adminProducts: (q = "") =>
    request<{ stats: DbStats; products: DbProduct[]; crossrefs: Crossref[] }>(`/api/admin/products?q=${encodeURIComponent(q)}`),
  adminClear: (token = "") =>
    request<{ cleared: number }>("/api/admin/clear-db", { method: "POST", headers: { "X-Admin-Token": token } }),
  adminSeed: (token = "") =>
    request<{ added: number }>("/api/admin/seed", { method: "POST", headers: { "X-Admin-Token": token } }),
  mailTest: () => request<{ ok: boolean; detail: string }>("/api/mail/test", { method: "POST" }),
  selfcheck: () =>
    request<{ ok: boolean; rows?: string; sources?: string; detail: string }>("/api/selfcheck", { method: "POST" }),
};

export const fileUrl = (id: string, name: string) =>
  `/api/runs/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`;
export const screenshotUrl = (pid: string) => `/api/pages/${encodeURIComponent(pid)}/screenshot`;

/** Subscribes to a run's pipeline events. Returns a function that closes the stream. */
export function subscribeEvents(id: string, onEvent: (e: PipelineEvent) => void, onEnd: () => void) {
  const source = new EventSource(`/api/runs/${encodeURIComponent(id)}/events`);
  source.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data) as PipelineEvent;
      if (event.type === "end") {
        source.close();
        onEnd();
      } else onEvent(event);
    } catch {
      /* keep-alive or partial line */
    }
  };
  source.onerror = () => {
    source.close();
    onEnd();
  };
  return () => source.close();
}
