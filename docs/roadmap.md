# Next development steps

## Baseline: v0.1.0

- Deterministic calculation and input validation.
- Evidence records with original inputs, status, stage, total, and error.
- Gemini explanation of the fixed missing-nutrition example.
- Standalone JSON syntax exercise using a sample string.
- Offline tests and a GitHub Actions workflow definition.

The model currently explains a known validation error. It does not independently
detect arbitrary pipeline failures or automatically fix anything.

## Next feature: structured explanations

Branch: `feature/structured-ai-output`.

Request `stage`, `problem`, `underlying_cause`, and `next_check` as structured
model output. Validate its schema separately from checking evidence support.

Acceptance checks:

- Valid JSON alone does not cause acceptance of the content.
- Missing fields, incorrect types, and unsupported stage values are rejected.
- For the known missing-nutrition fixture, the stage must be validation and
  the underlying cause must remain unknown (`null`).
- A fabricated outage or nutrition value is rejected in an evaluation fixture.
- Invalid model output leaves the original evidence unchanged and produces a
  clear diagnostic.
- Offline tests run in CI without credentials; live evaluation is deliberate.

Free-text factual support will need a defined evaluation method; parsing and
schema validation do not establish truth. This feature is planned, not included
in the baseline.

## Later milestones

1. Accept records from multiple synthetic pipeline scenarios and evaluate
   explanations against known expected outcomes.
2. Propose explicit repairs, showing the evidence and proposed changes for review.
3. Add a limited set of approved deterministic repairs with tests, before/after
   records, rollback behavior, and an audit trail. Never invent missing nutrition.
4. Add a service interface, then choose hosting and a deployment process.

Track each change in a GitHub issue, then implement it in a focused PR. Keep
planned capabilities separate from what the current code actually does.
