# Contributing

Use one feature or fix branch for each focused change. Open a pull request
targeting `main`. Describe the concrete problem, resulting behavior, test
evidence, and any limitations. Link the relevant issue when one exists.

Run `python -m unittest discover -s tests -v` in the project's environment before
pushing. Add regression tests when changing calculations, validation, response
handling, or future repair logic. Keep normal CI independent of live AI calls.

Use short descriptive commit messages, for example `fix: preserve missing
nutrition values` or `feat: validate structured AI output`. Review staged changes
before committing. Never include API keys or real personal data in fixtures.

Model output is untrusted input. Keep its instructions separate from supplied
evidence. Never describe a guessed underlying cause as established fact. Missing
nutrition is not zero. Do not turn a model recommendation into an automatic
repair without a defined permission boundary, validation, and rollback design.

Follow [the Git workflow](docs/git-workflow.md). For a solo project, use PRs for
self-review and CI history; independent approval begins when another reviewer
is available.
