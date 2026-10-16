import { Check, Loader2 } from "lucide-react";
import type { PipelineEvent } from "../lib/types";
import { cn } from "./ui/cn";

const STEPS = [
  { key: "read", label: "Read", done: ["email_read"] },
  { key: "lookup", label: "Look up", done: ["excel_saved"], active: ["lookup_start", "item_found"] },
  { key: "fill", label: "Fill", done: ["excel_saved"] },
  { key: "quality", label: "Quality", done: ["excel_saved"], active: ["quality_flag"] },
  { key: "reply", label: "Reply", done: ["reply_saved", "run_done"] },
];

export function stepState(events: PipelineEvent[]): number {
  const types = new Set(events.map((e) => e.type));
  if (types.has("run_done")) return STEPS.length;
  if (types.has("reply_saved")) return 4;
  if (types.has("excel_saved")) return 4;
  if (types.has("quality_flag")) return 3;
  if (types.has("lookup_start") || types.has("lookup_done") || types.has("spec_pdf_read")) return 1;
  if (types.has("email_read")) return 1;
  return 0;
}

export function PipelineSteps({ events }: { events: PipelineEvent[] }) {
  const current = stepState(events);
  const looked = events.filter((e) => e.type === "lookup_done").length;
  const items = events.filter((e) => e.type === "item_found" && e.kind !== "code").length;
  return (
    <ol className="flex flex-wrap items-center gap-2" aria-live="polite">
      {STEPS.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={step.key} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-7 items-center gap-1.5 rounded-full border px-3 text-xs font-medium",
                done && "border-success/40 bg-success-bg text-success",
                active && "border-accent text-text",
                !done && !active && "border-border text-muted",
              )}
            >
              {done ? <Check size={12} aria-hidden /> : active ? <Loader2 size={12} className="animate-spin" aria-hidden /> : null}
              {step.label}
              {step.key === "lookup" && active && items > 0 && <span className="tabular text-muted">{looked}/{items}</span>}
            </span>
            {i < STEPS.length - 1 && <span className="h-px w-4 bg-border" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
