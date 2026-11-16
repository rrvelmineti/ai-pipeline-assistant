import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StageTrack } from "../components/StageTrack";
import { Checklist, Decision, Severity } from "../components/ui";

afterEach(cleanup);

describe("StageTrack", () => {
  it("announces the stage and marks earlier stages done", () => {
    const { container } = render(<StageTrack stage="Remediation" />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Stage 4 of 7: Remediation");
    expect(container.querySelectorAll(".seg.done")).toHaveLength(3);
    expect(container.querySelector(".seg.current.held")).not.toBeNull();
  });
  it("does not mark a client that is ready as held", () => {
    const { container } = render(<StageTrack stage="Ready for approval" compact />);
    expect(container.querySelector(".held")).toBeNull();
    expect(container.querySelectorAll(".label")).toHaveLength(0);
  });
});

describe("status chips", () => {
  it("keeps red for blockers and Not ready only", () => {
    const { container } = render(<><Severity value="blocker" /><Severity value="warning" /><Decision value="Ready" /><Decision value="Not ready" /></>);
    const tones = [...container.querySelectorAll(".chip")].map((c) => c.className.replace("chip ", ""));
    expect(tones).toEqual(["blocker", "warning", "pass", "blocker"]);
  });
  it("tells screen readers whether each check passed", () => {
    render(<Checklist checks={[{ key: "a", label: "Rules approved", ok: true }, { key: "b", label: "No open blockers", ok: false }]} />);
    expect(screen.getByText("(passed)", { exact: false })).toBeTruthy();
    expect(screen.getByText("(not yet)", { exact: false })).toBeTruthy();
  });
});
