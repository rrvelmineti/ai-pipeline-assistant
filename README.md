# AI Pipeline Assistant

A Python learning project that validates a small calorie calculation pipeline,
records what happened, and asks Gemini to explain an error using that record.

This is the v0.1.0 baseline. The application detects predefined input problems
and explains them. It does not automatically repair data or code, monitor
production pipelines, or discover unknown root causes.

## What works now

| Component | Current behavior |
| --- | --- |
| `calorie_pipeline.py` | Validates inputs, calculates calories, and returns an evidence record. |
| `explain_calorie_error.py` | Sends the missing-nutrition example to Gemini and prints an explanation. |
| `check_response.py` | Parses a fixed sample JSON response; it does not call Gemini. |
| `tests/` | Checks calculations, invalid inputs, model-response handling, and key-input safeguards without live API calls. |
| `.github/workflows/ci.yml` | Defines automated tests for pushes and pull requests. It runs after upload to GitHub if Actions is enabled. |

The first two scripts are preserved from the working lessons. The JSON exercise
is copied from the completed lesson and includes a short explanatory docstring.
Repository documentation, tests, and CI configuration are new in this package.

## Run on Windows PowerShell

Install Python 3.10 or newer. Open PowerShell in this project folder.
Create a local environment; using its Python executable directly avoids needing
to change PowerShell's execution policy.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe calorie_pipeline.py
.\.venv\Scripts\python.exe check_response.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS or Linux, use `.venv/bin/python` instead of
`.\.venv\Scripts\python.exe` after creating the environment with `python3`.

The calculation and JSON exercises use only Python's standard library and can
also run before installing the Gemini dependencies.

### Expected calculation results

All values are synthetic test inputs, not measured food nutrition.

| Input | Expected result |
| --- | --- |
| 250 g, 200 calories per 100 g | 500 calories |
| 250 g, nutrition unavailable | Error at validation; total remains `null` |
| 500 g, 200 calories per 100 g | 1,000 calories |

The formula is `portion_grams / 100 * calories_per_100g`. A missing value stays
missing; zero is accepted as a real numeric input.

## Run the Gemini explanation

```powershell
.\.venv\Scripts\python.exe explain_calorie_error.py
```

The existing lesson asks you to check the Google AI Studio project associated
with your key and type `FREE` if the project is marked Free. The script cannot
verify billing or available quota. Availability and limits depend on the project
and may change; check [Google's current pricing](https://ai.google.dev/gemini-api/docs/pricing).

It reads `GEMINI_API_KEY` from the terminal environment if present. Otherwise,
it asks for the key through hidden terminal input and does not save it. Paste
once and press Enter; no characters or dots appear. Never put the key in a
Python file, commit, screenshot, issue, or pull request. This project does not
automatically load `.env` files.

The configured model is `gemini-3.5-flash-lite`. The script attempts one
generation request and sends only the synthetic evidence record and explanatory
instructions. It does not modify the original record. Review each model answer
against the evidence: a completed response is not proof of factual accuracy.

The author previously reported a successful Gemini run. Automated tests in this
repository use simulated responses; they do not establish current API access,
quota, billing status, or model-answer accuracy.

## How to develop from here

Use GitHub as the shared source of truth. Clone once, pull the latest `main`,
create a feature branch, make and test a focused change, push the branch, open a
pull request, review it, and merge after checks pass.

See [the working guide](docs/git-workflow.md) for PowerShell commands, repository
settings, and the difference between pushing code and deploying an application.
See [the roadmap](docs/roadmap.md) for the next feature and its acceptance checks.

CI covers Linux with Python 3.10 and 3.12, plus Windows with Python 3.12. No Gemini
key is required in GitHub Actions. Direct dependency versions are pinned in
`requirements.txt`; a full transitive lockfile is not yet maintained.

## Project files

| Location | Purpose |
| --- | --- |
| `requirements.txt` | Runtime dependencies |
| `tests/test_pipeline.py` | Calculation and input-validation regression tests |
| `tests/test_explanation.py` | Offline Gemini response and CLI tests |
| `tests/test_json_exercise.py` | JSON exercise output check |
| `docs/git-workflow.md` | Everyday Git workflow and repository setup |
| `docs/roadmap.md` | Planned features and limits |
| `CONTRIBUTING.md` | Change and review expectations |
| `CHANGELOG.md` | Version notes |
| `.github/pull_request_template.md` | Review prompts |

## References

- [GitHub flow](https://docs.github.com/en/get-started/using-github/github-flow)
- [Building and testing Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
- [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Gemini model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
- [Gemini API reference](https://ai.google.dev/api/generate-content)

No open-source license has been selected for this baseline.
