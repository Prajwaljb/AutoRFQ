import { ExternalLink } from "lucide-react";
import type { Flag, Item } from "../lib/types";
import { availability, firstUrl, money, sourceLabel } from "../lib/format";
import { screenshotUrl } from "../lib/api";
import { severityTone } from "../lib/status";
import { LookupBadge } from "./StatusBadge";
import { Badge, Sheet } from "./ui/primitives";

const COLUMNS = ["Description", "ANSI", "Application", "Color Finish", "Length", "Lettering", "Material",
  "Material Type", "No of Tools", "Temperature Range", "Thickness", "Tool Type", "UL Listed", "Width", "OSHA",
  "Waterworks Application", "Product details", "Weight", "ASTM", "Picture"];

const CONFIDENCE_TONE = { high: "success", medium: "warning", low: "danger" } as const;

function snippet(source: string): string | null {
  const m = /\(page (\d+): "([^"]+)"\)/.exec(source);
  return m ? `Page ${m[1]}: “${m[2]}”` : null;
}

export function SourceSheet({ item, flags, onClose }: { item: Item | null; flags: Flag[]; onClose: () => void }) {
  if (!item) return null;
  const found = item.lookup_status === "Found";
  return (
    <Sheet
      open
      onClose={onClose}
      title={
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-lg font-semibold">{item.product_id}</span>
            <LookupBadge found={found} />
          </div>
          <p className="mt-1 text-sm text-muted">{item.description || item.reason}</p>
        </div>
      }
    >
      {item.found_via === "live" && (
        <a href={screenshotUrl(item.product_id)} target="_blank" rel="noreferrer" className="mb-4 block overflow-hidden rounded-md border border-border">
          <img src={screenshotUrl(item.product_id)} alt={`ferguson.com page for ${item.product_id}`} className="w-full"
            onError={(e) => ((e.currentTarget.parentElement as HTMLElement).style.display = "none")} />
        </a>
      )}
      {found && (
        <dl className="mb-4 grid grid-cols-3 gap-2 text-sm">
          <div><dt className="text-muted">Price</dt><dd className="tabular font-medium">{money(item.extra?.["Price (USD)"]) || "—"}</dd></div>
          <div><dt className="text-muted">Availability</dt><dd className="font-medium">{availability(item.extra?.Availability)}</dd></div>
          <div><dt className="text-muted">Quantity</dt><dd className="tabular font-medium">{item.qty || "—"}</dd></div>
        </dl>
      )}
      {flags.length > 0 && (
        <div className="mb-4 space-y-2">
          {flags.map((f) => (
            <div key={f.id} className="rounded-md border border-border bg-surface-2 p-2 text-sm">
              <Badge tone={severityTone(f.severity)}>{f.severity}</Badge> <span className="font-medium">{f.column}</span>: {f.issue}
            </div>
          ))}
        </div>
      )}
      {found ? (
        <ul className="divide-y divide-border">
          {COLUMNS.map((column) => {
            const cell = item.cells[column];
            const url = cell ? firstUrl(cell.source) : null;
            const snip = cell ? snippet(cell.source) : null;
            return (
              <li key={column} className="py-2.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted">{column}</span>
                  {cell && (
                    <span className="flex items-center gap-1">
                      <Badge tone="info">{sourceLabel(cell.source_type)}</Badge>
                      <Badge tone={CONFIDENCE_TONE[cell.confidence as keyof typeof CONFIDENCE_TONE] ?? "neutral"}>{cell.confidence}</Badge>
                    </span>
                  )}
                </div>
                <p className="mt-1 break-words text-sm">{cell ? cell.value.split("|").join(" · ") : <span className="text-muted">Blank (unknown)</span>}</p>
                {cell && column !== "Description" && (
                  <p className="mt-1 break-words text-xs text-muted">
                    {snip ?? cell.source.replace(/\s*\(page.*$/, "")}{" "}
                    {url && (
                      <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-primary underline">
                        open <ExternalLink size={11} aria-hidden />
                      </a>
                    )}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-sm text-muted">Blank means unknown: nothing is guessed for an item we could not find.</p>
      )}
    </Sheet>
  );
}
