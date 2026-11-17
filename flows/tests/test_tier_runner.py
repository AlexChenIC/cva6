# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Test batch orchestration with controlled process results, not RTL."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/cook"))
spec = importlib.util.spec_from_file_location(
    "tier_runner", ROOT / ".github/cook/run-tier-regression.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TierRunnerTests(unittest.TestCase):
    def run_scenario(self, failed_recipe=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lists = {}
            for suite in ["basic", "extra"]:
                path = root / f"{suite}.yaml"
                path.write_text(yaml.safe_dump({"testlist": [{"test": suite}]}))
                lists[suite] = str(path)
            calls = []

            def process(command, **_):
                recipe = command[2]
                calls.append(command)
                fail = recipe == failed_recipe and (
                    recipe != "testharness-run-testlist"
                    or command[command.index("-l") + 1] == lists["basic"]
                )
                return (1 if fail else 0), False

            old = Path.cwd()
            try:
                os.chdir(root)
                with (
                    patch.object(sys, "argv", ["runner", "--profile", "rv32-scalar"]),
                    patch.object(
                        runner,
                        "materialize",
                        return_value=(
                            {
                                "target": "test_target",
                                "tandem_enabled": True,
                                "environment": "unit-test",
                            },
                            lists,
                        ),
                    ),
                    patch.object(runner, "run_logged", side_effect=process),
                    patch.object(runner, "checked_report"),
                    patch.object(
                        runner.subprocess, "check_output", return_value="test-sha"
                    ),
                ):
                    code = runner.main()
                report = yaml.safe_load(
                    (
                        root / "build/tier-regression/rv32-scalar/cook_report.yml"
                    ).read_text()
                )
            finally:
                os.chdir(old)
            return code, calls, report

    def test_failed_batch_continues_and_final_status_fails(self):
        code, calls, report = self.run_scenario("testharness-run-testlist")
        batches = [c for c in calls if c[2] == "testharness-run-testlist"]
        self.assertEqual(len(batches), 2)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "fail")
        commands = next(m["data"] for m in report["metrics"] if m["name"] == "Commands")
        self.assertEqual([c["exit_code"] for c in commands], [0, 0, 0, 1, 0])

    def test_compile_failure_stops_before_any_batch(self):
        code, calls, report = self.run_scenario("sw-compile-testlist")
        self.assertEqual(len(calls), 1)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "fail")

    def test_all_success_passes(self):
        code, calls, report = self.run_scenario()
        self.assertEqual(len(calls), 5)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
