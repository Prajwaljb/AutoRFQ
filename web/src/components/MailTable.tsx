import { Badge } from "./ui/primitives";
import type { MailEntry } from "../lib/types";

export const KIND_LABEL: Record<string, string> = {
  reply: "Reply to customer",
  rfq_email: "RFQ emailed",
  fallback: "Follow-up notice",
  review_notice: "Review notice",
};

/** The log of sent emails: who got what, when, from which part of the system, and whether it went through. */
export function MailTable({ entries, showRun = true }: { entries: MailEntry[]; showRun?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-3 py-2">When</th>
            <th className="px-3 py-2">To</th>
            <th className="px-3 py-2">Subject</th>
            <th className="px-3 py-2">Type</th>
            {showRun && <th className="px-3 py-2">Run</th>}
            <th className="px-3 py-2">Attached</th>
            <th className="px-3 py-2">Sent from</th>
            <th className="px-3 py-2">Result</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {entries.map((e) => (
            <tr key={e.id} className="hover:bg-surface-2">
              <td className="tabular whitespace-nowrap px-3 py-2 text-muted">{e.at_text}</td>
              <td className="px-3 py-2">{e.to_addr}</td>
              <td className="max-w-xs px-3 py-2"><span className="line-clamp-1" title={e.subject}>{e.subject}</span></td>
              <td className="whitespace-nowrap px-3 py-2">{KIND_LABEL[e.kind] ?? e.kind}</td>
              {showRun && (
                <td className="px-3 py-2 font-mono text-xs">
                  {e.run_id ? <a href={`/runs/${encodeURIComponent(e.run_id)}`} className="hover:underline">{e.run_id}</a> : "—"}
                </td>
              )}
              <td className="px-3 py-2 text-muted">{e.attachments || "—"}</td>
              <td className="whitespace-nowrap px-3 py-2 text-muted">{e.sent_by || "—"}</td>
              <td className="px-3 py-2">
                {e.status === "sent" ? (
                  <Badge tone="success">Sent</Badge>
                ) : (
                  <span title={e.error}><Badge tone="danger">Failed</Badge></span>
                )}
                {e.status === "failed" && e.error && <div className="mt-0.5 max-w-xs text-xs text-muted">{e.error}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
