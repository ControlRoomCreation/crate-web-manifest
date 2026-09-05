# AGENTS.md — Crate — Web Manifest

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

## Public repository scope

- Read `README.md` for the catalogue schema and licence-badge contract. `crate_web_manifest.json` is the public, reference-only Web directory fetched anonymously by Crate; this repository does not rehost the listed audio or contain app/website implementation.
- Preserve stable entry IDs, mirror references, and the documented licence flags. Licence badges are advisory under the existing contract. Do not infer redistribution rights, invent checksums, or add private operational notes, credentials, or customer data to this public repository.

## Validation and publication

- Run `python3 scripts/validate_manifest.py` and `python3 -m unittest discover -s scripts -p 'test_*.py' -v` for offline validation. `.github/workflows/pr-validation.yml` runs those checks on PRs and pushes to `main`.
- `scripts/health_check.py` is a separate network probe that rewrites manifest health data. The scheduled/manual `.github/workflows/health-check.yml` can also push a branch and open a PR or issue; do not run or dispatch it as an offline test.
- Changes to `main` become client-visible catalogue changes. Use a reviewed PR; obtain explicit owner approval before changing publication, repository access, workflow permissions, or external distribution. Preserve original source/licence evidence when updating an entry.
