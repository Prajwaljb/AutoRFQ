import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileUp, Mail, Play } from "lucide-react";
import { api } from "../lib/api";
import type { Health, Sample } from "../lib/types";
import { Button } from "../components/ui/button";
import { Card, ErrorBox } from "../components/ui/primitives";
import { cn } from "../components/ui/cn";

const MODES = [
  { value: "live", label: "Live", text: "ferguson.com pages through the scraping Chrome (opened and closed for you), then spec sheets, catalog as fallback." },
  { value: "no-browser", label: "No browser", text: "Spec sheet PDFs and the backup catalog. What the Azure deployment uses." },
  { value: "offline", label: "Offline", text: "Backup catalog only, no network. Repeatable: email 1 matches the reference exactly." },
];

export function NewRunPage({ health }: { health: Health | null }) {
  const [samples, setSamples] = useState<Sample[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState("offline");
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const forced = health?.forced_mode;

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);
  useEffect(() => {
    if (forced) setMode(forced);
  }, [forced]);

  async function start(sample?: string) {
    setBusy(true);
    setError("");
    const form = new FormData();
    if (sample) form.append("sample", sample);
    else if (file) form.append("file", file);
    form.append("mode", mode);
    try {
      const r = await api.start(form);
      navigate(`/runs/${encodeURIComponent(r.id)}`);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">New RFQ</h1>
        <p className="text-sm text-muted">Drop a request email (.eml) or try one of the sample emails.</p>
      </div>
      {error && <ErrorBox message={error} />}

      <fieldset className="space-y-2">
        <legend className="mb-2 text-sm font-semibold">Mode</legend>
        <div className="grid gap-2 md:grid-cols-3">
          {MODES.map((m) => {
            const disabled = !!forced && forced !== m.value;
            return (
              <label key={m.value} className={cn("cursor-pointer rounded-[var(--radius-card)] border p-3 text-sm",
                mode === m.value ? "border-accent bg-surface-2" : "border-border bg-surface", disabled && "cursor-not-allowed opacity-50")}>
                <input type="radio" name="mode" value={m.value} checked={mode === m.value} disabled={disabled}
                  onChange={() => setMode(m.value)} className="mr-2 accent-[var(--accent)]" />
                <span className="font-semibold">{m.label}</span>
                <p className="mt-1 text-muted">{m.text}</p>
              </label>
            );
          })}
        </div>
        {forced && <p className="text-xs text-muted">This server runs in {forced} mode (no browser in the cloud).</p>}
      </fieldset>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files[0];
          if (f) setFile(f);
        }}
        className={cn("flex flex-col items-center justify-center gap-3 rounded-[var(--radius-card)] border-2 border-dashed p-8 text-center",
          drag ? "border-accent bg-surface-2" : "border-border")}
      >
        <FileUp className="text-muted" aria-hidden />
        <p className="text-sm">{file ? <strong>{file.name}</strong> : "Drop an .eml file here"}</p>
        <div className="flex gap-2">
          <Button onClick={() => input.current?.click()}>Choose file</Button>
          <Button variant="primary" disabled={!file || busy} onClick={() => start()}>
            <Play size={16} aria-hidden /> Build RFQ
          </Button>
        </div>
        <input ref={input} type="file" accept=".eml,message/rfc822" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold">Sample emails</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {samples.map((s, i) => (
            <Card key={s.name} className="flex items-start gap-3 p-4">
              <Mail size={18} className="mt-0.5 shrink-0 text-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="font-medium">Email {i + 1}: {s.subject}</p>
                <p className="text-xs text-muted">{s.name}</p>
              </div>
              <Button size="sm" variant="primary" disabled={busy} onClick={() => start(s.name)}>Run</Button>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
