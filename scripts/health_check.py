#!/usr/bin/env python3
"""
Crate Web Manifest — health-check runner.

Reads ``crate_web_manifest.json``, pings each entry's ``health_check.url``,
updates ``status`` / ``last_checked`` / ``http_code`` / ``note`` in place,
and re-writes the file. Emits summary and new-failure info to GitHub Actions
outputs so the surrounding workflow can commit + open issues.

Two "did anything change" outputs, deliberately different:

``changed``
    the serialised file differs at all. This is true on essentially every
    run, because ``last_checked`` is rewritten for every entry and
    ``generated_at`` is rewritten at the top level even when nothing about
    the world changed.

``substantive``
    something other than those timestamps differs — a status, an HTTP code,
    or a note. This is the one worth committing. Between 2026-07-20 and
    2026-08-14 every scheduled run was pure timestamp churn.

Exit code:
    0  on success (regardless of which entries failed their checks).
    2  on script-level error (manifest unreadable, etc.).

Run locally:
    python scripts/health_check.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

MANIFEST_PATH = Path("crate_web_manifest.json")
TIMEOUT_SECONDS = 30
SLEEP_BETWEEN_REQUESTS_S = 1.5  # be polite to Sonniss / archive.org / Kenney
USER_AGENT = (
    "CrateWebManifestHealthCheck/1.0 "
    "(+https://github.com/ControlRoomCreation/crate-web-manifest; contact: bot@controlroomcreative.app)"
)

# Status vocabulary written into the manifest.
STATUS_OK = "ok"
STATUS_REDIRECT = "redirect"
STATUS_NOT_FOUND = "not_found"
STATUS_SERVER_ERROR = "server_error"
STATUS_ERROR = "error"
STATUS_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# HTTP probe
# ---------------------------------------------------------------------------

def classify(status_code: int) -> str:
    if 200 <= status_code < 300:
        return STATUS_OK
    if 300 <= status_code < 400:
        # we follow redirects — landing here means the redirect chain itself
        # didn't terminate at 2xx, which is odd but not necessarily fatal.
        return STATUS_REDIRECT
    if status_code == 404:
        return STATUS_NOT_FOUND
    if 400 <= status_code < 500:
        return STATUS_ERROR
    if 500 <= status_code < 600:
        return STATUS_SERVER_ERROR
    return STATUS_ERROR


def probe(url: str) -> tuple[str, int | None, str | None]:
    """
    Return (status, http_code, note). Tries HEAD first; falls back to a
    1-byte ranged GET when the origin rejects HEAD (common on CDN-fronted
    download URLs).
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    try:
        r = requests.head(
            url, headers=headers, allow_redirects=True, timeout=TIMEOUT_SECONDS
        )
        if r.status_code in (403, 405, 501):
            r = requests.get(
                url,
                headers={**headers, "Range": "bytes=0-0"},
                allow_redirects=True,
                timeout=TIMEOUT_SECONDS,
                stream=True,
            )
            r.close()
        return classify(r.status_code), r.status_code, None
    except requests.exceptions.Timeout:
        return STATUS_ERROR, None, "timeout"
    except requests.exceptions.ConnectionError as e:
        return STATUS_ERROR, None, f"connection: {e}"[:200]
    except requests.exceptions.RequestException as e:
        return STATUS_ERROR, None, f"request: {e}"[:200]


# ---------------------------------------------------------------------------
# Substantive-change detection
# ---------------------------------------------------------------------------

# Fields that move on every single run regardless of what the probes found.
VOLATILE_TOP_LEVEL = ("generated_at",)
VOLATILE_PER_ENTRY = ("last_checked",)


def strip_volatile(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with the always-moving timestamp fields removed.

    Two manifests that compare equal after this are the same *finding* even
    though their bytes differ. Committing that difference to a protected
    branch every week is noise that buries the runs which actually found
    something.
    """
    m = copy.deepcopy(manifest)
    for key in VOLATILE_TOP_LEVEL:
        m.pop(key, None)
    for entry in m.get("entries", []):
        hc = entry.get("health_check")
        if isinstance(hc, dict):
            for key in VOLATILE_PER_ENTRY:
                hc.pop(key, None)
    return m


# ---------------------------------------------------------------------------
# GitHub Actions outputs
# ---------------------------------------------------------------------------

def gha_output(name: str, value: str) -> None:
    """Write a key=value or multi-line key block to $GITHUB_OUTPUT."""
    out_path = os.environ.get("GITHUB_OUTPUT")
    if not out_path:
        return  # local run — silently no-op
    with open(out_path, "a", encoding="utf-8") as fh:
        if "\n" in value:
            delim = f"EOF_{name}_{int(time.time())}"
            fh.write(f"{name}<<{delim}\n{value}\n{delim}\n")
        else:
            fh.write(f"{name}={value}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not MANIFEST_PATH.exists():
        print(f"manifest not found at {MANIFEST_PATH}", file=sys.stderr)
        return 2

    raw_old = MANIFEST_PATH.read_text(encoding="utf-8")
    try:
        manifest = json.loads(raw_old)
    except json.JSONDecodeError as e:
        print(f"manifest is not valid JSON: {e}", file=sys.stderr)
        return 2

    # Snapshot before the probe loop mutates `manifest` in place.
    manifest_before = copy.deepcopy(manifest)

    entries: list[dict[str, Any]] = manifest.get("entries", [])
    if not entries:
        print("manifest has no entries", file=sys.stderr)
        return 0

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_failures: list[dict[str, Any]] = []
    ok_count = 0

    for i, entry in enumerate(entries, 1):
        eid = entry.get("id", f"<entry-{i}>")
        hc = entry.setdefault("health_check", {})
        url = hc.get("url") or entry.get("source_url")
        if not url:
            print(f"[{i}/{len(entries)}] {eid}: no URL, skipping")
            continue

        previous_status = hc.get("status", STATUS_UNKNOWN)
        status, code, note = probe(url)

        # transition: ok → not-ok counts as a "new failure" worth alerting on.
        if previous_status == STATUS_OK and status != STATUS_OK:
            new_failures.append(
                {"id": eid, "url": url, "status": status, "http": code, "note": note}
            )

        hc["last_checked"] = now_iso
        hc["status"] = status
        if code is not None:
            hc["http_code"] = code
        else:
            hc.pop("http_code", None)
        if note:
            hc["note"] = note
        else:
            hc.pop("note", None)

        if status == STATUS_OK:
            ok_count += 1

        line = f"[{i}/{len(entries)}] {eid}: {status}"
        if code is not None:
            line += f" ({code})"
        if note:
            line += f" — {note}"
        print(line)

        time.sleep(SLEEP_BETWEEN_REQUESTS_S)

    # Refresh the top-level snapshot date.
    manifest["generated_at"] = today

    # Re-serialise with stable key order + trailing newline so git diffs are clean.
    new_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    changed = new_text != raw_old
    substantive = strip_volatile(manifest_before) != strip_volatile(manifest)
    if changed:
        MANIFEST_PATH.write_text(new_text, encoding="utf-8")

    summary = (
        f"Checked {len(entries)} entries: {ok_count} ok, "
        f"{len(entries) - ok_count} non-ok. "
        f"{len(new_failures)} newly failing."
    )
    print()
    print(summary)

    if changed and not substantive:
        print("(only last_checked / generated_at moved — not worth a commit)")

    gha_output("changed", "true" if changed else "false")
    gha_output("substantive", "true" if substantive else "false")
    gha_output("summary", summary)
    if new_failures:
        failure_block = "\n".join(
            f"- `{f['id']}` — {f['status']}"
            + (f" (HTTP {f['http']})" if f["http"] is not None else "")
            + (f": {f['note']}" if f["note"] else "")
            + f"\n  {f['url']}"
            for f in new_failures
        )
        gha_output("new_failures", failure_block)
    else:
        gha_output("new_failures", "")

    return 0


if __name__ == "__main__":
    sys.exit(main())
