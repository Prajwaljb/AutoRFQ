import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Inbox, Plus } from "lucide-react";
import { api } from "../lib/api";
import { sortRuns, tabOf, type RunTab } from "../lib/sort";
import type { RunSummary } from "../lib/types";
import { age, ago } from "../lib/format";
import { StatusBadge } from "../components/StatusBadge";
import { LinkButton } from "../components/ui/button";
import { Card, EmptyState, ErrorBox, Skeleton, Tabs } from "../components/ui/primitives";

const TABS: { value: RunTab; label: string }[] = [
  { value: "needs_review", label: "Needs review" },
  { value: "processing", label: "Processing" },
  { value: "ready", label: "Ready" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
  { value: "all", label: "All" },
];

export function RunsPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<RunTab>("all");
  const navigate = useNavigate();

  const load = useCallback(() => {
    api.runs().then((r) => {
      setRuns(r);
      setError("");
    }).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  const counts = useMemo(() => {
    const c: Record<RunTab, number> = { needs_review: 0, processing: 0, ready: 0, sent: 0, failed: 0, all: 0 };
    for (const r of runs ?? []) {
      c[tabOf(r.status)] += 1;
      c.all += 1;
    }
    return c;
  }, [runs]);

  const shown = useMemo(
    () => sortRuns((runs ?? []).filter((r) => tab === "all" || tabOf(r.status) === tab)),
    [runs, tab],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Runs</h1>
          <p className="text-sm text-muted">Every RFQ email, from the inbox or uploaded here. Held RFQs wait for review first.</p>
        </div>
      </div>
      <Tabs
        label="Run status"
        value={tab}
        onChange={setTab}
        tabs={TABS.map((t) => ({
          value: t.value,
          label: (
            <span className="flex items-center gap-1.5">
              {t.label}
              <span className="tabular rounded-full bg-surface-2 px-1.5 text-xs text-muted">{counts[t.value]}</span>
            </span>
          ),
        }))}
      />
      {error && <ErrorBox message={`Could not load runs: ${error}`} onRetry={load} />}
      {runs === null && !error ? (
        <Card className="divide-y divide-border">
          {Array.from({ length: 4 }, (_, i) => (
            <div key={i} className="flex items-center gap-4 p-4">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-4 w-1/5" />
              <Skeleton className="ml-auto h-5 w-20" />
            </div>
          ))}
        </Card>
      ) : shown.length === 0 && !error ? (
        <EmptyState icon={<Inbox size={28} />} title={tab === "all" ? "No RFQs yet" : "Nothing here"}>
          {tab === "all" ? (
            <>
              Upload a request email or try a sample to see the flow.{" "}
              <div className="mt-3">
                <LinkButton href="/new" variant="primary" size="sm">
                  <Plus size={16} aria-hidden /> New RFQ
                </LinkButton>
              </div>
            </>
          ) : (
            "No runs with this status."
          )}
        </EmptyState>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-4 py-2 font-medium">Customer</th>
                <th className="px-4 py-2 font-medium">Subject</th>
                <th className="px-4 py-2 font-medium">Updated</th>
                <th className="px-4 py-2 text-right font-medium">Items</th>
                <th className="px-4 py-2 text-right font-medium">Flags</th>
                <th className="px-4 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shown.map((r) => (
                <tr
                  key={r.id}
                  tabIndex={0}
                  onClick={() => navigate(`/runs/${encodeURIComponent(r.id)}`)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(`/runs/${encodeURIComponent(r.id)}`)}
                  className="cursor-pointer hover:bg-surface-2 focus:bg-surface-2"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium">{r.sender_name || r.sender || "—"}</div>
                    <div className="text-xs text-muted">{r.source === "inbox" ? "Inbox" : "Uploaded"}</div>
                  </td>
                  <td className="max-w-md px-4 py-3">
                    <Link to={`/runs/${encodeURIComponent(r.id)}`} className="line-clamp-1 hover:underline" onClick={(e) => e.stopPropagation()}>
                      {r.subject || r.id}
                    </Link>
                    {r.error && <div className="line-clamp-1 text-xs text-danger">{r.error}</div>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted">
                    {r.status === "needs_review" ? `waiting ${age(r.updated)}` : ago(r.updated)}
                  </td>
                  <td className="tabular px-4 py-3 text-right">{r.status === "processing" ? "—" : `${r.found}/${r.items}`}</td>
                  <td className="tabular px-4 py-3 text-right">{r.flags ? (r.high_flags ? `${r.flags} (${r.high_flags} high)` : r.flags) : "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
