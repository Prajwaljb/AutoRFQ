import type { RunStatus } from "./types";

export type Tone = "success" | "warning" | "danger" | "info" | "neutral";

export interface StatusInfo {
  label: string;
  tone: Tone;
  icon: "check" | "alert" | "loader" | "send" | "x" | "badge";
  hint: string;
}

const STATUS: Record<RunStatus, StatusInfo> = {
  processing: { label: "Processing", tone: "info", icon: "loader", hint: "The RFQ is being built." },
  ready: { label: "Ready", tone: "success", icon: "check", hint: "RFQ built; no value needs review." },
  needs_review: {
    label: "Needs review",
    tone: "warning",
    icon: "alert",
    hint: "Held: a person must check the flagged values before the customer gets it.",
  },
  approved: { label: "Approved", tone: "success", icon: "badge", hint: "Reviewed and rebuilt; not sent yet." },
  sent: { label: "Sent", tone: "neutral", icon: "send", hint: "The reply is in the customer's thread." },
  failed: { label: "Failed", tone: "danger", icon: "x", hint: "The flow could not finish this email." },
  fallback_sent: {
    label: "Follow-up sent",
    tone: "danger",
    icon: "x",
    hint: "The customer was told a person will follow up.",
  },
};

export function statusInfo(status: string): StatusInfo {
  return STATUS[status as RunStatus] ?? { label: status, tone: "neutral", icon: "badge", hint: "" };
}

export function severityTone(severity: string): Tone {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  if (severity === "low") return "info";
  return "neutral";
}
