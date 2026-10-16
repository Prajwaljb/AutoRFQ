import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, ChevronDown, ChevronRight, Eraser, Eye, MailCheck, Pencil, Undo2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import type { ReviewFlag, ReviewState, Run, RunDetail } from "../lib/types";
import { sortFlags } from "../lib/sort";
import { sourceLabel } from "../lib/format";
import { severityTone } from "../lib/status";
import { Button } from "../components/ui/button";
import { Badge, Card, Dialog, ErrorBox, Skeleton } from "../components/ui/primitives";
import { cn } from "../components/ui/cn";
import { useToast } from "../components/ui/toast";

/** The reviewer's name: asked once, stored in this browser (no accounts in this version). */
export function useReviewer(): [string, () => string] {
  const [name, setName] = useState(() => localStorage.getItem("reviewer") ?? "");
  const ask = useCallback(() => {
    const value = (window.prompt("Your name, recorded with each review decision:", name) ?? "").trim();
    if (value) {
      localStorage.setItem("reviewer", value);
      setName(value);
    }
    return value;
  }, [name]);
  return [name, ask];
}

const ACTION_LABEL = { keep: "Kept", edit: "Edited", clear: "Cleared" };

export function ReviewPage() {
  const { id = "" } = useParams();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [review, setReview] = useState<ReviewState | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  const [editing, setEditing] = useState<string | null>(null);
  const [showAi, setShowAi] = useState(false);
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof api.preview>> | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reviewer, askReviewer] = useReviewer();
  const toast = useToast();
  const navigate = useNavigate();

  const load = useCallback(() => {
    api.run(id).then((d) => {
      setDetail(d);
      setReview(d.review ?? null);
      setError("");
    }).catch((e) => setError(String(e.message ?? e)));
  }, [id]);
  useEffect(load, [load]);

  const run = detail?.run as Run | undefined;
  const order = useMemo(() => (run?.items ?? []).map((i) => i.product_id), [run]);
  const flags = useMemo(() => sortFlags(review?.flags ?? [], order), [review, order]);
  const current: ReviewFlag | undefined = flags[selected];
  const item = run?.items.find((i) => i.product_id === current?.product_id);

  const act = useCallback(
    async (action: "keep" | "edit" | "clear", value?: string) => {
      if (!current || !review) return;
      const name = reviewer || askReviewer();
      if (!name) return;
      try {
        const next = await api.decide(id, { flag_id: current.id, action, reviewer: name, value, version: review.version });
        setReview(next);
        setEditing(null);
        setSelected((s) => Math.min(s + 1, flags.length - 1));
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          toast("Someone else changed this review. Reloaded.", "danger");
          load();
        } else toast(String((e as Error).message), "danger");
      }
    },
    [current, review, reviewer, askReviewer, id, flags.length, toast, load],
  );

  const undo = useCallback(async () => {
    if (!review || review.decisions.length === 0) return;
    try {
      setReview(await api.undo(id, review.version));
    } catch (e) {
      toast(String((e as Error).message), "danger");
      load();
    }
  }, [review, id, toast, load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing !== null || confirm || preview) return;
      const target = e.target as HTMLElement;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setSelected((s) => Math.min(s + 1, flags.length - 1)); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setSelected((s) => Math.max(s - 1, 0)); }
      else if (e.key === "Enter") { e.preventDefault(); act("keep"); }
      else if (e.key.toLowerCase() === "e" && !e.ctrlKey && !e.metaKey) { e.preventDefault(); setEditing(current?.value ?? ""); }
      else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); act("clear"); }
      else if (e.key.toLowerCase() === "z" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); undo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flags.length, act, undo, editing, confirm, preview, current]);

  if (error) return <ErrorBox message={`Could not load the review: ${error}`} onRetry={load} />;
  if (!detail || !review) return <Skeleton className="h-96 w-full" />;

  const canSend = detail.mail_configured && detail.summary.source === "inbox";

  async function approve() {
    const name = reviewer || askReviewer();
    if (!name) return;
    setBusy(true);
    try {
      const r = await api.approve(id, name, canSend);
      if (r.send_error) toast(`Approved, but not sent: ${r.send_error}`, "danger");
      else toast(r.sent_to ? `Approved and sent to ${r.sent_to}.` : "Approved. RFQ.xlsx and the reply were rebuilt without review marks.");
      navigate(`/runs/${encodeURIComponent(id)}`);
    } catch (e) {
      toast(String((e as Error).message), "danger");
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  }

  const evidence = item && current ? item.cells[current.column] : undefined;

  return (
    <div className="flex min-h-[calc(100vh-8rem)] flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={`/runs/${encodeURIComponent(id)}`} className="inline-flex items-center gap-1 text-sm text-muted hover:text-text">
            <ArrowLeft size={14} aria-hidden /> {detail.summary.subject}
          </Link>
          <h1 className="text-xl font-semibold">Review</h1>
        </div>
        <div className="text-sm text-muted" aria-live="polite">
          <span className="tabular font-semibold text-text">{review.resolved} of {review.total}</span> resolved
          {reviewer && <> · reviewing as <button className="underline" onClick={askReviewer}>{reviewer}</button></>}
        </div>
      </div>

      <div className="grid flex-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card className="flex flex-col overflow-hidden">
          <ul className="flex-1 divide-y divide-border overflow-y-auto" role="listbox" aria-label="Flags">
            {flags.length === 0 && <li className="p-4 text-sm text-muted">No rule flags on this RFQ.</li>}
            {flags.map((f, i) => (
              <li key={f.id}>
                <button
                  role="option"
                  aria-selected={i === selected}
                  onClick={() => setSelected(i)}
                  className={cn("flex w-full items-start gap-3 p-3 text-left text-sm", i === selected ? "bg-surface-2" : "hover:bg-surface-2")}
                >
                  <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
                  <span className="min-w-0 flex-1">
                    <span className="font-mono text-xs text-muted">{f.product_id}</span>
                    <span className="block font-medium">{f.column}</span>
                    <span className="line-clamp-1 text-muted">{f.issue}</span>
                  </span>
                  {f.decision && (
                    <Badge tone="success"><Check size={11} aria-hidden /> {ACTION_LABEL[f.decision.action]}</Badge>
                  )}
                </button>
              </li>
            ))}
          </ul>
          <div className="border-t border-border">
            <button className="flex w-full items-center gap-2 p-3 text-sm font-medium" onClick={() => setShowAi((v) => !v)} aria-expanded={showAi}>
              {showAi ? <ChevronDown size={14} /> : <ChevronRight size={14} />} AI suggestions ({review.ai_suggestions.length})
              <Badge className="ml-auto">advisory</Badge>
            </button>
            {showAi && (
              <ul className="max-h-48 divide-y divide-border overflow-y-auto">
                {review.ai_suggestions.length === 0 && (
                  <li className="px-3 pb-3 text-sm text-muted">{run?.ai_status || "No AI suggestions."}</li>
                )}
                {review.ai_suggestions.map((f) => (
                  <li key={f.id} className="p-3 text-sm">
                    <span className="font-mono text-xs text-muted">{f.product_id}</span> · <span className="font-medium">{f.column}</span>: {f.issue}
                    <span className="block text-xs text-muted">Quoted value: “{f.value}”. Suggestions never change a value or the status.</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>

        <Card className="p-5">
          {current && item ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-lg font-semibold">{item.product_id}</span>
                <Badge tone={severityTone(current.severity)}>{current.severity}</Badge>
                <Badge>{current.rule.replaceAll("_", " ")}</Badge>
              </div>
              <p className="text-sm text-muted">{item.description}</p>
              <div className="rounded-md border border-border bg-surface-2 p-4">
                <div className="text-xs uppercase tracking-wide text-muted">{current.column}</div>
                <div className="mt-1 text-lg font-semibold">{current.value || <span className="text-muted">blank</span>}</div>
                <p className="mt-2 text-sm">{current.issue}</p>
                {evidence && (
                  <p className="mt-2 break-words text-xs text-muted">
                    Source: {sourceLabel(evidence.source_type)} ({evidence.confidence}) – {evidence.source}
                  </p>
                )}
              </div>

              {editing !== null ? (
                <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); act("edit", editing); }}>
                  <input autoFocus value={editing} onChange={(e) => setEditing(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                    aria-label={`New value for ${current.column}`}
                    className="h-10 flex-1 rounded-md border border-border bg-surface px-3 text-sm" />
                  <Button type="submit" variant="primary">Save</Button>
                  <Button type="button" onClick={() => setEditing(null)}>Cancel</Button>
                </form>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <Button variant="primary" onClick={() => act("keep")}><Check size={16} aria-hidden /> Keep value <kbd className="text-xs opacity-70">Enter</kbd></Button>
                  <Button onClick={() => setEditing(current.value)}><Pencil size={16} aria-hidden /> Edit <kbd className="text-xs opacity-70">E</kbd></Button>
                  <Button onClick={() => act("clear")}><Eraser size={16} aria-hidden /> Clear (unknown) <kbd className="text-xs opacity-70">Del</kbd></Button>
                  <Button variant="ghost" onClick={undo} disabled={!review.decisions.length}><Undo2 size={16} aria-hidden /> Undo <kbd className="text-xs opacity-70">Ctrl+Z</kbd></Button>
                </div>
              )}
              {current.decision && (
                <p className="text-sm text-success">
                  {ACTION_LABEL[current.decision.action]} by {current.decision.reviewer}
                  {current.decision.value ? `: “${current.decision.value}”` : ""} ({current.decision.at})
                </p>
              )}

              <details className="text-sm">
                <summary className="cursor-pointer text-muted">Other fields of this product</summary>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                  {Object.entries(item.cells).filter(([c]) => !["Image", "Picture", "Product details"].includes(c)).map(([c, cell]) => (
                    <div key={c} className="contents">
                      <dt className="text-muted">{c}</dt>
                      <dd className="break-words">{cell.value}</dd>
                    </div>
                  ))}
                </dl>
              </details>
              <p className="text-xs text-muted">Keys: ↑/↓ move · Enter keep · E edit · Del clear · Ctrl+Z undo</p>
            </div>
          ) : (
            <p className="text-sm text-muted">Nothing to review.</p>
          )}
        </Card>
      </div>

      <div className="sticky bottom-0 flex flex-wrap items-center justify-end gap-3 border-t border-border bg-background py-3">
        {!review.can_approve && <span className="text-sm text-warning">{review.approve_blocked_reason}</span>}
        <Button onClick={() => api.preview(id).then(setPreview).catch((e) => toast(String(e.message), "danger"))}>
          <Eye size={16} aria-hidden /> Preview customer email
        </Button>
        <Button variant="primary" disabled={!review.can_approve || busy} onClick={() => setConfirm(true)}
          title={review.can_approve ? undefined : review.approve_blocked_reason}>
          <MailCheck size={16} aria-hidden /> {canSend ? "Approve & send" : "Approve"}
        </Button>
      </div>

      <Dialog open={!!preview} onClose={() => setPreview(null)} wide title="Customer email (current draft)">
        {preview && (
          <div className="space-y-3 text-sm">
            <p><span className="text-muted">To:</span> {preview.to}<br /><span className="text-muted">Subject:</span> {preview.subject}<br />
              <span className="text-muted">Attachment:</span> {preview.attachments.join(", ")}</p>
            <iframe title="Email preview" sandbox="" srcDoc={preview.html} className="h-[60vh] w-full rounded-md border border-border bg-white" />
            <p className="text-xs text-muted">After approval the RFQ and this email are rebuilt from your decisions, without review marks.</p>
          </div>
        )}
      </Dialog>

      <Dialog open={confirm} onClose={() => setConfirm(false)} title={canSend ? "Approve and send?" : "Approve this RFQ?"}
        footer={<>
          <Button onClick={() => setConfirm(false)}>Cancel</Button>
          <Button variant="primary" disabled={busy} onClick={approve}>{canSend ? "Approve & send" : "Approve"}</Button>
        </>}>
        <p className="text-sm">
          {canSend
            ? <>RFQ.xlsx is rebuilt from your decisions and sent to <strong>{detail.summary.sender}</strong> in the same thread. This can't be undone.</>
            : <>RFQ.xlsx and reply.eml are rebuilt from your decisions, ready to download.{!detail.mail_configured && " Mail sending is not set up."}</>}
        </p>
      </Dialog>
    </div>
  );
}
