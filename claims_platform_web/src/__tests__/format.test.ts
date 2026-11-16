import { describe, expect, it } from "vitest";
import { parseRoute } from "../App";
import { STAGES, n, pct, seconds, stageIndex } from "../format";

describe("formatting", () => {
  it("places every stage on the track in order", () => {
    expect(STAGES.map(stageIndex)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(stageIndex("Unknown")).toBe(0);
  });
  it("shows missing figures as a dash, never as zero", () => {
    expect(n(null)).toBe("–");
    expect(pct(undefined)).toBe("–");
    expect(seconds(null)).toBe("–");
    expect(n(0)).toBe("0");
  });
  it("formats rates and durations", () => {
    expect(pct(0.75)).toBe("75%");
    expect(seconds(5170)).toBe("5.2 s");
    expect(n(100000)).toBe("100,000");
  });
});

describe("routes", () => {
  it("reads client routes and falls back to the dashboard", () => {
    expect(parseRoute("#/clients/4/golive")).toEqual({ view: "client", id: 4, tab: "golive" });
    expect(parseRoute("#/clients/4")).toEqual({ view: "client", id: 4, tab: null });
    expect(parseRoute("#/nowhere")).toEqual({ view: "dashboard" });
  });
});
