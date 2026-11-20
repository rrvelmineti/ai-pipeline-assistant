import { describe, expect, it } from "vitest";
import { glyph, posterStyle } from "../components/Poster";
import { pickFeatured } from "../screens/Dashboard";
import type { ClientRow } from "../types";

function row(id: number, stage: string, open_blockers = 0): ClientRow {
  return {
    id, code: `C${id}`, name: `Client ${id}`, status: "active", go_live_target: null, created_at: "2026-11-01",
    stage, ready_for_approval: stage === "Ready for approval", open_blockers, open_warnings: 0,
    latest_submission: null, latest_run_status: null, latest_decision: null, checks_passed: 0, checks_total: 8,
  };
}

describe("billboard", () => {
  it("features the client with the most open blockers first", () => {
    expect(pickFeatured([row(1, "Live"), row(2, "Remediation", 3), row(3, "Remediation", 12)])?.id).toBe(3);
  });
  it("then a client waiting for approval, then one still in progress", () => {
    expect(pickFeatured([row(1, "Live"), row(2, "Mapping"), row(3, "Ready for approval")])?.id).toBe(3);
    expect(pickFeatured([row(1, "Live"), row(2, "Mapping")])?.id).toBe(2);
    expect(pickFeatured([row(1, "Live")])?.id).toBe(1);
    expect(pickFeatured([])).toBeNull();
  });
});

describe("poster art", () => {
  it("is the same for the same client and differs between clients", () => {
    expect(posterStyle("B-BIRCH")).toEqual(posterStyle("B-BIRCH"));
    expect(posterStyle("B-BIRCH")).not.toEqual(posterStyle("C-CEDAR"));
  });
  it("shows the client code's prefix", () => {
    expect(glyph("B-BIRCH")).toBe("B");
    expect(glyph("C2-CEDAR-WEST")).toBe("C2");
  });
});
