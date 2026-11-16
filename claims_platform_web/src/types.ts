export type Role = "admin" | "implementation_analyst" | "approver" | "client_contact";

export interface User { id: number; username: string; display_name: string; role: Role; active: boolean; locked: boolean }

export interface Check { key: string; label: string; ok: boolean }

export interface RunSummary {
  id: number; status: string; attempts: number; error: string | null; rows_checked: number | null;
  blockers: number | null; warnings: number | null; scan_complete: boolean | null; decision: string | null;
  duration_ms: number | null; queued_at: string; finished_at: string | null; mapping_id: number; rule_set_id: number;
}

export interface ExportInfo {
  id: number; run_id: number; status: string; total_records: number; batches_total: number; batches_done: number;
  sent_records: number; skipped_duplicates: number; batch_retries: number; attempts: number; last_error: string | null;
  created_at: string; finished_at: string | null; duration_ms: number | null;
}

export interface Readiness {
  stage: string; ready_for_approval: boolean; checks: Check[]; open_blockers: number; open_warnings: number;
  rule_set_version: number | null; mapping_version: number | null; latest_submission: number | null;
  latest_run_status: string | null; run: RunSummary | null;
  approval: { id: number; decision: string; comment: string; approver_id: number; at: string } | null;
  export: ExportInfo | null;
}

export interface ClientRow {
  id: number; code: string; name: string; status: string; go_live_target: string | null; created_at: string;
  stage: string; ready_for_approval: boolean; open_blockers: number; open_warnings: number;
  latest_submission: number | null; latest_run_status: string | null; latest_decision: string | null;
  checks_passed: number; checks_total: number;
}

export interface Milestone { id: number; key: string; name: string; sort: number; due_date: string | null; status: string; completed_at: string | null }

export interface ClientDetail {
  id: number; code: string; name: string; status: string; go_live_target: string | null;
  readiness: Readiness; milestones: Milestone[];
}

export interface Submission {
  id: number; sequence: number; filename: string; sha256: string; size_bytes: number; headers: string[];
  header_error: string | null; uploaded_at: string; run?: RunSummary | null;
}

export interface Suggestion {
  field: string; description: string; required: boolean; column: string | null; source: string; reason: string;
  confidence: number | null; level: "high" | "medium" | "low" | "ambiguous" | "none"; alternatives: string[];
  needs_confirmation: boolean;
}

export interface MappingInfo {
  id: number; version: number; status: string; submission_id: number | null; headers: string[];
  suggestions: Record<string, Suggestion>; mapping: Record<string, string | null>; confirmed_fields: string[];
  corrections: { field: string; suggested_column: string | null; suggested_by: string; chosen_column: string | null }[];
  note: string; author: string | null; author_id: number | null; approver: string | null; review_comment: string;
  created_at: string; approved_at: string | null; ai_used?: boolean; ai_error?: string | null; template?: string | null;
}

export interface RuleSetInfo {
  id: number; version: number; status: string; note: string; text: string; author: string; author_id: number | null;
  approver: string | null; created_at: string; approved_at: string | null;
}

export interface ExceptionInfo {
  id: number; field: string; client_column: string; rule: string; severity: "blocker" | "warning"; status: string;
  owner_id: number | null; owner: string | null; resolution: string; first_count: number; current_count: number;
  first_submission: number; last_submission: number; created_at: string; updated_at: string; resolved_at: string | null;
}

export interface ExceptionEvent { at: string; kind: string; actor: string; detail: Record<string, unknown> }

export interface Explanation { summary: string; why_it_matters: string; how_to_fix: string; source: string; ai_text: string | null; ai_error: string | null }

export interface GroupChange { field: string; rule: string; severity: string; before: number; after: number; status: string }

export interface HistoryItem {
  submission_id: number; sequence: number; filename: string; uploaded_at: string; sha256: string; run: RunSummary | null;
  comparison: null | { fixed: GroupChange[]; new: GroupChange[]; unresolved: GroupChange[]; mapping_changed: boolean;
    same_file: boolean; previous_blockers: number; current_blockers: number };
}

export interface Communication {
  id: number; kind: string; subject: string; status: string; run_id: number | null; created_by: string | null;
  created_at: string; sent_by: string | null; sent_at: string | null; body?: string;
}

export interface Scorecard {
  submissions: number; validated_submissions: number; rounds_to_acceptance: number | null;
  first_pass_acceptance: boolean | null; rework_rate: number | null;
  blockers_by_submission: { sequence: number; blockers: number; warnings: number; decision: string }[];
  exceptions: { total: number; open: number; resolved: number; accepted: number; reopened_ever: number; median_hours_to_resolve: number | null };
  days_in_onboarding: number; milestones_done: number; milestones_total: number;
}

export interface Kpi { name: string; value: number | null; n: number; definition: string }

export interface Portfolio { clients: number; live: number; kpis: Kpi[]; validation_accuracy: string; baseline: string }

export interface Metrics {
  runs: { total: number; by_status: Record<string, number>; finished: number; retried: number;
    first_attempt_success_rate: number | null; median_ms: number | null; p95_ms: number | null; max_ms: number | null;
    rows_validated: number; rows_per_second: number | null; largest_file_rows: number | null };
  exports: { total: number; completed: number; failed: number; completion_rate: number | null; records_loaded: number;
    duplicates_skipped: number; batch_retries: number };
  recent_runs: { id: number; client: string; status: string; attempts: number; rows_checked: number | null;
    duration_ms: number | null; decision: string | null; queued_at: string }[];
}

export interface AuditRow { id: number; at: string; actor: string; action: string; entity: string; entity_id: number | null; detail: Record<string, unknown>; hash: string }
