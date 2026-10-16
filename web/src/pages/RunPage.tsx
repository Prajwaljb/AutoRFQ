import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Download, FileText, LayoutGrid, List, MailCheck, ShieldCheck, Sparkles } from "lucide-react";
import { api, fileUrl, subscribeEvents } from "../lib/api";
import type { Flag, Item, PipelineEvent, Run, RunDetail } from "../lib/types";
import { availability, estimatedTotal, money, senderLabel, sourceLabel } from "../lib/format";
import { severityLabel, severityTone, statusInfo } from "../lib/status";
import { StatusBadge, LookupBadge } from "../components/StatusBadge";
import { ItemCard, ItemCardSkeleton } from "../components/ItemCard";
import { SourceSheet } from "../components/SourceSheet";
import { PipelineSteps, stepState } from "../components/PipelineSteps";
import { Confetti, CountUp, FillRing, PipelineStrip } from "../components/fx";
import { EmailView } from "../components/EmailView";
import { Button, LinkButton } from "../components/ui/button";
import { Badge, Card, Dialog, ErrorBox, Skeleton, Tabs } from "../components/ui/primitives";
import { useToast } from "../components/ui/toast";
import { useReviewer } from "./ReviewPage";

type Tab = "items" | "email" | "sources" | "notes" | "activity";
const MANUAL_MINUTES_PER_ITEM = 6;

function describeEvent(e: PipelineEvent): string {
  const pid = e.product_id ? ` ${e.product_id}` : "";
  switch (e.type) {
    case "email_read": return `read the email: ${e.subject ?? ""}`;
    case "item_found": return `found item${pid}`;
    case "lookup_start": return `looking up${pid} (${e.source})`;
    case "lookup_done": return `${e.found ? "got" : "no result for"}${pid} from ${e.source}${e.error ? ` – ${e.error}` : ""}`;
    case "spec_pdf_read": return `read the spec sheet for${pid}`;
    case "alternatives": return `suggested alternatives for${pid}`;
    case "quality_flag": return `flagged${pid} ${e.column}: ${String(e.rule).replaceAll("_", " ")}`;
    case "excel_saved": return "saved RFQ.xlsx";
    case "reply_saved": return "wrote the reply";
    case "run_done": return `done: ${e.status}`;
    default: return e.type;
  }
}

const STAGE_LABEL: Record<string, string> = {
  extract: "Reading the email",
  lookup: "Lookup",
  spec: "Spec sheet",
  quality: "Quality agent",
  output: "Output",
};

/** Notes in plain words: what happened to each item, the values to check, and the blanks per item. */
function NotesTab({ run }: { run: Run }) {
  const toCheck = run.flags.filter((f) => f.severity === "high" || f.severity === "medium");
  const blanks: Record<string, string[]> = {};
  for (const f of run.flags) if (f.rule === "missing") (blanks[f.product_id] ??= []).push(f.column);
  return (
    <div className="space-y-4">
      <Card className="grid gap-3 p-4 text-sm md:grid-cols-3">
        <div className="flex items-start gap-2"><Badge tone="danger">{severityLabel("high")}</Badge><span className="text-muted">Probably wrong. Holds the RFQ until a person decides.</span></div>
        <div className="flex items-start gap-2"><Badge tone="warning">{severityLabel("medium")}</Badge><span className="text-muted">Worth a second look. Doesn't hold the RFQ.</span></div>
        <div className="flex items-start gap-2"><Badge>{severityLabel("low")}</Badge><span className="text-muted">No source had a value, so the cell stays empty. Blank means unknown; it's never guessed.</span></div>
      </Card>

      <Card className="divide-y divide-border">
        <h3 className="p-3 text-sm font-semibold">Values to check ({toCheck.length})</h3>
        {toCheck.length === 0 && <p className="p-3 text-sm text-muted">Nothing looks wrong.</p>}
        {toCheck.map((f) => (
          <div key={f.id} className="flex flex-wrap items-start gap-3 p-3 text-sm">
            <span className="w-24 shrink-0 font-mono text-muted">{f.product_id}</span>
            <Badge tone={severityTone(f.severity)}>{severityLabel(f.severity)}</Badge>
            <span className="min-w-0 flex-1"><span className="font-medium">{f.column}</span>
              {f.value && <span className="text-muted"> “{f.value}”</span>}: {f.issue}{f.resolved ? " (resolved)" : ""}</span>
          </div>
        ))}
        {(run.ai_suggestions ?? []).map((f) => (
          <div key={f.id} className="flex flex-wrap items-start gap-3 p-3 text-sm">
            <span className="w-24 shrink-0 font-mono text-muted">{f.product_id}</span>
            <Badge className="mark-model !text-[#7c2d12]">AI note</Badge>
            <span className="min-w-0 flex-1"><span className="font-medium">{f.column}</span>: {f.issue}</span>
          </div>
        ))}
      </Card>

      {Object.keys(blanks).length > 0 && (
        <Card className="divide-y divide-border">
          <h3 className="p-3 text-sm font-semibold">Blank cells per item ({run.counts.missing ?? 0})</h3>
          {Object.entries(blanks).map(([pid, cols]) => (
            <div key={pid} className="flex flex-wrap items-start gap-3 p-3 text-sm">
              <span className="w-24 shrink-0 font-mono text-muted">{pid}</span>
              <Badge>{cols.length} blank</Badge>
              <span className="min-w-0 flex-1 text-muted">{cols.join(", ")}</span>
            </div>
          ))}
        </Card>
      )}

      <Card className="divide-y divide-border">
        <h3 className="p-3 text-sm font-semibold">What happened ({run.notes.length})</h3>
        {run.notes.length === 0 && <p className="p-3 text-sm text-muted">Every item was read without problems.</p>}
        {run.notes.map((n, i) => (
          <div key={i} className="flex flex-wrap items-start gap-3 p-3 text-sm">
            <span className="w-24 shrink-0 font-mono text-muted">{n.product_id || "email"}</span>
            <Badge tone="info">{STAGE_LABEL[n.stage] ?? n.stage}</Badge>
            <span className="min-w-0 flex-1">{n.text}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}

/** What the quality agent did, in the same colours as the Excel: grey missing, amber code, orange model. */
function AgentFindings({ run }: { run: Run }) {
  const code = run.flags.filter((f) => !f.resolved && (f.severity === "high" || f.severity === "medium"));
  const missing = run.counts.missing ?? run.flags.filter((f) => f.rule === "missing").length;
  const model = run.ai_suggestions ?? [];
  return (
    <Card className="fade-up p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold"><Sparkles size={16} className="text-accent" aria-hidden /> Agent findings</h2>
          <p className="text-xs text-muted">Flags, never overwrites: every value stays for a person to decide. Same colours as RFQ.xlsx.</p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1"><span className="mark-missing h-2.5 w-2.5 rounded-sm" /> {missing} missing · code</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1"><span className="mark-code h-2.5 w-2.5 rounded-sm" /> {code.length} suspicious · code</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1"><span className="mark-model h-2.5 w-2.5 rounded-sm" /> {model.length} suspicious · model</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1">{run.units_converted} units standardised</span>
        </div>
      </div>
      {(code.length > 0 || model.length > 0) && (
        <ul className="mt-4 grid gap-2 md:grid-cols-2">
          {[...code.map((f) => ({ f, by: "code" })), ...model.map((f) => ({ f, by: "model" }))].slice(0, 8).map(({ f, by }, i) => (
            <li key={f.id} className="fade-up flex items-start gap-3 rounded-lg border border-border bg-surface-2/60 p-3 text-sm" style={{ animationDelay: `${i * 50}ms` }}>
              <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-sm ${by === "model" ? "mark-model" : "mark-code"}`} aria-hidden />
              <span className="min-w-0">
                <span className="font-mono text-xs text-muted">{f.product_id}</span> · <span className="font-medium">{f.column}</span>
                <Badge tone={severityTone(f.severity)} className="ml-2">{severityLabel(f.severity)}</Badge>
                <Badge className="ml-1">by {by}</Badge>
                <span className="mt-0.5 block text-muted">{f.issue}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">{run.ai_status}.</p>
    </Card>
  );
}

function Kpi({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <Card className="lift p-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl font-bold text-gradient">{value}</div>
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
  const location = useLocation();
  const [celebrate, setCelebrate] = useState(() => ((location.state as { celebrate?: boolean } | null)?.celebrate ? 1 : 0));
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
      else {
        toast(r.sent_to ? `Sent to ${r.sent_to}.` : "Approved. The RFQ and reply were rebuilt.");
        setCelebrate((n) => n + 1);
      }
      setConfirm(false);
      load();
    } catch (e) {
      toast(String((e as Error).message), "danger");
    } finally {
      setBusy(false);
    }
  }

  async function substitute(requested: string, alternative: string) {
    const name = reviewer || askReviewer();
    if (!name) return;
    if (!window.confirm(`Replace ${requested} with Ferguson item ${alternative} on this RFQ? The reply asks the customer to confirm.`)) return;
    try {
      await api.substitute(id, requested, alternative, name);
      toast(`${requested} replaced by ${alternative}.`);
      setOpen(null);
      load();
    } catch (e) {
      toast(String((e as Error).message), "danger");
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
        <Card className="space-y-4 p-5">
          <PipelineStrip active={stepState(events) + (stepState(events) > 0 ? 1 : 0)} />
          <ol className="space-y-1 font-mono text-xs text-muted" aria-live="polite">
            {events.slice(-5).map((e, i) => (
              <li key={i} className="fade-up">› {describeEvent(e)}</li>
            ))}
            {!events.length && <li>› starting…</li>}
          </ol>
        </Card>
      )}
      {s.error && <ErrorBox message={s.error} />}

      {run?.counts && (
        <div className="grid gap-3 lg:grid-cols-[auto_1fr]">
          <Card className="flex items-center justify-center p-4">
            <FillRing value={run.counts.fill_rate ?? 0} />
          </Card>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Kpi label="Items" value={<CountUp value={run.counts.items} />} />
            <Kpi label="Found" value={<CountUp value={run.counts.found} />}
              hint={`live ${run.counts.by_source.live} · catalog ${run.counts.by_source.catalog}`} />
            <Kpi label="Not found" value={<CountUp value={run.counts.not_found} />} />
            <Kpi label="To check" value={<CountUp value={run.counts.flags} />} hint={run.counts.high_flags ? `${run.counts.high_flags} high` : "none high"} />
            <Kpi label="Units standardised" value={<CountUp value={run.units_converted ?? 0} />} />
            <Kpi label="Est. value" value={total ? <CountUp value={total} decimals={2} prefix="$" /> : "—"} hint={total ? "price × qty" : "no quantities"} />
          </div>
        </div>
      )}

      {run?.quality_ran && <AgentFindings run={run} />}

      <Tabs
        label="Run details"
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "items", label: "Items" },
          { value: "email", label: "Email" },
          { value: "sources", label: "Sources" },
          { value: "notes", label: `Notes & flags (${(run?.counts?.flags ?? 0) + (run?.notes?.length ?? 0)})` },
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
              {items.map((item, i) => (
                <ItemCard key={item.product_id} item={item} delay={Math.min(i, 12) * 45}
                  flags={(flagsByItem[item.product_id] ?? []).length} onOpen={() => setOpen(item)} />
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

      {tab === "notes" && run && <NotesTab run={run} />}

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

      <Confetti fire={celebrate} />
      <SourceSheet
        item={open}
        flags={open ? flagsByItem[open.product_id] ?? [] : []}
        onClose={() => setOpen(null)}
        onSubstitute={status === "ready" || status === "needs_review" ? substitute : undefined}
      />

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
