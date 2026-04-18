#!/usr/bin/env bash
#
# One-shot setup: create the GitHub repo for ControlRoomCreation/crate-web-manifest
# and push this local repo to it.
#
# Prerequisites:
#   - Your existing SSH alias "github.com-controlroom" works for ControlRoomCreation
#     (already proven — that's how you push to ControlRoomCreation/crate).
#   - Either:
#       (a) `gh` CLI installed and authenticated against ControlRoomCreation, OR
#       (b) You create the empty repo yourself at https://github.com/organizations/ControlRoomCreation/repositories/new
#           (repo name: crate-web-manifest, visibility: Public recommended,
#            do NOT add a README/licence/gitignore — this local repo already has them).
#
# Usage:
#   cd /Users/ednet/Documents/CrateMaster/crate-web-manifest-repo
#   bash SETUP.sh
#

set -euo pipefail

ORG="ControlRoomCreation"
REPO="crate-web-manifest"
VISIBILITY="private"   # PRE-LAUNCH: private. Flip to public on launch day —
                       # the iOS/macOS Crate client fetches via
                       # raw.githubusercontent.com unauthenticated, so the repo
                       # MUST be public before the first shipped build that
                       # reads the manifest.

# Sanity: run from the repo dir
if [ ! -f "crate_web_manifest.json" ]; then
  echo "ERROR: run this from inside the crate-web-manifest-repo directory." >&2
  exit 1
fi

echo "→ Target: $ORG/$REPO ($VISIBILITY)"
echo

if command -v gh >/dev/null 2>&1; then
  echo "→ gh CLI detected — creating repo and pushing in one step."
  # --source=. picks up the existing remote; --push pushes main.
  # If the repo already exists, gh will say so — then fall through to plain push.
  if gh repo view "$ORG/$REPO" >/dev/null 2>&1; then
    echo "  (repo already exists on GitHub — skipping create)"
  else
    gh repo create "$ORG/$REPO" \
      --"$VISIBILITY" \
      --description "Crate Web directory manifest + health-check automation. Reference-only catalogue of royalty-free SFX sources consumed by the Crate iOS/macOS app." \
      --disable-wiki \
      --source="." \
      --remote=origin \
      --push
    echo
    echo "✓ Repo created and main pushed."
  fi

  # If gh repo create didn't push (because repo already existed), push now.
  if ! git ls-remote --heads origin main | grep -q .; then
    echo "→ Pushing main..."
    git push -u origin main
  fi

else
  echo "→ gh CLI not installed."
  echo "  1. Create the empty repo here:"
  echo "       https://github.com/organizations/$ORG/repositories/new"
  echo "     Name: $REPO"
  echo "     Visibility: $VISIBILITY"
  echo "     DO NOT tick 'Add a README', '.gitignore', or 'licence'."
  echo "  2. When the empty repo exists, re-run this script — or run:"
  echo "       git push -u origin main"
  echo
  read -r -p "Empty repo exists on GitHub now? [y/N] " ok
  if [[ "$ok" =~ ^[Yy] ]]; then
    git push -u origin main
    echo "✓ main pushed."
  else
    echo "Aborting. Create the repo, then re-run."
    exit 1
  fi
fi

echo
echo "─────────────────────────────────────────────────────────────"
echo "Next steps (manual, one-time, in the GitHub UI):"
echo
echo "  1. https://github.com/$ORG/$REPO/settings/actions"
echo "     Under 'Workflow permissions':"
echo "       ✓ Read and write permissions"
echo "       ✓ Allow GitHub Actions to create and approve pull requests"
echo "     Save."
echo
echo "  2. https://github.com/$ORG/$REPO/actions"
echo "     Open 'Crate Web Manifest — Health Check' → 'Run workflow'."
echo "     First run populates all status fields and commits."
echo
echo "  3. Verify the raw URL your Swift client will hit:"
echo "       https://raw.githubusercontent.com/$ORG/$REPO/main/crate_web_manifest.json"
echo "     Expect 404 while private — that's fine during dev."
echo
echo "─────────────────────────────────────────────────────────────"
echo "⚠  PRE-LAUNCH REMINDER"
echo
echo "  The shipped Crate client fetches via raw.githubusercontent.com"
echo "  UNAUTHENTICATED. A private repo will return 404 and the Web"
echo "  directory will be empty on every launch."
echo
echo "  BEFORE first public TestFlight/App Store build:"
echo "    https://github.com/$ORG/$REPO/settings"
echo "    → Danger Zone → Change visibility → Make public"
echo
echo "  See README.md → 'Pre-launch checklist' for full steps."
echo "─────────────────────────────────────────────────────────────"
echo
echo "Done."
