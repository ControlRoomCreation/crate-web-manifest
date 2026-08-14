#!/usr/bin/env python3
"""Tests for health_check.py's substantive-change detection.

Stdlib only — `requests` is stubbed before import so this runs anywhere
without installing scripts/requirements.txt, and it never touches the network.

Run:  python3 -m unittest discover -s scripts -p 'test_*.py' -v
"""

from __future__ import annotations

import copy
import sys
import types
import unittest
from pathlib import Path

# health_check imports `requests` at module scope for the probe path, which is
# not under test here. Stub it so this suite stays stdlib-only.
if "requests" not in sys.modules:
    stub = types.ModuleType("requests")
    stub.RequestException = Exception  # type: ignore[attr-defined]
    stub.get = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        AssertionError("network access from a unit test")
    )
    sys.modules["requests"] = stub

sys.path.insert(0, str(Path(__file__).resolve().parent))
import health_check  # noqa: E402


def manifest(last_checked: str, status: str = "ok", http_code: int = 200) -> dict:
    return {
        "generated_at": "2026-08-14",
        "entries": [
            {
                "id": "sonniss-gdc",
                "name": "Sonniss GDC bundle",
                "health_check": {
                    "url": "https://example.invalid/a",
                    "last_checked": last_checked,
                    "status": status,
                    "http_code": http_code,
                },
            },
            {
                "id": "no-health-block",
                "name": "entry without a health_check key",
            },
        ],
    }


class StripVolatileTests(unittest.TestCase):
    def test_timestamp_only_difference_is_not_substantive(self):
        a = manifest("2026-08-07T06:00:00Z")
        b = manifest("2026-08-14T06:00:00Z")
        b["generated_at"] = "2026-08-21"
        self.assertNotEqual(a, b, "precondition: the raw manifests differ")
        self.assertEqual(
            health_check.strip_volatile(a),
            health_check.strip_volatile(b),
            "a pure timestamp refresh must not read as a substantive change",
        )

    def test_status_change_is_substantive(self):
        a = manifest("2026-08-14T06:00:00Z", status="ok")
        b = manifest("2026-08-14T06:00:00Z", status="not_found", http_code=404)
        self.assertNotEqual(
            health_check.strip_volatile(a), health_check.strip_volatile(b)
        )

    def test_http_code_change_is_substantive(self):
        a = manifest("2026-08-14T06:00:00Z", http_code=200)
        b = manifest("2026-08-14T06:00:00Z", http_code=301)
        self.assertNotEqual(
            health_check.strip_volatile(a), health_check.strip_volatile(b)
        )

    def test_added_note_is_substantive(self):
        a = manifest("2026-08-14T06:00:00Z")
        b = copy.deepcopy(a)
        b["entries"][0]["health_check"]["note"] = "timeout after 30s"
        self.assertNotEqual(
            health_check.strip_volatile(a), health_check.strip_volatile(b)
        )

    def test_new_entry_is_substantive(self):
        a = manifest("2026-08-14T06:00:00Z")
        b = copy.deepcopy(a)
        b["entries"].append({"id": "new-source", "name": "New source"})
        self.assertNotEqual(
            health_check.strip_volatile(a), health_check.strip_volatile(b)
        )

    def test_does_not_mutate_its_argument(self):
        a = manifest("2026-08-14T06:00:00Z")
        before = copy.deepcopy(a)
        health_check.strip_volatile(a)
        self.assertEqual(a, before, "strip_volatile must not mutate the caller's dict")

    def test_entry_without_health_check_block_is_tolerated(self):
        a = manifest("2026-08-14T06:00:00Z")
        stripped = health_check.strip_volatile(a)
        self.assertEqual(stripped["entries"][1]["id"], "no-health-block")
        self.assertNotIn("generated_at", stripped)
        self.assertNotIn("last_checked", stripped["entries"][0]["health_check"])


if __name__ == "__main__":
    unittest.main()
