import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Download, FileText, LayoutGrid, List, MailCheck, ShieldCheck } from "lucide-react";
import { api, fileUrl, subscribeEvents } from "../lib/api";
import type { Flag, Item, PipelineEvent, Run, RunDetail } from "../lib/types";
import { availability, estimatedTotal, money, senderLabel, sourceLabel } from "../lib/format";
import { severityTone, statusInfo } from "../lib/status";
import { StatusBadge, LookupBadge } from "../components/StatusBadge";
import { ItemCard, ItemCardSkeleton } from "../components/ItemCard";
import { SourceSheet } from "../components/SourceSheet";
import { PipelineSteps } from "../components/PipelineSteps";
import { EmailView } from "../components/EmailView";
import { Button, LinkButton } from "../components/ui/button";
import { Badge, Card, Dialog, ErrorBox, Skeleton, Tabs } from "../components/ui/primitives";
import { useToast } from "../components/ui/toast";
import { useReviewer } from "./ReviewPage";

type Tab = "items" | "email" | "sources" | "notes" | "activity";
const MANUAL_MINUTES_PER_ITEM = 6;

function Kpi({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Card className="p-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="tabular mt-1 text-xl font-semibold">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export function RunPage() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState("");
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [tab, setTab] = useState<Tab>("items");
  const [layout, setLayout] = useState<"cards" | "table">("cards");
  const [open, setOpen] = useState<Item | null>(null);
  const [email, setEmail] = useState<Awaited<ReturnType<typeof api.email>> | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();
  const [reviewer, askReviewer] = useReviewer();

  const load = useCallback(() => {
    api.run(id).then((d) => {
      setDetail(d);
      setError("");
    }).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  useEffect(load, [load]);

  const processing = detail?.summary.status === "processing";
  useEffect(() => {
    if (!detail) return;
    setEvents([]);
    return subscribeEvents(id, (e) => setEvents((list) => [...list, e]), () => {
      if (processing) setTimeout(load, 300);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, processing]);

  useEffect(() => {
    if (tab === "email" && !email) api.email(id).then(setEmail).catch(() => setEmail(null));
  }, [tab, email, id]);

  const run = detail?.run as Run | undefined;
  const items = run?.items ?? [];
  const flagsByItem = useMemo(() => {
    const m: Record<string, Flag[]> = {};
    for (const f of run?.flags ?? []) if (f.severity !== "info" && !f.resolved) (m[f.product_id] ??= []).push(f);
    return m;
  }, [run]);

  if (error) return <ErrorBox message={`Could not load this run: ${error}`} onRetry={load} />;
  if (!detail) return <Skeleton className="h-64 w-full" />;

  const s = detail.summary;
  const status = s.status;
  const xlsx = detail.files.find((f) => f.endsWith(".xlsx"));
  const canSend = detail.mail_configured && s.source === "inbox";
  const total = estimatedTotal(items);
  const durations = events.length > 1 ? (Number(events[events.length - 1].ts) - Number(events[0].ts)) : 0;

  async function approve(send: boolean) {
    const name = reviewer || askReviewer();
    if (!name) return;
    setBusy(true);
    try {
      const r = await api.approve(id, name, send);
      if (r.send_error) toast(`Approved, but not sent: ${r.send_error}`, "danger");
      else toast(r.sent_to ? `Sent to ${r.sent_to}.` : "Approved. The RFQ and reply were rebuilt.");
      setConfirm(false);
      load();
    } catch (e) {
      toast(String((e as Error).message), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function sendNow() {
    setBusy(true);
    try {
      const r = await api.send(id);
      toast(`Sent to ${r.sent_to}.`);
      load();
    } catch (e) {
      toast(String((e as Error).message), "danger");
    } finally {
      setBusy(false);
    }
  }

  let primary: React.ReactNode = null;
  const openFlags = detail.review ? detail.review.total - detail.review.resolved : 0;
  if (status === "needs_review") {
    primary = (
      <Button variant="primary" onClick={() => navigate(`/runs/${encodeURIComponent(id)}/review`)}>
        <ShieldCheck size={16} aria-hidden /> Review {openFlags} flag{openFlags === 1 ? "" : "s"}
      </Button>
    );
  } else if (status === "ready" && run?.quality_ran && canSend) {
    primary = (
      <Button variant="primary" onClick={() => setConfirm(true)}>
        <MailCheck size={16} aria-hidden /> Approve & send
      </Button>
    );
  } else if (status === "approved" && canSend) {
    primary = (
      <Button variant="primary" onClick={sendNow} disabled={busy}>
        <MailCheck size={16} aria-hidden /> Send reply
      </Button>
    );
  } else if (xlsx) {
    primary = (
      <LinkButton variant="primary" href={fileUrl(id, xlsx)} download>
        <Download size={16} aria-hidden /> Download RFQ.xlsx
      </LinkButton>
    );
  }

  return (
    <div className="space-y-5">
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
        <ArrowLeft size={14} aria-hidden /> Runs
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold">{s.subject || id}</h1>
            <StatusBadge status={status} />
          </div>
          <p className="mt-1 text-sm text-muted">
            {senderLabel(s.sender_name, s.sender)} · {s.received || "—"} · {s.source === "inbox" ? "from the inbox" : "uploaded"}
            {run?.mode ? ` · mode: ${run.mode}` : ""}
          </p>
          <p className="mt-1 text-sm text-muted">{statusInfo(status).hint}</p>
          {run?.reviewed_by && <p className="mt-1 text-sm">Reviewed by {run.reviewed_by}, {run.reviewed_at}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {primary}
          {xlsx && status !== "ready" && status !== "sent" && status !== "failed" && (
            <LinkButton href={fileUrl(id, xlsx)} download>
              <Download size={16} aria-hidden /> RFQ.xlsx
            </LinkButton>
          )}
          {detail.files.includes("reply.eml") && (
            <LinkButton href={fileUrl(id, "reply.eml")} download>
              <FileText size={16} aria-hidden /> reply.eml
            </LinkButton>
          )}
        </div>
      </div>

      {processing && (
        <Card className="space-y-3 p-4">
          <PipelineSteps events={events} />
          <p className="text-sm text-muted">Building the RFQ. Cards appear when the lookups finish.</p>
        </Card>
      )}
      {s.error && <ErrorBox message={s.error} />}

      {run?.counts && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Kpi label="Items" value={run.counts.items} />
          <Kpi label="Found" value={run.counts.found}
            hint={`live ${run.counts.by_source.live} · catalog ${run.counts.by_source.catalog}`} />
          <Kpi label="Not found" value={run.counts.not_found} />
          <Kpi label="Flags" value={run.counts.flags} hint={run.counts.high_flags ? `${run.counts.high_flags} high` : "none high"} />
          <Kpi label="Units standardised" value={run.units_converted ?? 0} />
          <Kpi label="Est. value" value={total ? money(total) : "—"} hint={total ? "price × qty" : "no quantities"} />
        </div>
      )}

      <Tabs
        label="Run details"
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "items", label: "Items" },
          { value: "email", label: "Email" },
          { value: "sources", label: "Sources" },
          { value: "notes", label: `Notes (${run?.notes?.length ?? 0})` },
          { value: "activity", label: "Activity" },
        ]}
      />

      {tab === "items" && (
        <div className="space-y-3">
          <div className="flex justify-end gap-1">
            <Button size="sm" variant={layout === "cards" ? "secondary" : "ghost"} onClick={() => setLayout("cards")} aria-label="Cards">
              <LayoutGrid size={14} />
            </Button>
            <Button size="sm" variant={layout === "table" ? "secondary" : "ghost"} onClick={() => setLayout("table")} aria-label="Table">
              <List size={14} />
            </Button>
          </div>
          {processing && items.length === 0 ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: Math.max(3, events.filter((e) => e.type === "item_found").length) }, (_, i) => (
                <ItemCardSkeleton key={i} />
              ))}
            </div>
          ) : layout === "cards" ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {items.map((item) => (
                <ItemCard key={item.product_id} item={item} flags={(flagsByItem[item.product_id] ?? []).length} onOpen={() => setOpen(item)} />
              ))}
            </div>
          ) : (
            <Card className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-3 py-2">#</th><th className="px-3 py-2">Item</th><th className="px-3 py-2">Description</th>
                    <th className="px-3 py-2">Status</th><th className="px-3 py-2 text-right">Unit price</th>
                    <th className="px-3 py-2">Availability</th><th className="px-3 py-2 text-right">Qty</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {items.map((item, n) => (
                    <tr key={item.product_id} className="cursor-pointer hover:bg-surface-2" onClick={() => setOpen(item)}>
                      <td className="tabular px-3 py-2 text-muted">{n + 1}</td>
                      <td className="px-3 py-2 font-mono">{item.product_id}</td>
                      <td className="px-3 py-2">{item.description || item.reason}</td>
                      <td className="px-3 py-2"><LookupBadge found={item.lookup_status === "Found"} /></td>
                      <td className="tabular px-3 py-2 text-right">{money(item.extra?.["Price (USD)"])}</td>
                      <td className="px-3 py-2">{item.lookup_status === "Found" ? availability(item.extra?.Availability) : ""}</td>
                      <td className="tabular px-3 py-2 text-right">{item.qty}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}

      {tab === "email" && (email ? <EmailView email={email} items={items} /> : <Skeleton className="h-48 w-full" />)}

      {tab === "sources" && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-3 py-2">Item</th><th className="px-3 py-2">Column</th><th className="px-3 py-2">Value</th>
                <th className="px-3 py-2">Source</th><th className="px-3 py-2">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.flatMap((item) =>
                Object.entries(item.cells)
                  .filter(([c]) => !["Description", "Image"].includes(c))
                  .map(([column, cell]) => (
                    <tr key={`${item.product_id}-${column}`} className="align-top">
                      <td className="px-3 py-2 font-mono">{item.product_id}</td>
                      <td className="px-3 py-2">{column}</td>
                      <td className="max-w-xs break-words px-3 py-2">{cell.value.length > 120 ? `${cell.value.slice(0, 120)}…` : cell.value}</td>
                      <td className="px-3 py-2"><Badge tone="info">{sourceLabel(cell.source_type)}</Badge></td>
                      <td className="px-3 py-2">{cell.confidence}</td>
                    </tr>
                  )),
              )}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "notes" && (
        <Card className="divide-y divide-border">
          {(run?.notes ?? []).length === 0 && <p className="p-4 text-sm text-muted">No notes: every item was read without problems.</p>}
          {(run?.notes ?? []).map((n, i) => (
            <div key={i} className="flex gap-3 p-3 text-sm">
              <span className="w-28 shrink-0 font-mono text-muted">{n.product_id || "email"}</span>
              <Badge>{n.stage}</Badge>
              <span>{n.text}</span>
            </div>
          ))}
          {(run?.flags ?? []).filter((f) => f.severity !== "info").map((f) => (
            <div key={f.id} className="flex gap-3 p-3 text-sm">
              <span className="w-28 shrink-0 font-mono text-muted">{f.product_id}</span>
              <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
              <span>{f.column}: {f.issue}{f.resolved ? " (resolved)" : ""}</span>
            </div>
          ))}
        </Card>
      )}

      {tab === "activity" && (
        <Card className="space-y-3 p-4 text-sm">
          <PipelineSteps events={events} />
          {durations > 0 && (
            <p>
              Processed in <span className="tabular font-semibold">{durations.toFixed(1)} s</span>. Doing this by hand takes about{" "}
              <span className="tabular font-semibold">{(items.length || 1) * MANUAL_MINUTES_PER_ITEM} min</span> ({MANUAL_MINUTES_PER_ITEM} min per item).
            </p>
          )}
          {run?.ai_status && <p className="text-muted">{run.ai_status}.</p>}
          <ol className="max-h-80 space-y-1 overflow-y-auto font-mono text-xs text-muted">
            {events.map((e, i) => (
              <li key={i}>
                +{(Number(e.ts) - Number(events[0].ts)).toFixed(2)}s {e.type}
                {e.product_id ? ` ${e.product_id}` : ""}
                {e.source ? ` (${e.source})` : ""}
                {e.error ? ` – ${e.error}` : ""}
              </li>
            ))}
          </ol>
        </Card>
      )}

      <SourceSheet item={open} flags={open ? flagsByItem[open.product_id] ?? [] : []} onClose={() => setOpen(null)} />

      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Approve and send?"
        footer={<>
          <Button onClick={() => setConfirm(false)}>Cancel</Button>
          <Button variant="primary" disabled={busy} onClick={() => approve(true)}>Approve & send</Button>
        </>}>
        <p className="text-sm">The reply with RFQ.xlsx goes to <strong>{s.sender}</strong> in the same thread. This can't be undone.</p>
      </Dialog>
    </div>
  );
}
