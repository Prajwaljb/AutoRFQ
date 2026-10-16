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
  missing: number;
  fill_rate: number;
  units_converted: number;
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
  extra: Record<string, string> & {
    alternatives?: Alternative[];
    described_as?: string;
    described_from?: string;
    replaces?: string;
    competitor?: Competitor;
  };
}

export interface Competitor {
  code: string;
  brand: string;
  description: string;
  title?: string;
  specs: Record<string, { value: string; source: string }>;
  sources: string[];
  confirmed?: string;
  confirmed_by?: string;
}

export interface Crossref {
  code: string;
  brand: string;
  description: string;
  sources: string[];
  known: boolean;
  confirmed: string;
  confirmed_by: string;
  updated_at: number;
}

export interface Alternative {
  product_id: string;
  description: string;
  score: number;
  matched: string[];
  confidence?: "confirmed" | "strong" | "possible";
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
  missing: number;
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
    missing: number;
    ai_flags: number;
    fill_rate: number;
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
  mail_log?: MailEntry[];
}

export interface MailEntry {
  id: number;
  at: number;
  at_text: string;
  run_id: string;
  kind: string;
  to_addr: string;
  subject: string;
  attachments: string;
  message_id: string;
  status: "sent" | "failed";
  error: string;
  sent_by: string;
}

export interface Health {
  chrome: boolean;
  chrome_auto: boolean;
  ai: boolean;
  inbox: boolean;
  inbox_info?: { watching: boolean; by: string; email: string; error: string; seconds_ago: number | null };
  mail: boolean;
  mode: string;
  forced_mode: string | null;
  running: string[];
  settings?: Record<string, Record<string, boolean>>;
  api_version?: number;
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

export interface DbStats {
  products: number;
  by_source: Record<string, number>;
  reused: number;
  last_updated: number | null;
  path: string;
  ttl_hours: number;
  crossrefs: number;
  token_required: boolean;
  now: number;
}

export interface DbProduct {
  product_id: string;
  description: string;
  source: string;
  url: string;
  fetched_at: number;
  updated_at: number;
  hits: number;
  price: string;
  availability: string;
  cells: number;
}
