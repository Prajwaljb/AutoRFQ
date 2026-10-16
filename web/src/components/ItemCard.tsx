import { Flag as FlagIcon, ImageOff } from "lucide-react";
import type { Item } from "../lib/types";
import { availability, money, pictureOf } from "../lib/format";
import { LookupBadge } from "./StatusBadge";
import { Badge, Card, Skeleton } from "./ui/primitives";
import { cn } from "./ui/cn";

const VIA: Record<string, string> = { live: "Live page", spec: "Spec sheet", catalog: "Catalog" };

export function ItemCard({ item, flags, onOpen }: { item: Item; flags: number; onOpen: () => void }) {
  const found = item.lookup_status === "Found";
  const picture = pictureOf(item);
  const price = item.extra?.["Price (USD)"];
  return (
    <button onClick={onOpen} className="text-left" aria-label={`Open ${item.product_id}`}>
      <Card className={cn("flex h-full flex-col overflow-hidden transition-colors duration-150 hover:border-accent", !found && "opacity-80")}>
        <div className="flex h-36 items-center justify-center bg-white">
          {picture ? (
            <img src={picture} alt="" loading="lazy" className="h-full w-full object-contain p-2" />
          ) : (
            <ImageOff className="text-slate-400" aria-hidden />
          )}
        </div>
        <div className="flex flex-1 flex-col gap-2 p-3">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-sm font-semibold">{item.product_id}</span>
            <LookupBadge found={found} />
          </div>
          {found ? (
            <>
              <p className="line-clamp-2 min-h-10 text-sm">{item.description || item.cells?.Description?.value}</p>
              <div className="mt-auto flex flex-wrap items-center gap-2 text-xs text-muted">
                <Badge tone="info">{VIA[item.found_via] ?? "Catalog"}</Badge>
                <span className="tabular">{price ? money(price) : "Price on request"}</span>
                <span aria-hidden>·</span>
                <span>{availability(item.extra?.Availability)}</span>
                {item.qty && (
                  <>
                    <span aria-hidden>·</span>
                    <span className="tabular">Qty {item.qty}</span>
                  </>
                )}
                {flags > 0 && (
                  <Badge tone="warning" className="ml-auto">
                    <FlagIcon size={11} aria-hidden /> {flags}
                  </Badge>
                )}
              </div>
            </>
          ) : (
            <>
              <p className="text-sm text-muted">{item.reason || "Not found in any source."}</p>
              <p className="mt-auto text-xs text-muted">
                {item.kind === "code" ? "Next step: ask for the Ferguson item number or suggest an equivalent." : "Next step: check the number with the customer."}
              </p>
            </>
          )}
        </div>
      </Card>
    </button>
  );
}

export function ItemCardSkeleton() {
  return (
    <Card className="overflow-hidden">
      <Skeleton className="h-36 rounded-none" />
      <div className="space-y-2 p-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </Card>
  );
}
