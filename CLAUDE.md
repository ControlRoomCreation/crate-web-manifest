# CLAUDE.md — Crate — Web Manifest

This repo is part of the Control Room Creations workspace and is edited from multiple machines. The multi-device git protocol below applies to every session. Project-specific guidance can be added below it.

## Multi-device work protocol (Mac Mini + MacBook Neo)

This repo is edited from two machines. **GitHub is the single source of truth.**

### Start of every session (before any edit)
1. `git fetch --all --prune`
2. `git status` — if the working tree is dirty with work you don't recognise, **STOP** and surface it (it may be stranded work from the other device).
3. `git pull --rebase` on the branch you'll work on. If behind `main`, rebase onto it.
4. State which branch you are on and that it is up to date with origin.

### During the session
- Commit in small, logical steps. WIP commits are fine.
- Never leave substantial work uncommitted at a stopping point.
- Work that isn't ready goes on a pushed branch, not a dirty local tree.

### End of every session (before stopping)
1. Commit all intended changes.
2. `git push` the branch.
3. Confirm `git status` is clean and the branch is pushed to origin.
4. If anything is intentionally left uncommitted, say so explicitly.

### Hard rules
- **Never force-push.** Never push directly to `main`; open a PR.
- **Never commit secrets.** Real mechanism: gitignored `.env` files (VPS runtime), macOS keychain, `wrangler secret put`, GitHub Actions secrets. (The old age/sops line was aspirational — no such tooling exists; verified 2026-06-10.)
- If you cannot reconcile divergent state safely, **STOP and ask** — do not guess.
