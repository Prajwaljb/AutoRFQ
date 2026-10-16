// Mirrors rfq/models.py (run.json) and the API in app/.

export type RunStatus =
  | "processing"
  | "ready"
  | "needs_review"
  | "approved"
  | "sent"
  | "failed"
  | "fallback_sent";

export interface RunSummary {
  id: string;
  subject: string;
  sender: string;
  sender_name: string;
  received: string;
  status: RunStatus;
  mode: string;
  source: "inbox" | "upload" | "sample";
  items: number;
  found: number;
  not_found: number;
  flags: number;
  high_flags: number;
  updated: number;
  error: string;
}

export interface Cell {
  value: string;
  source_type: string;
  confidence: string;
  source: string;
}

export interface Item {
  index: number;
  product_id: string;
  kind: "ferguson" | "code";
  brand: string;
  qty: string;
  line: string;
  lookup_status: "Found" | "Not found";
  found_via: "live" | "spec" | "catalog" | "";
  reason: string;
  description: string;
  cells: Record<string, Cell>;
  extra: Record<string, string> & { alternatives?: Alternative[]; described_as?: string; described_from?: string; replaces?: string };
}

export interface Alternative {
  product_id: string;
  description: string;
  score: number;
  matched: string[];
  price: string;
  availability: string;
}

export interface Note {
  product_id: string;
  stage: string;
  text: string;
  item_index: number;
}

export interface Flag {
  id: string;
  product_id: string;
  column: string;
  value: string;
  issue: string;
  rule: string;
  severity: "high" | "medium" | "low" | "info";
  origin: "rule" | "ai";
  resolved: boolean;
}

export interface Decision {
  flag_id: string;
  action: "keep" | "edit" | "clear";
  value: string | null;
  reviewer: string;
  at: string;
}

export interface ReviewFlag extends Flag {
  decision: Decision | null;
}

export interface ReviewState {
  version: number;
  flags: ReviewFlag[];
  ai_suggestions: ReviewFlag[];
  resolved: number;
  total: number;
  can_approve: boolean;
  approve_blocked_reason: string;
  decisions: Decision[];
}

export interface Run {
  run_id: string;
  email_file: string;
  mode: string;
  sender: string;
  sender_name: string;
  subject: string;
  received: string;
  status: RunStatus;
  counts: {
    items: number;
    found: number;
    not_found: number;
    by_source: { live: number; spec: number; catalog: number };
    flags: number;
    high_flags: number;
    warnings: number;
  };
  quality_ran: boolean;
  units_converted: number;
  ai_status: string;
  reviewed_by: string;
  reviewed_at: string;
  items: Item[];
  notes: Note[];
  flags: Flag[];
  ai_suggestions: Flag[];
  warnings: string[];
}

export interface RunDetail {
  summary: RunSummary;
  run: Run | Record<string, never>;
  files: string[];
  review?: ReviewState;
  mail_configured: boolean;
}

export interface Health {
  chrome: boolean;
  chrome_auto: boolean;
  ai: boolean;
  inbox: boolean;
  mail: boolean;
  mode: string;
  forced_mode: string | null;
  running: string[];
}

export interface PipelineEvent {
  type: string;
  ts?: number;
  [key: string]: unknown;
}

export interface Sample {
  name: string;
  subject: string;
  sender: string;
}
