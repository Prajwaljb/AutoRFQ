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
  const [mail, setMail] = useState<{ ok: boolean; detail: string } | null>(null);
  const [mailBusy, setMailBusy] = useState(false);

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
            <Row label="Chrome" ok={health.chrome || health.chrome_auto}
              text={health.chrome ? "The scraping window is open." : health.chrome_auto ? "Closed. Live runs open it and close it when done." : "Not available on this server: catalog + spec sheets."} />
            <Row label="LLM check" ok={health.ai} text={health.ai ? "OpenAI / Azure OpenAI key set: the model looks for odd values (advisory)." : "Off: set OPENAI_API_KEY (or AZURE_OPENAI_*) in .env. Units, blanks and rule flags still run."} />
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
            <h2 className="font-semibold">Mail login</h2>
            <p className="text-sm text-muted">Signs in to the team inbox and the mail server with BOT_EMAIL / BOT_PASSWORD. Nothing is sent.</p>
          </div>
          <Button onClick={async () => { setMailBusy(true); try { setMail(await api.mailTest()); } catch (e) { setMail({ ok: false, detail: String((e as Error).message) }); } finally { setMailBusy(false); } }} disabled={mailBusy}>
            {mailBusy && <Loader2 size={16} className="animate-spin" aria-hidden />} Test mail login
          </Button>
        </div>
        {mail && (
          <div aria-live="polite" className={`rounded-md p-3 text-sm ${mail.ok ? "bg-success-bg text-success" : "bg-danger-bg text-danger"}`}>
            {mail.ok ? "Mail login works: the bot can read the inbox and send replies." : mail.detail}
          </div>
        )}
      </Card>

      {health?.settings && (
        <Card className="p-4">
          <h2 className="font-semibold">Settings (.env)</h2>
          <p className="mb-3 text-sm text-muted">
            Which keys have a value. Values are never shown. Edit <code className="font-mono">.env</code> in the repo root (template:{" "}
            <code className="font-mono">.env.example</code>), then restart the app.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {Object.entries(health.settings).map(([group, keys]) => (
              <div key={group} className="rounded-md border border-border p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{group}</p>
                <ul className="space-y-1 text-sm">
                  {Object.entries(keys).map(([name, set]) => (
                    <li key={name} className="flex items-center gap-2">
                      {set ? <CheckCircle2 size={14} className="text-success" aria-hidden /> : <XCircle size={14} className="text-muted" aria-hidden />}
                      <code className="font-mono text-xs">{name}</code>
                      <span className="text-xs text-muted">{set ? "set" : "not set"}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>
      )}

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
