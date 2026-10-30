# Learn one small step at a time

1. Run the successful browser demo. Notice the total 250.00 and rows processed 3.
2. Run the broken demo. Find line 3 and `invalid_quantity` in the evidence. Explain
   why there is no complete sales total.
3. Open `core.py`. Read only the quantity check. Change a COPY of the CSV to `three`.
   Run it from the CLI. Compare exit codes for valid and invalid input.
4. Read `storage.py`. Run success after failure. Compare latest.json with history:
   the snapshot changes, while history keeps both run IDs.
5. Read one test in `tests/test_orders.py`. Temporarily change an expected total,
   run tests, observe the failure, and restore it.
6. Read `explain.py`. Understand why an upstream cause remains unknown. Only after
   offline steps make sense, configure Gemini and try the optional classification.
7. Review `test_gemini_rejects_unproven_cause`: valid JSON is not proof of truth.
8. Make one small improvement on a new branch. Run tests, open a PR, inspect CI.

Do not study every file in one sitting. Each step is a separate lesson.
