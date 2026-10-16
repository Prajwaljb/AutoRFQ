import { AlertTriangle, BadgeCheck, CheckCircle2, Loader2, Send, XCircle } from "lucide-react";
import { Badge } from "./ui/primitives";
import { statusInfo } from "../lib/status";

const ICONS = { check: CheckCircle2, alert: AlertTriangle, loader: Loader2, send: Send, x: XCircle, badge: BadgeCheck };

export function StatusBadge({ status }: { status: string }) {
  const info = statusInfo(status);
  const Icon = ICONS[info.icon];
  return (
    <Badge tone={info.tone}>
      <Icon size={12} className={info.icon === "loader" ? "animate-spin" : undefined} aria-hidden />
      <span title={info.hint}>{info.label}</span>
    </Badge>
  );
}

export function LookupBadge({ found }: { found: boolean }) {
  return found ? (
    <Badge tone="success">
      <CheckCircle2 size={12} aria-hidden /> Found
    </Badge>
  ) : (
    <Badge tone="danger">
      <XCircle size={12} aria-hidden /> Not found
    </Badge>
  );
}
