import { useEffect, useState } from "react";
import { Bot, Globe, Inbox, Mail } from "lucide-react";
import { api } from "../lib/api";
import type { Health } from "../lib/types";
import { cn } from "./ui/cn";

function Pill({ icon, label, value, ok, title }: { icon: React.ReactNode; label: string; value: string; ok: boolean; title: string }) {
  return (
    <span title={title} className="hidden items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs md:inline-flex">
      <span className={cn("h-1.5 w-1.5 rounded-full", ok ? "bg-success" : "bg-muted")} aria-hidden />
      {icon}
      <span className="text-muted">{label}:</span>
      <span className="font-medium">{value}</span>
    </span>
  );
}

export function useHealth(intervalMs = 10000) {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => api.health().then((h) => alive && setHealth(h)).catch(() => alive && setHealth(null));
    load();
    const t = setInterval(load, intervalMs);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [intervalMs]);
  return health;
}

export function HealthBar({ health }: { health: Health | null }) {
  if (!health) return null;
  const chrome = health.forced_mode
    ? "Server mode"
    : health.chrome
      ? "Connected"
      : health.chrome_auto
        ? "Opens on demand"
        : "Offline";
  return (
    <div className="flex items-center gap-2">
      <Pill icon={<Globe size={12} aria-hidden />} label="Chrome" value={chrome} ok={health.chrome}
        title="The scraping Chrome window for live ferguson.com pages. Live runs open it and close it when done." />
      <Pill icon={<Bot size={12} aria-hidden />} label="AI review" value={health.ai ? "On" : "Off"} ok={health.ai}
        title="Azure OpenAI suggestions (advisory only)." />
      <Pill icon={<Inbox size={12} aria-hidden />} label="Inbox" value={health.inbox ? "Watching" : "Off"} ok={health.inbox}
        title="mailbot.py answering RFQ emails in the team inbox." />
      <Pill icon={<Mail size={12} aria-hidden />} label="Mail" value={health.mail ? "On" : "Off"} ok={health.mail}
        title="Sending approved replies (BOT_EMAIL / BOT_PASSWORD)." />
    </div>
  );
}
