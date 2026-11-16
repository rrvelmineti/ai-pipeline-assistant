# Demo script (about 12 minutes)

Set up once: build the interface, then `python -m claims_platform.cli seed-demo` with
`CLAIMS_DEMO_PASSWORD` set, and `python -m claims_platform.cli serve`. The seed runs scenarios A–F,
so every stage of the journey is on screen. All data is synthetic.

## 1. The portfolio (1 minute), signed in as `priya` (approver)

- The dashboard shows seven synthetic clients on the go-live track: Live, Approved, Ready for
  approval, Remediation (in red), Mapping and Setup.
- Point out the measures: each shows how many clients or files it is based on, and the note that no
  saving is claimed without a baseline.

## 2. A file that is not ready (3 minutes): Birch Mutual

- **Validation and exceptions:** 2,000 rows checked, 42 blockers, 10 warnings. These are the 52
  errors planted in the synthetic file, all found at the right line, with no false alarms.
- Open the **Rendering NPI** exception: what it means, why it matters, how the client fixes it. Show
  the history, including the client contact's note.
- Try to accept it: blockers cannot be waived.
- **Go-live and reporting:** the checklist shows what is missing; approval is not possible.
- **Resubmissions:** open the released issue letter. It uses the client's column names.

## 3. A new layout (3 minutes): Cedar Benefits, then Cedar West

- **Data mapping** on Cedar Benefits: version 1 was corrected by the analyst. Name matching picked
  "Billing Provider NPI"; the analyst chose "Servicing Provider NPI", and the correction is logged.
- **Onboarding rules:** version 2 accepts US-format dates; it was proposed by Ana with a reason and
  approved by Priya. The audit trail shows both.
- Cedar West has the same layout: its mapping started from the saved template, every field a clear
  match, still waiting for the analyst to send it.

## 4. Resubmissions (2 minutes): Dogwood Health

- **Resubmissions:** four files. File 2 fixed two problems and introduced two new ones; file 3 brought
  the NPI problem back, which reopened it; file 4 was clean.
- **Go-live and reporting:** scorecard says 4 files until accepted, first file not accepted, 75% sent
  back, all from the records.

## 5. Things going wrong (2 minutes): Elm Street Cooperative

- **Validation and exceptions > All:** the truncated and the corrupt file created exceptions that
  resolved only when the full file was re-sent.
- **Go-live and reporting:** the export shows batch retries. A simulated outage stopped it after
  batch 1; the resumed export lost an acknowledgement on purpose and still loaded each of the 1,500
  claims exactly once.
- Download the **evidence package** and open `manifest.json`: every file's SHA-256.

## 6. Who can see what (1 minute)

Sign out and sign in as `birch.contact`: one client only, no mapping or go-live screens, released
letters only, notes allowed. As `sam`, Aster Health Plan does not exist.

## Questions people ask

- **Is it HIPAA-compliant?** No. It is a pilot on synthetic data; the security assessment lists what
  real data would need first.
- **What does AI do?** It can suggest mappings from column headings and reword explanations. It
  never decides: anything uncertain needs a person, and every check is code.
- **What is the saving?** Not known yet. The business case describes how to measure the manual
  baseline before claiming one.
