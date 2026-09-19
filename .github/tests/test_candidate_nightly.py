# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "dispatch",
    Path(__file__).resolve().parents[1] / "scripts/dispatch-candidate-tier2.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.runs = []
        self.sha = "a" * 40
        self.now = datetime(2026, 9, 19, 23, 17, tzinfo=timezone.utc)

    def api(self, repo, endpoint, body=None):
        self.calls.append((repo, endpoint, body))
        if endpoint.startswith("git/ref/"):
            return {"object": {"sha": self.sha}}
        if "/runs?" in endpoint:
            return {"workflow_runs": self.runs}
        return {}

    def invoke(self, dry_run=True):
        return module.dispatch(
            "owner/cva6",
            "master_candidate",
            dry_run=dry_run,
            api=self.api,
            now=self.now,
        )

    def test_default_is_read_only(self):
        self.assertEqual(self.invoke()["action"], "would-dispatch")
        self.assertTrue(all(c[2] is None for c in self.calls))

    def test_explicit_execute_posts_only_same_repository(self):
        self.assertEqual(self.invoke(False)["action"], "dispatched")
        posts = [c for c in self.calls if c[2] is not None]
        self.assertEqual(
            posts,
            [
                (
                    "owner/cva6",
                    "actions/workflows/openhw-cva6-ci-tier2.yml/dispatches",
                    {"ref": "master_candidate"},
                )
            ],
        )

    def test_existing_even_failed_run_prevents_retry_loop(self):
        self.runs = [
            {
                "head_sha": self.sha,
                "head_branch": "master_candidate",
                "created_at": "2026-09-19T01:00:00Z",
                "event": "workflow_dispatch",
                "conclusion": "failure",
            }
        ]
        self.assertEqual(self.invoke(False)["action"], "already-dispatched")

    def test_yesterday_or_other_sha_does_not_block(self):
        self.runs = [
            {
                "head_sha": self.sha,
                "head_branch": "master_candidate",
                "created_at": "2026-09-18T01:00:00Z",
                "event": "workflow_dispatch",
            }
        ]
        self.assertEqual(self.invoke()["action"], "would-dispatch")

    def test_bad_ref(self):
        for ref in ["../main", "--help", "x\ny", "x.lock", "x/../y"]:
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                module.validate_ref(ref)

    def test_missing_cook_preflight_never_dispatches(self):
        def api(repo, endpoint, body=None):
            if "contents/" in endpoint:
                raise RuntimeError("not found")
            return self.api(repo, endpoint, body)

        with self.assertRaises(RuntimeError):
            module.dispatch("o/cva6", "master", dry_run=False, api=api)
        self.assertTrue(all(c[2] is None for c in self.calls))

    def test_ref_movement_rejected(self):
        count = 0

        def api(repo, endpoint, body=None):
            nonlocal count
            if endpoint.startswith("git/ref/"):
                count += 1
                return {"object": {"sha": "a" * 40 if count == 1 else "b" * 40}}
            return self.api(repo, endpoint, body)

        with self.assertRaisesRegex(RuntimeError, "moved"):
            module.dispatch("o/cva6", "master_candidate", dry_run=False, api=api)


if __name__ == "__main__":
    unittest.main()
