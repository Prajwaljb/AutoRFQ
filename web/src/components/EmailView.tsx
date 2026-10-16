import { Fragment } from "react";
import { Paperclip } from "lucide-react";
import type { Item } from "../lib/types";
import { Badge } from "./ui/primitives";

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The email text with each detected item highlighted; repeats and competitor codes get a label. */
export function HighlightedText({ text, items }: { text: string; items: Item[] }) {
  if (!items.length) return <>{text}</>;
  const ids = [...items].sort((a, b) => b.product_id.length - a.product_id.length);
  const re = new RegExp(`(${ids.map((i) => escapeRe(i.product_id)).join("|")})`, "gi");
  const seen = new Set<string>();
  const parts = text.split(re);
  return (
    <>
      {parts.map((part, n) => {
        const item = items.find((i) => i.product_id.toLowerCase() === part.toLowerCase());
        if (!item || n % 2 === 0) return <Fragment key={n}>{part}</Fragment>;
        const repeat = seen.has(item.product_id);
        seen.add(item.product_id);
        const found = item.lookup_status === "Found";
        const competitor = item.kind === "code";
        const style = found
          ? "bg-success-bg text-success ring-success/40"
          : competitor
            ? "bg-warning-bg text-warning ring-warning/40"
            : "bg-danger-bg text-danger ring-danger/40";
        const label = repeat
          ? "repeat · kept once"
          : found
            ? "found"
            : competitor
              ? `competitor${item.brand ? ` · ${item.brand}` : ""}`
              : "not found";
        const title = found ? item.description : item.reason;
        return (
          <mark key={n} title={title} className={`rounded-md px-1 py-0.5 font-semibold ring-1 ${style}`}>
            {part}
            <span className="ml-1 rounded bg-black/10 px-1 text-[10px] font-semibold uppercase tracking-wide">{label}</span>
          </mark>
        );
      })}
    </>
  );
}

export function EmailView({
  email,
  items,
}: {
  email: { subject: string; sender: string; sender_name: string; date: string; texts: { label: string; text: string }[]; attachments: { name: string; bytes: number }[] };
  items: Item[];
}) {
  return (
    <div className="space-y-4">
      <div className="text-sm">
        <p className="font-semibold">{email.subject}</p>
        <p className="text-muted">
          {email.sender_name ? `${email.sender_name} <${email.sender}>` : email.sender} · {email.date}
        </p>
        {email.attachments.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {email.attachments.map((a) => (
              <Badge key={a.name}>
                <Paperclip size={11} aria-hidden /> {a.name} ({Math.ceil(a.bytes / 1024)} KB)
              </Badge>
            ))}
          </div>
        )}
      </div>
      {email.texts.map((t, i) => (
        <div key={i}>
          {email.texts.length > 1 && <p className="mb-1 text-xs uppercase tracking-wide text-muted">{t.label}</p>}
          <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-surface-2 p-4 font-sans text-sm leading-relaxed">
            <HighlightedText text={t.text} items={items} />
          </pre>
        </div>
      ))}
      <div className="flex flex-wrap gap-3 text-xs text-muted">
        <span><mark className="rounded bg-success-bg px-1 text-success">1234567</mark> found on ferguson.com or in the catalog</span>
        <span><mark className="rounded bg-danger-bg px-1 text-danger">1234567</mark> Ferguson number we couldn't find</span>
        <span><mark className="rounded bg-warning-bg px-1 text-warning">AB-123</mark> another brand's part: we suggest a Ferguson equivalent</span>
      </div>
      {email.attachments.length > 0 && (
        <p className="text-xs text-muted">Items found in attachments are listed on the Items tab with their sheet row.</p>
      )}
    </div>
  );
}
