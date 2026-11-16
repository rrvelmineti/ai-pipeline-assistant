import { STAGES, stageIndex } from "../format";

// The go-live track. Stages are a true sequence, so they read left to right.
// A client held in Remediation shows its current segment in the blocker colour.
export function StageTrack({ stage, compact = false }: { stage: string; compact?: boolean }) {
  const current = stageIndex(stage);
  const held = stage === "Remediation";
  return (
    <div className={`track${compact ? " compact" : ""}`} role="img" aria-label={`Stage ${current + 1} of ${STAGES.length}: ${stage}`}>
      {STAGES.map((s, i) => (
        <div key={s} className={`seg${i < current ? " done" : ""}${i === current ? " current" : ""}${i === current && held ? " held" : ""}`}>
          <div className="bar" />
          {!compact && <div className="label">{s}</div>}
        </div>
      ))}
    </div>
  );
}
