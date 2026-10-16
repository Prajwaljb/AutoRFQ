import { useCallback, useEffect, useState } from "react";
import { Database, Loader2, RefreshCw, Search, Sprout, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import type { DbProduct, DbStats } from "../lib/types";
import { ago, availability, money } from "../lib/format";
import { Button } from "../components/ui/button";
import { Badge, Card, Dialog, EmptyState, ErrorBox, Skeleton } from "../components/ui/primitives";
import { CountUp } from "../components/fx";
import { useToast } from "../components/ui/toast";

const SOURCE = { live: "Live page", catalog: "Catalog", spec: "Spec sheet", human_review: "Reviewer" } as Record<string, string>;

function token(stats: DbStats | null): string | null {
  if (!stats?.token_required) return "";
  const saved = sessionStorage.getItem("adminToken") ?? "";
  const value = saved || (window.prompt("Admin token (ADMIN_TOKEN):") ?? "").trim();
  if (value) sessionStorage.setItem("adminToken", value);
  return value || null;
}

/** The product database: every product the flow has looked up, shared by the app, the bot and later scale-out. */
export function AdminPage() {
  const [stats, setStats] = useState<DbStats | null>(null);
  const [products, setProducts] = useState<DbProduct[] | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = useCallback((query = q) => {
    api.adminProducts(query).then((r) => {
      setStats(r.stats);
      setProducts(r.products);
      setError("");
    }).catch((e) => setError(String(e.message ?? e)));
  }, [q]);
  useEffect(() => load(""), []); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(kind: "clear" | "seed") {
    const t = token(stats);
    if (t === null) return;
    setBusy(true);
    try {
      if (kind === "clear") {
        const r = await api.adminClear(t);
        toast(`Product database cleared (${r.cleared} products removed). The next live run fetches everything again.`);
      } else {
        const r = await api.adminSeed(t);
        toast(`Loaded ${r.added} products from the backup catalog.`);
      }
      load();
    } catch (e) {
      sessionStorage.removeItem("adminToken");
      toast(String((e as Error).message), "danger");
    } finally {
      setBusy(false);
      setConfirm(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold"><Database size={20} className="text-accent" aria-hidden /> Admin · product database</h1>
          <p className="text-sm text-muted">
            Every product the flow has looked up, with its values and sources. Live runs reuse a product fetched within
            {" "}{stats?.ttl_hours ?? 24} h instead of opening ferguson.com again.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => load()} disabled={busy}><RefreshCw size={16} aria-hidden /> Refresh</Button>
          <Button onClick={() => act("seed")} disabled={busy}><Sprout size={16} aria-hidden /> Load catalog</Button>
          <Button variant="danger" onClick={() => setConfirm(true)} disabled={busy || !stats?.products}>
            <Trash2 size={16} aria-hidden /> Clear database
          </Button>
        </div>
      </div>
      {error && <ErrorBox message={`Could not load the product database: ${error}`} onRetry={() => load()} />}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Products stored", stats?.products ?? 0],
          ["From live pages", stats?.by_source?.live ?? 0],
          ["From the catalog", stats?.by_source?.catalog ?? 0],
          ["Re-used (not fetched again)", stats?.reused ?? 0],
        ].map(([label, value]) => (
          <Card key={label as string} className="lift p-4">
            <div className="text-2xl font-bold text-gradient"><CountUp value={value as number} /></div>
            <div className="mt-1 text-xs font-semibold uppercase tracking-wide text-muted">{label}</div>
          </Card>
        ))}
      </div>

      <Card className="p-4">
        <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); load(q); }}>
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3 top-3 text-muted" aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by item number or description"
              className="h-10 w-full rounded-md border border-border bg-surface pl-9 pr-3 text-sm" aria-label="Search products" />
          </div>
          <Button type="submit">Search</Button>
        </form>
        {products === null ? (
          <Skeleton className="h-40 w-full" />
        ) : products.length === 0 ? (
          <EmptyState icon={<Database size={28} />} title="The product database is empty">
            Run an RFQ (live or no-browser) or click Load catalog. Products appear here as they are looked up.
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-3 py-2">Item</th><th className="px-3 py-2">Description</th><th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2 text-right">Price</th><th className="px-3 py-2">Stock</th>
                  <th className="px-3 py-2 text-right">Values</th><th className="px-3 py-2">Fetched</th><th className="px-3 py-2 text-right">Re-used</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {products.map((p) => (
                  <tr key={p.product_id} className="hover:bg-surface-2">
                    <td className="px-3 py-2 font-mono">{p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="hover:underline">{p.product_id}</a> : p.product_id}</td>
                    <td className="max-w-md px-3 py-2"><span className="line-clamp-1">{p.description}</span></td>
                    <td className="px-3 py-2"><Badge tone={p.source === "live" ? "success" : "info"}>{SOURCE[p.source] ?? p.source}</Badge></td>
                    <td className="tabular px-3 py-2 text-right">{money(p.price)}</td>
                    <td className="px-3 py-2">{availability(p.availability)}</td>
                    <td className="tabular px-3 py-2 text-right">{p.cells}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-muted">{ago(p.fetched_at)}</td>
                    <td className="tabular px-3 py-2 text-right">{p.hits}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {stats && <p className="mt-3 text-xs text-muted">Stored in <code className="font-mono">{stats.path}</code> (SQLite). For more scale, the same functions can sit on a server database.</p>}
      </Card>

      <Dialog open={confirm} onClose={() => setConfirm(false)} title="Clear the product database?"
        footer={<>
          <Button onClick={() => setConfirm(false)}>Cancel</Button>
          <Button variant="danger" disabled={busy} onClick={() => act("clear")}>
            {busy && <Loader2 size={16} className="animate-spin" aria-hidden />} Clear {stats?.products} products
          </Button>
        </>}>
        <p className="text-sm">All stored products are removed. RFQs already built keep their Excel files. The next live run looks every item up again: use this to simulate a first run.</p>
      </Dialog>
    </div>
  );
}
