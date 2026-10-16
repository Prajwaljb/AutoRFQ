import { useCallback, useEffect, useState } from "react";
import { Mail, RefreshCw } from "lucide-react";
import { api } from "../lib/api";
import type { MailEntry } from "../lib/types";
import { Button } from "../components/ui/button";
import { Card, EmptyState, ErrorBox, Skeleton } from "../components/ui/primitives";
import { MailTable, KIND_LABEL } from "../components/MailTable";

const FIELD = "h-9 rounded-md border border-border bg-surface px-2 text-sm";

/** Every email the system has sent, newest first. Kept in its own database, so Clear database never touches it. */
export function MailPage() {
  const [entries, setEntries] = useState<MailEntry[] | null>(null);
  const [counts, setCounts] = useState({ sent: 0, failed: 0 });
  const [kinds, setKinds] = useState<string[]>([]);
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api.mailLog({ status, kind }).then((r) => {
      setEntries(r.entries);
      setCounts(r.counts);
      setKinds(r.kinds);
      setError("");
    }).catch((e) => setError(String(e.message ?? e)));
  }, [status, kind]);
  useEffect(load, [load]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold"><Mail size={20} className="text-accent" aria-hidden /> Sent mail</h1>
          <p className="text-sm text-muted">Every reply, RFQ email and notice the system sent, with the result. Open a run to see its own mail.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select aria-label="Result" className={FIELD} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All results</option>
            <option value="sent">Sent ({counts.sent})</option>
            <option value="failed">Failed ({counts.failed})</option>
          </select>
          <select aria-label="Type" className={FIELD} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All types</option>
            {kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k] ?? k}</option>)}
          </select>
          <Button onClick={load}><RefreshCw size={16} aria-hidden /> Refresh</Button>
        </div>
      </div>
      {error && <ErrorBox message={`Could not load the mail log: ${error}`} onRetry={load} />}
      <Card className="p-4">
        {entries === null ? (
          <Skeleton className="h-40 w-full" />
        ) : entries.length === 0 ? (
          <EmptyState icon={<Mail size={28} />} title="No emails sent yet">
            Replies sent from the inbox or the dashboard appear here, one row per attempt.
          </EmptyState>
        ) : (
          <MailTable entries={entries} />
        )}
      </Card>
      <p className="text-xs text-muted">Stored in <code className="font-mono">out/db/mail.db</code> (SQLite), separate from the product database.</p>
    </div>
  );
}
