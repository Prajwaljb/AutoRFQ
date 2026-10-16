import { ExternalLink } from "lucide-react";
import type { Flag, Item } from "../lib/types";
import { availability, firstUrl, money, sourceLabel } from "../lib/format";
import { screenshotUrl } from "../lib/api";
import { severityLabel, severityTone } from "../lib/status";
import { LookupBadge } from "./StatusBadge";
import { Badge, Sheet } from "./ui/primitives";
import { Button } from "./ui/button";

const COLUMNS = ["Description", "ANSI", "Application", "Color Finish", "Length", "Lettering", "Material",
  "Material Type", "No of Tools", "Temperature Range", "Thickness", "Tool Type", "UL Listed", "Width", "OSHA",
  "Waterworks Application", "Product details", "Weight", "ASTM", "Picture"];

const CONFIDENCE_TONE = { high: "success", medium: "warning", low: "danger" } as const;

function snippet(source: string): string | null {
  const m = /\(page (\d+): "([^"]+)"\)/.exec(source);
  return m ? `Page ${m[1]}: “${m[2]}”` : null;
}

export function SourceSheet({
  item,
  flags,
  onClose,
  onSubstitute,
}: {
  item: Item | null;
  flags: Flag[];
  onClose: () => void;
  onSubstitute?: (requested: string, alternative: string) => void;
}) {
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
              <Badge tone={severityTone(f.severity)}>{severityLabel(f.severity)}</Badge> <span className="font-medium">{f.column}</span>: {f.issue}
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
        <div className="space-y-3 text-sm">
          <p className="text-muted">Blank means unknown: nothing is guessed for an item we could not find.</p>
          {item.extra?.competitor && (
            <div className="rounded-md border border-border p-3">
              <h3 className="mb-2 font-semibold">What the web says about {item.brand ? `${item.brand} ` : ""}{item.product_id}</h3>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                {Object.entries(item.extra.competitor.specs).map(([name, spec]) => (
                  <div key={name} className="contents">
                    <dt className="text-muted">{name}</dt>
                    <dd>
                      {spec.value}{" "}
                      {spec.source && (
                        <a href={spec.source} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-xs text-primary underline">
                          {new URL(spec.source).hostname.replace("www.", "")} <ExternalLink size={10} aria-hidden />
                        </a>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-2 text-xs text-muted">Only pages that name this exact part are used. These specs pick the Ferguson equivalent; they are not put on the RFQ.</p>
            </div>
          )}
          {item.extra?.described_as && !item.extra?.competitor && (
            <p>
              <span className="text-muted">Described as:</span> “{item.extra.described_as}”{" "}
              <span className="text-xs text-muted">({item.extra.described_from})</span>
            </p>
          )}
          {item.extra?.alternatives?.length ? (
            <div>
              <h3 className="mb-2 font-semibold">Suggested Ferguson alternatives</h3>
              <ul className="space-y-2">
                {item.extra.alternatives.map((alt) => (
                  <li key={alt.product_id} className="rounded-md border border-border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <span className="font-mono font-semibold">{alt.product_id}</span> {alt.description}{" "}
                        {alt.confidence && (
                          <Badge tone={alt.confidence === "possible" ? "neutral" : "success"}>
                            {alt.confidence === "confirmed" ? "usual equivalent" : `${alt.confidence} match`}
                          </Badge>
                        )}
                        <p className="mt-1 text-xs text-muted">
                          Matches {alt.matched.join(", ")} · {money(alt.price) || "price on request"} · {availability(alt.availability)}
                        </p>
                      </div>
                      {onSubstitute && (
                        <Button size="sm" className="shrink-0 whitespace-nowrap" onClick={() => onSubstitute(item.product_id, alt.product_id)}>
                          Use instead
                        </Button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">Not added unless you choose one. The reply asks the customer to confirm a replacement.</p>
            </div>
          ) : (
            <p className="text-muted">No close Ferguson alternative: neither the request nor the web says what this item is (size, colour, use). The reply asks the customer.</p>
          )}
        </div>
      )}
    </Sheet>
  );
}
