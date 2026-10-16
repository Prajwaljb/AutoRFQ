import { describe, expect, it } from "vitest";
import { sortFlags, sortRuns, tabOf } from "./sort";
import { statusInfo } from "./status";
import { estimatedTotal } from "./format";
import type { Flag, Item, RunSummary } from "./types";

const run = (id: string, status: RunSummary["status"], updated: number) =>
  ({ id, status, updated }) as RunSummary;

describe("sortRuns", () => {
  it("puts needs review first, oldest waiting first, then newest first", () => {
    const sorted = sortRuns([run("a", "ready", 5), run("b", "needs_review", 9), run("c", "needs_review", 2),
      run("d", "sent", 7)]);
    expect(sorted.map((r) => r.id)).toEqual(["c", "b", "d", "a"]);
  });
});

describe("sortFlags", () => {
  it("groups by item in email order, then by severity", () => {
    const f = (product_id: string, severity: Flag["severity"], column = "Width") =>
      ({ product_id, severity, column }) as Flag;
    const sorted = sortFlags([f("2", "medium"), f("1", "medium"), f("2", "high"), f("1", "high", "Length")],
      ["1", "2"]);
    expect(sorted.map((x) => `${x.product_id}:${x.severity}`)).toEqual(["1:high", "1:medium", "2:high", "2:medium"]);
  });
});

describe("status mapping", () => {
  it("has a label and an icon for every status", () => {
    for (const s of ["processing", "ready", "needs_review", "approved", "sent", "failed", "fallback_sent"]) {
      const info = statusInfo(s);
      expect(info.label).not.toBe(s === "ready" ? "" : s);
      expect(info.icon).toBeTruthy();
    }
    expect(tabOf("approved")).toBe("ready");
    expect(tabOf("fallback_sent")).toBe("failed");
  });
});

describe("estimatedTotal", () => {
  it("adds price × qty for found items only", () => {
    const item = (price: string, qty: string, found = true) =>
      ({ lookup_status: found ? "Found" : "Not found", qty, extra: { "Price (USD)": price } }) as unknown as Item;
    expect(estimatedTotal([item("10.5", "4 rolls"), item("3", ""), item("99", "2", false)])).toBe(42);
  });
});
