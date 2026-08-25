#!/usr/bin/env python3
"""
Crate Web Manifest — schema validator.

Checks ``crate_web_manifest.json`` against the shape documented in README.md
("Top-level fields" / "Entry fields" / "Health-check contract"). Pure stdlib,
zero network: every rule is about what this repo owns, so it is safe and cheap
to run on every pull request.

Why this exists separately from ``health_check.py``: that script probes third
parties on a weekly cron and needs write permissions to open PRs and issues.
This one only reads a file, so it can be the PR-context gate that
``health-check.yml`` cannot be.

Exit code:
    0  manifest valid.
    1  one or more violations (all are reported, not just the first).
    2  script-level error (file missing / unreadable).

Run locally:
    python3 scripts/validate_manifest.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MANIFEST_PATH = Path("crate_web_manifest.json")

# Entry keys, exactly as documented in README.md "Entry fields". Unknown keys
# are an error: a typo'd field name (``souce_url``) would otherwise be silently
# ignored by every client and by health_check.py.
ENTRY_KEYS = {
    "id",
    "name",
    "source",
    "source_url",
    "download_url",
    "download_resolution",
    "tier",
    "license",
    "category",
    "content_types",
    "formats",
    "size_bytes_estimate",
    "file_count_estimate",
    "checksum_sha256",
    "health_check",
    "mirrors",
    "notes",
}

LICENSE_KEYS = {
    "name",
    "license_url",
    "attribution_required",
    "commercial_use",
    "redistribution_allowed",
    "ai_training_allowed",
}
LICENSE_FLAGS = LICENSE_KEYS - {"name", "license_url"}

# README "Entry fields": `direct` | `scrape` | `api`.
DOWNLOAD_RESOLUTIONS = {"direct", "scrape", "api"}

# README "Entry fields": 1 = CC0/PD; 2 = certified explicit licence; 3 = policy-only.
TIERS = {1, 2, 3}

# README "Health-check contract", and the STATUS_* constants written by
# scripts/health_check.py (lines 57-62). Kept in sync deliberately: this
# validator is the thing that catches them drifting apart.
HEALTH_STATUSES = {
    "ok",
    "redirect",
    "not_found",
    "server_error",
    "error",
    "unknown",
}
HEALTH_REQUIRED_KEYS = {"url", "last_checked", "status"}
HEALTH_OPTIONAL_KEYS = {"http_code", "note"}

KEBAB_CASE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
ISO_TIMESTAMP_Z = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


class Validator:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    # -- small typed helpers -------------------------------------------------

    def want_str(self, where: str, value: Any, *, allow_empty: bool = False) -> bool:
        if not isinstance(value, str):
            self.fail(where, f"expected a string, got {type(value).__name__}")
            return False
        if not allow_empty and not value.strip():
            self.fail(where, "must not be empty")
            return False
        return True

    def want_int(self, where: str, value: Any) -> bool:
        # bool is a subclass of int in Python; `true` is not a valid count.
        if isinstance(value, bool) or not isinstance(value, int):
            self.fail(where, f"expected an integer, got {type(value).__name__}")
            return False
        return True

    def want_url(self, where: str, value: Any) -> None:
        if not self.want_str(where, value):
            return
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https"):
            self.fail(where, f"URL scheme must be http/https, got {parsed.scheme!r} in {value!r}")
        elif not parsed.netloc:
            self.fail(where, f"URL has no host: {value!r}")

    def want_str_list(self, where: str, value: Any) -> None:
        if not isinstance(value, list):
            self.fail(where, f"expected a list, got {type(value).__name__}")
            return
        if not value:
            self.fail(where, "must not be empty")
            return
        for i, item in enumerate(value):
            self.want_str(f"{where}[{i}]", item)

    def want_keys(self, where: str, obj: dict[str, Any], expected: set[str]) -> None:
        missing = sorted(expected - obj.keys())
        unknown = sorted(obj.keys() - expected)
        if missing:
            self.fail(where, f"missing required field(s): {', '.join(missing)}")
        if unknown:
            self.fail(where, f"unknown field(s): {', '.join(unknown)}")

    # -- structure -----------------------------------------------------------

    def validate(self, data: Any) -> None:
        if not isinstance(data, dict):
            self.fail("manifest", f"top level must be an object, got {type(data).__name__}")
            return

        self.validate_top_level(data)

        entries = data.get("entries")
        if not isinstance(entries, list):
            return  # already reported; nothing further to walk.

        categories = data.get("categories")
        vocabulary = set(categories) if isinstance(categories, list) else set()
        known_ids = {
            e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)
        }

        seen: set[str] = set()
        for i, entry in enumerate(entries):
            where = f"entries[{i}]"
            if not isinstance(entry, dict):
                self.fail(where, f"expected an object, got {type(entry).__name__}")
                continue
            if isinstance(entry.get("id"), str):
                where = f"entries[{i}] ({entry['id']})"
            self.validate_entry(where, entry, vocabulary, known_ids, seen)

    def validate_top_level(self, data: dict[str, Any]) -> None:
        self.want_keys(
            "manifest",
            data,
            {
                "schema_version",
                "generated_at",
                "generator",
                "description",
                "categories",
                "license_flags_reference",
                "entries",
            },
        )

        if "schema_version" in data and self.want_int("schema_version", data["schema_version"]):
            if data["schema_version"] < 1:
                self.fail("schema_version", f"must be >= 1, got {data['schema_version']}")

        if "generated_at" in data and self.want_str("generated_at", data["generated_at"]):
            if not ISO_DATE.fullmatch(data["generated_at"]):
                self.fail("generated_at", f"expected YYYY-MM-DD, got {data['generated_at']!r}")

        for field in ("generator", "description"):
            if field in data:
                self.want_str(field, data[field])

        if "categories" in data:
            self.want_str_list("categories", data["categories"])
            if isinstance(data["categories"], list):
                dupes = sorted({c for c in data["categories"] if data["categories"].count(c) > 1})
                if dupes:
                    self.fail("categories", f"duplicate value(s): {', '.join(map(str, dupes))}")

        if "license_flags_reference" in data and not isinstance(
            data["license_flags_reference"], dict
        ):
            self.fail(
                "license_flags_reference",
                f"expected an object, got {type(data['license_flags_reference']).__name__}",
            )

        if "entries" in data:
            if not isinstance(data["entries"], list):
                self.fail("entries", f"expected a list, got {type(data['entries']).__name__}")
            elif not data["entries"]:
                self.fail("entries", "must not be empty")

    def validate_entry(
        self,
        where: str,
        entry: dict[str, Any],
        vocabulary: set[str],
        known_ids: set[str],
        seen: set[str],
    ) -> None:
        self.want_keys(where, entry, ENTRY_KEYS)

        entry_id = entry.get("id")
        if "id" in entry and self.want_str(f"{where}.id", entry_id):
            if not KEBAB_CASE.fullmatch(entry_id):
                self.fail(f"{where}.id", f"must be kebab-case ([a-z0-9-]), got {entry_id!r}")
            if entry_id in seen:
                # README: ids are a client-side primary key and are referenced
                # by mirrors[]; two entries sharing one is a real defect.
                self.fail(f"{where}.id", f"duplicate id {entry_id!r}")
            seen.add(entry_id)

        for field in ("name", "source", "download_resolution", "category"):
            if field in entry:
                self.want_str(f"{where}.{field}", entry[field])
        if "notes" in entry:
            self.want_str(f"{where}.notes", entry["notes"], allow_empty=True)

        if "source_url" in entry:
            self.want_url(f"{where}.source_url", entry["source_url"])
        if entry.get("download_url") is not None and "download_url" in entry:
            self.want_url(f"{where}.download_url", entry["download_url"])

        if entry.get("download_resolution") not in DOWNLOAD_RESOLUTIONS and isinstance(
            entry.get("download_resolution"), str
        ):
            self.fail(
                f"{where}.download_resolution",
                f"must be one of {sorted(DOWNLOAD_RESOLUTIONS)}, got "
                f"{entry['download_resolution']!r}",
            )

        if "tier" in entry and self.want_int(f"{where}.tier", entry["tier"]):
            if entry["tier"] not in TIERS:
                self.fail(f"{where}.tier", f"must be one of {sorted(TIERS)}, got {entry['tier']}")

        if isinstance(entry.get("category"), str) and vocabulary:
            if entry["category"] not in vocabulary:
                self.fail(
                    f"{where}.category",
                    f"{entry['category']!r} is not in the manifest's categories[] vocabulary",
                )

        for field in ("content_types", "formats"):
            if field in entry:
                self.want_str_list(f"{where}.{field}", entry[field])

        for field in ("size_bytes_estimate", "file_count_estimate"):
            if entry.get(field) is not None and field in entry:
                if self.want_int(f"{where}.{field}", entry[field]) and entry[field] < 0:
                    self.fail(f"{where}.{field}", f"must be >= 0, got {entry[field]}")

        if entry.get("checksum_sha256") is not None and "checksum_sha256" in entry:
            value = entry["checksum_sha256"]
            if self.want_str(f"{where}.checksum_sha256", value) and not SHA256_HEX.fullmatch(value):
                self.fail(
                    f"{where}.checksum_sha256",
                    f"expected 64 lowercase hex characters, got {value!r}",
                )

        if "license" in entry:
            self.validate_license(f"{where}.license", entry["license"])
        if "health_check" in entry:
            self.validate_health_check(f"{where}.health_check", entry["health_check"])
        if "mirrors" in entry:
            self.validate_mirrors(f"{where}.mirrors", entry["mirrors"], entry_id, known_ids)

    def validate_license(self, where: str, license_obj: Any) -> None:
        if not isinstance(license_obj, dict):
            self.fail(where, f"expected an object, got {type(license_obj).__name__}")
            return
        self.want_keys(where, license_obj, LICENSE_KEYS)

        if "name" in license_obj:
            self.want_str(f"{where}.name", license_obj["name"])
        if "license_url" in license_obj:
            self.want_url(f"{where}.license_url", license_obj["license_url"])
        for flag in sorted(LICENSE_FLAGS):
            if flag in license_obj and not isinstance(license_obj[flag], bool):
                # These drive the client's advisory badges (README "Advisory-badge
                # UI semantics"); a string "false" is truthy and would flip a badge.
                self.fail(
                    f"{where}.{flag}",
                    f"expected a boolean, got {type(license_obj[flag]).__name__}",
                )

    def validate_health_check(self, where: str, health: Any) -> None:
        if not isinstance(health, dict):
            self.fail(where, f"expected an object, got {type(health).__name__}")
            return

        missing = sorted(HEALTH_REQUIRED_KEYS - health.keys())
        unknown = sorted(health.keys() - HEALTH_REQUIRED_KEYS - HEALTH_OPTIONAL_KEYS)
        if missing:
            self.fail(where, f"missing required field(s): {', '.join(missing)}")
        if unknown:
            self.fail(where, f"unknown field(s): {', '.join(unknown)}")

        if "url" in health:
            self.want_url(f"{where}.url", health["url"])

        if "last_checked" in health and self.want_str(
            f"{where}.last_checked", health["last_checked"]
        ):
            if not ISO_TIMESTAMP_Z.fullmatch(health["last_checked"]):
                self.fail(
                    f"{where}.last_checked",
                    f"expected YYYY-MM-DDTHH:MM:SSZ, got {health['last_checked']!r}",
                )

        if "status" in health and self.want_str(f"{where}.status", health["status"]):
            if health["status"] not in HEALTH_STATUSES:
                self.fail(
                    f"{where}.status",
                    f"must be one of {sorted(HEALTH_STATUSES)}, got {health['status']!r}",
                )

        if health.get("http_code") is not None and "http_code" in health:
            if self.want_int(f"{where}.http_code", health["http_code"]):
                if not 100 <= health["http_code"] <= 599:
                    self.fail(
                        f"{where}.http_code",
                        f"must be a 100-599 HTTP status, got {health['http_code']}",
                    )

        if "note" in health:
            self.want_str(f"{where}.note", health["note"], allow_empty=True)

    def validate_mirrors(
        self, where: str, mirrors: Any, entry_id: Any, known_ids: set[str]
    ) -> None:
        if not isinstance(mirrors, list):
            self.fail(where, f"expected a list, got {type(mirrors).__name__}")
            return
        for i, mirror in enumerate(mirrors):
            if not self.want_str(f"{where}[{i}]", mirror):
                continue
            if mirror == entry_id:
                self.fail(f"{where}[{i}]", f"entry lists itself as a mirror ({mirror!r})")
            elif mirror not in known_ids:
                # README: mirrors[] holds other entry ids and drives client-side
                # fallback; a dangling id is a fallback that silently never fires.
                self.fail(f"{where}[{i}]", f"references unknown entry id {mirror!r}")
        dupes = sorted({m for m in mirrors if isinstance(m, str) and mirrors.count(m) > 1})
        if dupes:
            self.fail(where, f"duplicate mirror id(s): {', '.join(dupes)}")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else MANIFEST_PATH

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
        print(f"\nFAIL: {path} is not valid JSON.")
        return 1

    validator = Validator()
    validator.validate(data)

    if validator.errors:
        for error in validator.errors:
            print(f"{path}: {error}")
        print(f"\nFAIL: {len(validator.errors)} schema violation(s) in {path}.")
        return 1

    entry_count = len(data.get("entries", []))
    print(f"OK: {path} is valid — {entry_count} entries, schema_version {data['schema_version']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
