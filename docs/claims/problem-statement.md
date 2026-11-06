# Claims data onboarding: problem statement

## Context

A health insurer's claims platform is onboarding a new client (an employer group or a
third-party administrator). Before go-live, the client sends a historical claims extract.
The extract never matches the platform's format: column names differ, dates and amounts
use the client's own conventions, and some records are incomplete or inconsistent.

All data in this project is **synthetic**. No real member, patient or provider
information is used, and no protected health information (PHI) is stored or sent to an AI
model. In a real HIPAA setting the same workflow would run inside the insurer's approved
environment.

## Problem

Implementation analysts currently map the client's columns to the platform's fields by
hand, write one-off checks in spreadsheets, and email back and forth about errors. This is
slow, inconsistent between analysts, and makes it hard to say with confidence whether a
file is ready to load.

## Stakeholders

| Stakeholder | What they need |
| --- | --- |
| Implementation analyst | A fast, repeatable way to map columns and find every data problem |
| Client data contact | A clear list of what to fix, with row and value, not vague feedback |
| Business owner / approver | A plain-language ready or not-ready decision they can sign off on |
| Claims operations | Confidence that loaded claims will not break payment or reporting |

## Goal

Turn a raw client claims file into a go-live decision in one sitting:

1. AI suggests how the client's columns map to the platform's target fields.
2. The analyst approves or corrects each suggestion; every correction is logged.
3. Plain-language rules, editable by a business user, are checked by code, not by AI.
4. A readiness report separates go-live **blockers** from **warnings** and gives a clear
   ready or not-ready call, with an optional AI-written summary that may only use figures
   the code has verified.

## What "ready for go-live" means

A file is **ready** only when all of these hold:

- Every required target field is mapped to exactly one client column.
- The whole file was scanned (no parsing stop, no row limit hit).
- There are zero blocker findings.

Warnings do not block go-live, but they are listed for the client to review.

## Out of scope

- Loading data into a production system.
- Automatically fixing client data. The tool suggests; people decide.
- Medical coding validation beyond format checks (for example, whether a diagnosis code is
  clinically appropriate for a procedure).
