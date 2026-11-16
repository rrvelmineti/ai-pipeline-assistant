import type { Role } from "./types";

export const STAGES = ["Setup", "Mapping", "Validation", "Remediation", "Ready for approval", "Approved", "Live"] as const;

export function stageIndex(stage: string): number {
  const i = STAGES.indexOf(stage as (typeof STAGES)[number]);
  return i < 0 ? 0 : i;
}

export function n(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : value.toLocaleString("en-US");
}

export function plural(count: number | null | undefined, one: string, many = `${one}s`): string {
  return `${n(count)} ${count === 1 ? one : many}`;
}

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${Math.round(value * 1000) / 10}%`;
}

export function seconds(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "–";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function date(value: string | null | undefined): string {
  if (!value) return "–";
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : `${value}Z`);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "–";
  return new Date(`${value}Z`).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  implementation_analyst: "Implementation analyst",
  approver: "Approver",
  client_contact: "Client data contact",
};

export const LEVEL_LABEL: Record<string, string> = {
  high: "Clear match",
  medium: "Likely match",
  low: "Weak match",
  ambiguous: "Ambiguous",
  none: "No match",
};

export const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  reopened: "Reopened",
  resolved: "Resolved",
  accepted: "Accepted",
};

export function canAnalyse(role: Role) {
  return role === "admin" || role === "implementation_analyst";
}

export function canApprove(role: Role) {
  return role === "admin" || role === "approver";
}

export function isInternal(role: Role) {
  return role !== "client_contact";
}
