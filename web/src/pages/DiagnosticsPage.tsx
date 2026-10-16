import { useState } from "react";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { api } from "../lib/api";
import type { Health } from "../lib/types";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/primitives";

function Row({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <div className="flex items-start gap-3 p-3 text-sm">
      {ok ? <CheckCircle2 size={16} className="mt-0.5 text-success" aria-hidden /> : <XCircle size={16} className="mt-0.5 text-muted" aria-hidden />}
      <span className="w-32 shrink-0 font-medium">{label}</span>
      <span className="text-muted">{text}</span>
    </div>
  );
}

export function DiagnosticsPage({ health }: { health: Health | null }) {
  const [check, setCheck] = useState<Awaited<ReturnType<typeof api.selfcheck>> | null>(null);
  const [running, setRunning] = useState(false);

  async function selfcheck() {
    setRunning(true);
    try {
      setCheck(await api.selfcheck());
    } catch (e) {
      setCheck({ ok: false, detail: String((e as Error).message) });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Diagnostics</h1>
        <p className="text-sm text-muted">What this server can reach, and a one-click check against the reference RFQ.</p>
      </div>
      <Card className="divide-y divide-border">
        {health ? (
          <>
            <Row label="Default mode" ok text={health.forced_mode ? `${health.forced_mode} (set by RFQ_MODE)` : health.mode} />
            <Row label="Chrome" ok={health.chrome}
              text={health.chrome ? "The scraping window is open." : health.chrome_auto ? "Closed. Live runs open it and close it when done." : "Not available on this server: catalog + spec sheets."} />
            <Row label="AI review" ok={health.ai} text={health.ai ? "Azure OpenAI is configured (advisory suggestions)." : "Off: AZURE_OPENAI_* not set. Rule flags still run."} />
            <Row label="Inbox" ok={health.inbox} text={health.inbox ? "mailbot.py is answering RFQ emails." : "mailbot.py is not running."} />
            <Row label="Mail" ok={health.mail} text={health.mail ? "Approved replies can be sent." : "BOT_EMAIL / BOT_PASSWORD not set: approve and download instead."} />
          </>
        ) : (
          <p className="p-3 text-sm text-muted">Loading…</p>
        )}
      </Card>

      <Card className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-semibold">Self-check</h2>
            <p className="text-sm text-muted">Builds email 1 offline and compares it with the reference output, cell for cell.</p>
          </div>
          <Button variant="primary" onClick={selfcheck} disabled={running}>
            {running && <Loader2 size={16} className="animate-spin" aria-hidden />} Run self-check
          </Button>
        </div>
        {check && (
          <div aria-live="polite" className={`rounded-md p-3 text-sm ${check.ok ? "bg-success-bg text-success" : "bg-danger-bg text-danger"}`}>
            {check.ok ? <CheckCircle2 size={16} className="mr-1 inline" aria-hidden /> : <XCircle size={16} className="mr-1 inline" aria-hidden />}
            {check.rows ? `${check.rows} rows, ${check.sources} sources matched.` : "Self-check failed."}
            <pre className="mt-2 whitespace-pre-wrap font-mono text-xs opacity-80">{check.detail}</pre>
          </div>
        )}
      </Card>
    </div>
  );
}
