import { useEffect, useRef, useState } from "react";
import { cn } from "./ui/cn";

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Counts up to a value (once per change). Shows the final value at once when motion is reduced. */
export function useCountUp(value: number, ms = 900): number {
  const [shown, setShown] = useState(reducedMotion() ? value : 0);
  const from = useRef(0);
  useEffect(() => {
    if (reducedMotion()) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const begin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(begin + (value - begin) * eased);
      if (t < 1) frame = requestAnimationFrame(tick);
      else from.current = value;
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, ms]);
  return shown;
}

export function CountUp({ value, decimals = 0, prefix = "", suffix = "" }: { value: number; decimals?: number; prefix?: string; suffix?: string }) {
  const shown = useCountUp(value);
  return (
    <span className="tabular">
      {prefix}
      {shown.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
      {suffix}
    </span>
  );
}

/** A ring gauge for a percentage (fill rate). */
export function FillRing({ value, size = 112, label = "fill rate" }: { value: number; size?: number; label?: string }) {
  const shown = useCountUp(value, 1100);
  const r = (size - 14) / 2;
  const c = 2 * Math.PI * r;
  const id = useRef(`ring-${Math.random().toString(36).slice(2)}`).current;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}
      role="img" aria-label={`${value}% ${label}`}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id={id} x1="0" x2="1">
            <stop offset="0%" stopColor="#00a0dd" />
            <stop offset="100%" stopColor="#5eead4" />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-2)" strokeWidth="10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${id})`} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.min(100, shown) / 100)} />
      </svg>
      <div className="absolute text-center">
        <div className="tabular text-xl font-bold">{shown.toFixed(0)}%</div>
        <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      </div>
    </div>
  );
}

const STAGES = ["Email", "Extract", "Look up", "Fill", "Quality", "Reply"];

/** The flow as an animated strip: a light runs along the line. `active` highlights a stage while processing. */
export function PipelineStrip({ active, className }: { active?: number; className?: string }) {
  return (
    <div className={cn("relative flex items-center justify-between gap-2", className)}>
      <div className="absolute left-4 right-4 top-1/2 h-px -translate-y-1/2 bg-border" aria-hidden />
      <div className="flow-line absolute left-4 right-4 top-1/2 h-0.5 -translate-y-1/2 opacity-80" aria-hidden />
      {STAGES.map((stage, i) => (
        <div key={stage} className="relative z-10 flex flex-col items-center gap-1.5">
          <span
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-full border text-xs font-bold",
              active === undefined || i < active ? "border-accent/60 bg-surface text-accent" : "border-border bg-surface text-muted",
              active === i && "pulse-ring border-accent text-accent",
            )}
          >
            {i + 1}
          </span>
          <span className="text-[11px] font-medium text-muted">{stage}</span>
        </div>
      ))}
    </div>
  );
}

/** A short confetti burst (canvas, no library). */
export function Confetti({ fire }: { fire: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!fire || reducedMotion()) return;
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const colors = ["#00a0dd", "#5eead4", "#a78bfa", "#fde68a", "#ffffff", "#00446a"];
    const parts = Array.from({ length: 160 }, () => ({
      x: canvas.width / 2 + (Math.random() - 0.5) * 200,
      y: canvas.height / 3,
      vx: (Math.random() - 0.5) * 14,
      vy: -Math.random() * 12 - 4,
      s: Math.random() * 6 + 4,
      r: Math.random() * Math.PI,
      c: colors[Math.floor(Math.random() * colors.length)],
    }));
    let frame = 0;
    let t = 0;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of parts) {
        p.vy += 0.35;
        p.x += p.vx;
        p.y += p.vy;
        p.r += 0.15;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.r);
        ctx.fillStyle = p.c;
        ctx.fillRect(-p.s / 2, -p.s / 4, p.s, p.s / 2);
        ctx.restore();
      }
      if (++t < 140) frame = requestAnimationFrame(draw);
      else ctx.clearRect(0, 0, canvas.width, canvas.height);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [fire]);
  return <canvas ref={ref} className="pointer-events-none fixed inset-0 z-[70]" aria-hidden />;
}
