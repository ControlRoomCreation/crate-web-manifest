# Crate Web Directory — Manifest Schema

`crate_web_manifest.json` is the source-of-truth catalogue for the **Web** section of Crate. It is reference-only: Crate does not rehost any audio listed here. Clients fetch from `source_url` / `download_url` on first use, then compute waveforms / BPM / key / LUFS / duration client-side after download.

## Top-level fields

| Field | Type | Purpose |
|---|---|---|
| `schema_version` | int | Bump on any breaking change to the entry shape. |
| `generated_at` | ISO date | When this manifest snapshot was produced. |
| `generator` | string | Who/what produced it. Useful for audit. |
| `description` | string | Human-readable note about what this file is. |
| `categories` | string[] | Canonical category vocabulary — must match the Community-upload categoriser. |
| `license_flags_reference` | object | In-line documentation of the four licence boolean flags. |
| `entries` | object[] | The actual entries. |

## Entry fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | Stable, kebab-case, never reused. Used for cross-references and as a primary key client-side. |
| `name` | string | Display name. |
| `source` | string | Brand / publisher of origin. |
| `source_url` | URL | Landing page (always set). |
| `download_url` | URL or null | Direct file/zip URL when known and stable. Null when the client must resolve it via scrape or API. |
| `download_resolution` | enum | `direct` \| `scrape` \| `api` — tells the client how to get the actual download URL. |
| `tier` | int | 1 = CC0/PD; 2 = certified explicit licence file; 3 = YouTube/policy-only (none in initial set). |
| `license` | object | See licence subfields below. |
| `category` | string | One of `categories[]`. |
| `content_types` | string[] | Free-text tags for filtering. |
| `formats` | string[] | File formats inside the bundle. |
| `size_bytes_estimate` | int or null | Approximate; used for "this will use ~X GB" UI warnings. |
| `file_count_estimate` | int or null | Approximate; used for progress UI. |
| `checksum_sha256` | string or null | Filled in by the client after first successful download; lets future runs detect upstream changes. |
| `health_check` | object | `{ url, last_checked, status }` — populated by a periodic ping. |
| `mirrors` | string[] | List of other entry `id`s that are mirrors of the same content. Use for fallback. |
| `notes` | string | Anything else a user/dev should know. |

### `license` subfields

| Field | Type | Drives badge |
|---|---|---|
| `name` | string | Display label on the badge. |
| `license_url` | URL | Click-through for the full text. |
| `attribution_required` | bool | If true → ATTRIB badge + auto-append to ATTRIBUTION.md on import. |
| `commercial_use` | bool | If false → COMMERCIAL-RESTRICTED warning. (Should always be true in this manifest per Phase-1 strict filter.) |
| `redistribution_allowed` | bool | If false → community members may not re-upload extracted files as their own content. |
| `ai_training_allowed` | bool | If false → NO-AI badge. Future Crate AI features must respect this per-entry. |

## Advisory-badge UI semantics (per user direction)

Badges are **informational**, not enforcement gates. The client surfaces them on every entry card and at import time, but never blocks a download or import. The user is responsible for compliance.

Recommended badge set (computed from licence flags):

- **TIER 1** / **TIER 2** / **TIER 3** — from `tier`
- **NO ATTRIB** (green) when `attribution_required` is false; **ATTRIB** (amber) when true
- **COMMERCIAL OK** (green) when `commercial_use` is true; **COMMERCIAL RESTRICTED** (red) when false
- **NO AI** (red) when `ai_training_allowed` is false (notably Sonniss)
- **NO REDISTRIBUTE** (amber) when `redistribution_allowed` is false (Sonniss, 99Sounds)

## Health-check contract

A scheduled **GitHub Actions** workflow hits `health_check.url` weekly and updates `health_check.last_checked`, `health_check.status`, and (where available) `health_check.http_code` / `health_check.note` in-place. Stale (>14 days) or non-`ok` entries should render with a warning in the Crate client.

Status vocabulary written into the manifest:

- `ok` — 2xx response
- `redirect` — redirect chain did not resolve to 2xx (rare; flag but not fatal)
- `not_found` — 404
- `server_error` — 5xx
- `error` — 4xx other than 404, or network/timeout/DNS
- `unknown` — never checked yet (initial state on new entries)

### Files that implement this

| Path | Purpose |
|---|---|
| `.github/workflows/health-check.yml` | Cron + manual-dispatch workflow; checks out, runs Python, opens a **PR** for substantive diffs, opens an Issue on new failures. Never pushes to `main`. |
| `scripts/health_check.py` | Probe runner — HEAD-then-ranged-GET, status classification, in-place manifest update, GitHub Actions outputs. |
| `scripts/requirements.txt` | Pinned Python deps (`requests`). |

### Setup checklist

1. Push this repo to `ControlRoomCreation/crate-web-manifest` (run `bash SETUP.sh` from the repo root — it uses `gh` if installed, else walks you through the web UI).
2. In **Settings → Actions → General → Workflow permissions**, tick *Allow GitHub Actions to create and approve pull requests*.

   > **Currently off** (verified 2026-08-14 at both repo and org level:
   > `/repos/ControlRoomCreation/crate-web-manifest/actions/permissions/workflow`
   > → `can_approve_pull_request_reviews: false`). While it is off, the
   > workflow still pushes its update branch and then opens an **issue**
   > linking the compare view instead of a PR. The run stays green either
   > way. Turning it on is the only thing needed to get PRs.

   The workflow declares its own `permissions:` block, so the
   *Read and write permissions* radio does not need changing.
3. First run: trigger manually via **Actions → Crate Web Manifest — Health Check → Run workflow**. This populates all `status` fields the first time.

### What triggers a PR vs. an issue

- **PR** — a *substantive* field changed: `status`, `http_code`, or `note` on any entry, or an entry was added or removed. A refreshed `last_checked` / `generated_at` on its own does **not** qualify; those move on every run and committing them weekly is churn. Per-run freshness is written to the Actions run summary instead.
- **Issue** — one or more entries transitioned from `ok` → anything else in this run. Labelled `web-manifest`, `health-check`. Ok → ok with no change does not open an issue.
- **Nothing** — everything still `ok` and unchanged. The run is green and silent.

`main` is a protected branch, so the workflow never pushes to it. It failed
three consecutive scheduled runs (2026-07-27, 08-03, 08-10) with
`GH006: Protected branch update failed` while the check itself passed every
time; opening a PR is the fix.

### Running locally

```bash
pip install -r scripts/requirements.txt
python scripts/health_check.py
```

Local runs update the manifest file but don't commit, open PRs, or open issues (the GitHub Actions outputs are no-ops outside CI).

Unit tests for the substantive-change detection (stdlib only, no network,
no `requests` install needed):

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

### Cadence

Default is `cron: '0 6 * * 1'` (Mondays 06:00 UTC). Adjust in the workflow YAML if you want more frequent checks or a different window. Weekly is enough — these sources change slowly and a polite probe cadence avoids looking like a scraper.

## Updating the manifest

1. Add the new entry at the bottom of the `entries` array with a unique `id`.
2. Bump `generated_at`.
3. Do **not** change existing `id` values — they are referenced by `mirrors[]` and by client-side caches.
4. If you change a licence interpretation for an existing entry, bump `schema_version` and document why in `notes`.

## Initial entry coverage

24 entries in v1, all direct-download-friendly:

- 1 Sonniss hub + 4 yearly Sonniss bundles (2023–2026) + 4 Internet Archive Sonniss mirrors
- 6 Kenney audio packs (all CC0)
- 7 OpenGameArt CC0 sound-effect collections
- 1 rse/soundfx GitHub tarball (Tier 2, mixed CC0/CC-BY-3.0)
- 1 99Sounds aggregator pointer (Tier 2, per-pack licence)

API-only sources (Freesound CC0/CC-BY, BigSoundBank, Pixabay) are intentionally excluded from this manifest — they need first-class connectors in Crate, not Web-directory entries.

## Excluded sources (and why) — for institutional memory

- **BBC Sound Effects (RemArc)** — non-commercial only; fails strict filter.
- **Zapsplat free tier** — attribution + email gate; fails strict filter.
- **PennSound** — non-commercial only.
- **YouTube Audio Library** — Tier-3 ambiguity; better-covered by Tier-1 sources.
- **Generic "no copyright" YouTube channels** — unclear/misattributed terms.

## Consumption

The shipped Crate client fetches this manifest anonymously from `raw.githubusercontent.com/ControlRoomCreation/crate-web-manifest/main/crate_web_manifest.json` via `WebManifestService.load()`. No token is embedded in the app; repo is public-by-design so the fetch can succeed unauthenticated.
