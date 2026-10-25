# Working with Git and GitHub

This project uses GitHub flow. Organizations choose different workflows; there
is no single mandatory industry layout. Short feature branches, automated tests,
pull requests, and a stable main branch fit this project's current size.

## First repository setup

Use `ai-pipeline-assistant` as the working name and Private as the initial
visibility. The owner may rename it later. Create the initial baseline commit
and push it to `main`; subsequent feature work goes through pull requests.

After the first CI run, configure main-branch protections where the account plan
supports them: require a pull request, require all three Python test checks,
resolve review conversations, and block force pushes and branch deletion.
These settings are not enabled merely by adding files to a repository.

For solo work, review the diff and checks yourself without requiring another
approver. When a collaborator joins, require one independent approval.
GitHub does not allow authors to approve their own pull requests.

GitHub Free supports protected branches in public repositories; private-repo
protection depends on the plan. Keep the repository private unless the owner
chooses to publish it. If enforcement is unavailable, follow the same PR and
test process manually. Do not claim it is enforced.

Use squash merges for small feature PRs and automatically delete merged feature
branches if those settings are available. Tag a tested milestone `v0.1.0` only
after the baseline is committed and its checks pass.

## Start on a new computer

Install Git and Python. Sign in to GitHub using Git Credential Manager, GitHub
Desktop, or GitHub CLI. Copy the repository's actual HTTPS URL from GitHub's Code
menu. In PowerShell, this reads the URL without requiring edits to a template:

```powershell
$repoUrl = Read-Host "Paste this repository's HTTPS clone URL"
git clone $repoUrl ai-pipeline-assistant
Set-Location ai-pipeline-assistant
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Clone once per working location. If the folder already contains the repository,
open that folder and pull instead. Configure Git's author name and email using
your own GitHub identity before making commits; a GitHub-provided no-reply email
can keep your personal email out of commits.

## One change from start to merge

First check that your working tree is clean. Commit or deliberately set aside
unfinished changes before switching branches.

```powershell
git status
git switch main
git pull --ff-only origin main
git switch -c feature/structured-ai-output
```

Implement the agreed change and its regression tests. The branch name above is
for our next planned feature; use a new descriptive name for each later task.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git diff
git status
git add -p
```

`git add -p` stages selected changes to tracked files. Stage each intended new
file explicitly with `git add` followed by its path. Check what will be committed:

```powershell
git diff --cached
git commit -m "feat: validate structured AI explanations"
git push -u origin feature/structured-ai-output
```

Open a pull request targeting `main` in GitHub. Explain the problem, the change,
and how it was tested. Read the Files changed tab and the Actions results. Fix
failed checks on the same branch and push again. Merge only when the checks pass
and the review is complete. Then update the local baseline:

```powershell
git switch main
git pull --ff-only origin main
```

Delete the merged remote branch through GitHub. After a squash merge, local
`git branch -d` may refuse deletion because the commit IDs differ. Verify the PR
is merged and no unique work remains before deciding to force-delete a local
branch; never delete it simply to make an error disappear.

## Conflicts and undoing a change

If a branch has conflicts, fetch the latest main and merge it into the feature
branch. Resolve each conflict deliberately, run tests, and push the resolution.
If `git pull --ff-only` fails, inspect the divergence rather than force-pushing.

Use a new PR with `git revert` to undo a merged change while preserving shared
history. Do not reset or force-push main as a routine rollback method.

## What the words mean

| Term | Meaning in this project |
| --- | --- |
| Clone | Download a repository and its Git history for the first time. |
| Pull | Bring committed remote changes into the local branch. |
| Commit | Record a named snapshot in local Git history. |
| Push | Upload local commits to GitHub. |
| Pull request | Propose and review merging a branch into main. |
| CI | Run the test suite automatically on GitHub. |
| Release tag | Name a particular tested commit. |
| Deployment | Install and run a version in a hosting environment. |

Pushing this Python project to GitHub stores and versions its source. It does
not start a persistent Python service. GitHub Pages does not provide a runtime
for this Python backend. Hosting and deployment automation are later work.

## Official guidance

- https://docs.github.com/en/get-started/using-github/github-flow
- https://docs.github.com/en/actions/tutorials/build-and-test-code/python
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/about-pull-request-reviews
