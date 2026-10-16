import type { Item } from "./types";

export function age(seconds: number, now = Date.now() / 1000): string {
  const s = Math.max(0, Math.round(now - seconds));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h`;
  return `${Math.round(h / 24)} d`;
}

export function ago(seconds: number, now = Date.now() / 1000): string {
  const a = age(seconds, now);
  return a === "just now" ? a : `${a} ago`;
}

export function money(value: string | number | undefined | null): string {
  const n = typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

export function availability(value: string | undefined): string {
  if (value === "InStock") return "In stock";
  if (value === "OutOfStock") return "Out of stock";
  return value || "Ask";
}

export function qtyNumber(qty: string): number | null {
  const n = Number.parseFloat(qty);
  return Number.isFinite(n) ? n : null;
}

/** Estimated value of the request: unit price × quantity where both are known. */
export function estimatedTotal(items: Item[]): number {
  let total = 0;
  for (const item of items) {
    const price = Number.parseFloat(item.extra?.["Price (USD)"] ?? "");
    const qty = qtyNumber(item.qty);
    if (item.lookup_status === "Found" && Number.isFinite(price) && qty !== null) total += price * qty;
  }
  return Math.round(total * 100) / 100;
}

export function senderLabel(name: string, address: string): string {
  return name ? `${name} <${address}>` : address;
}

export function pictureOf(item: Item): string | null {
  const url = item.cells?.Picture?.value?.split("|")[0];
  return url && url.startsWith("https://") ? url : null;
}

export function sourceLabel(sourceType: string): string {
  switch (sourceType) {
    case "ferguson_page":
      return "Live page";
    case "spec_sheet":
      return "Spec sheet";
    case "human_review":
      return "Reviewer";
    case "ferguson_rfq_sample":
      return "Ferguson sample RFQ";
    case "validated_rule":
      return "Validated rule";
    case "sibling_products":
      return "Sibling products";
    case "same_product_description":
      return "Same description";
    case "catalog":
      return "Catalog";
    default:
      return sourceType || "Unknown";
  }
}

export function firstUrl(text: string): string | null {
  const m = /https?:\/\/[^\s"')]+/.exec(text);
  return m ? m[0] : null;
}
