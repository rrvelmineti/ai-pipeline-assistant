# Git workflow

This repository uses short-lived branches and pull requests. Start with a clean
working tree; commit or deliberately stash local changes before switching branches.

```powershell
git status
git switch main
git pull --ff-only origin main
git switch -c feature/your-change
```

Make the change, run the README checks, review `git diff`, and stage intended files.
Commit and push your branch. Open a pull request, inspect the diff and CI, and merge
when review is complete. Pull main again afterward. Never force-push to solve a
conflict without understanding which work would be lost.

If you still have the laptop's `chore/orders-cleanup` work, preserve it before
switching to this version. The v1 branch includes the cleanup, so compare rather
than copying old files over the new package.

A GitHub repository stores source and history. It does not host a running Python
service. Use the README's local Streamlit command to launch the demo.
