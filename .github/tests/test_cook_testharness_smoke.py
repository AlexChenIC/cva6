# SPDX-License-Identifier: Apache-2.0
"""Contract tests use fixtures; the workflow separately runs a real RTL smoke."""

import copy
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

import yaml

from test_verilator_testharness_run import REPO_ROOT, working_directory

SMOKE = runpy.run_path(str(REPO_ROOT / ".github/scripts/cook_testharness_smoke.py"))
TARGET, TESTLIST, TEST_NAME = (
    SMOKE[key] for key in ("TARGET", "TESTLIST", "TEST_NAME")
)


def summary():
    return {
        "schema_version": 1,
        "target": TARGET,
        "testlist": TESTLIST,
        "simulator": "verilator",
        "comp_mode": "rtl",
        "trace_mode": "notrace",
        "iss_enabled": False,
        "status": "PASS",
        "total": 1,
        "passed": 1,
        "failed": 0,
        "cases": [{"test_name": TEST_NAME, "status": "PASS", "detail": "fixture"}],
    }


def report():
    return {
        "status": "pass",
        "metrics": [
            {
                "status": "pass",
                "type": "table_status",
                "value": [
                    {
                        "status": "pass",
                        "label": "PASS",
                        "col": [TARGET, TEST_NAME, "fixture"],
                    }
                ],
            }
        ],
    }


def run_result(directory):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.yml").write_text(
        yaml.safe_dump(
            {
                "target": TARGET,
                "test_name": TEST_NAME,
                "comp_mode": "rtl",
                "trace_mode": "notrace",
                "iss_enabled": False,
                "status": "PASS",
            }
        )
    )
    (directory / "testharness.log").write_text(
        "0: Hello World !\n*** SUCCESS *** (tohost = 0)\n"
    )
    (directory / "cook_manifest.yml").write_text("recipe: verilator-testharness-run\n")


class SmokeTests(unittest.TestCase):
    def test_summary_requires_one_current_matching_pass(self):
        self.assertEqual(SMOKE["checked_summary"](summary())["total"], 1)
        for change in (
            {"status": "FAIL"},
            {"iss_enabled": True},
            {"target": "other"},
            {"testlist": "other"},
            {"trace_mode": "fast"},
            {"total": True},
            {"failed": 1},
            {"cases": []},
            {"cases": [{"test_name": "other", "status": "PASS"}]},
            {"cases": [{"test_name": TEST_NAME, "status": "FAIL"}]},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                SMOKE["checked_summary"]({**summary(), **change})
        with self.assertRaises(ValueError):
            SMOKE["checked_summary"](None)

    def test_cook_report_must_agree_with_summary(self):
        SMOKE["checked_report"](report(), summary())
        for change in ({"status": "fail"}, {"metrics": []}, {"metrics": [None]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                SMOKE["checked_report"]({**report(), **change}, summary())
        wrong = copy.deepcopy(report())
        wrong["metrics"][0]["value"][0]["col"][1] = "other"
        with self.assertRaises(ValueError):
            SMOKE["checked_report"](wrong, summary())

    def test_receipt_and_greeting_are_both_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_result(root)
            SMOKE["checked_run"](root)
            for log in (
                "0: Hello World !\n",
                "*** SUCCESS *** (tohost = 0)\n",
                "0: Hello World !\n*** SUCCESS *** (tohost = 0)\n*** FAILED ***",
            ):
                (root / "testharness.log").write_text(log)
                with self.subTest(log=log), self.assertRaises(ValueError):
                    SMOKE["checked_run"](root)
            run_result(root)
            (root / "result.yml").unlink()
            with self.assertRaises(OSError):
                SMOKE["checked_run"](root)

    def test_direct_commands_do_not_use_legacy_or_iss(self):
        commands = SMOKE["cook_commands"]()
        self.assertEqual(
            [cmd[2] for cmd in commands],
            [
                "sw-compile-testlist",
                "verilator-testharness-comp",
                "verilator-testharness-run",
                "testharness-run-testlist",
            ],
        )
        for command in commands[2:]:
            self.assertIn("--no-iss-enabled", command)
            self.assertIn("notrace", command)
        self.assertNotIn("cva6.py", str(commands))
        self.assertNotIn("make", str(commands))

    def test_repository_testlist_reuses_hello_world(self):
        data = yaml.safe_load((REPO_ROOT / TESTLIST).read_text())
        self.assertEqual(len(data["testlist"]), 1)
        entry = data["testlist"][0]
        self.assertEqual((entry["test"], entry["iterations"]), ("hello-world", 1))
        source = REPO_ROOT / entry["asm_tests"].replace("<path_var>", "verif/tests")
        self.assertIn("Hello World !", source.read_text())
        self.assertEqual(entry["mabi"], "ilp32")
        self.assertNotIn("zcmt", entry["march"])

    def exercise_main(self, failure_step=None, timed_out=False, bad_greeting=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            testlist = root / TESTLIST
            testlist.parent.mkdir(parents=True)
            testlist.write_text("testlist:\n  - test: hello-world\n    iterations: 1\n")
            config = root / "config-fixture"
            config.mkdir()
            (config / "environment.yml").write_text(
                yaml.safe_dump(
                    {
                        "validation_mode": "rtl-only",
                        "required_toolchain": "github_actions_gcc",
                    }
                )
            )
            run_dir = SMOKE["simulation_directory"](
                root, TARGET, TEST_NAME, SMOKE["CompMode"].rtl
            )
            calls = []

            def execute(command, **options):
                calls.append(command)
                options["log"].write_text("fixture command\n")
                if len(calls) == failure_step:
                    return 0 if timed_out else 7, timed_out
                if len(calls) >= 3:
                    run_result(run_dir)
                if len(calls) == 4:
                    batch_report = SMOKE["report_path"](
                        root, TARGET, SMOKE["Simulator"].verilator, TESTLIST
                    )
                    batch_report.write_text(yaml.safe_dump(report()))
                    batch_report.with_name(
                        batch_report.name.replace("_report.yml", "_summary.yml")
                    ).write_text(yaml.safe_dump(summary()))
                    if bad_greeting:
                        (run_dir / "testharness.log").write_text(
                            "*** SUCCESS *** (tohost = 0)"
                        )
                return 0, False

            with (
                working_directory(root),
                patch.dict(os.environ, {"CONFIG_DIR": str(config)}, clear=True),
                patch.object(
                    SMOKE["subprocess"], "check_output", return_value="fixture-sha\n"
                ),
                patch.dict(SMOKE["main"].__globals__, {"run_logged_process": execute}),
            ):
                code = SMOKE["main"]()
            evidence = json.loads((root / "ci-results/evidence.json").read_text())
            saved_single = (root / "ci-results/single-test/testharness.log").is_file()
            return code, evidence, len(calls), saved_single

    def test_success_saves_independent_single_and_batch_results(self):
        code, evidence, calls, saved = self.exercise_main()
        self.assertEqual((code, evidence["status"], calls, saved), (0, "PASS", 4, True))
        self.assertEqual(evidence["single_test"]["test_name"], TEST_NAME)
        self.assertEqual(evidence["batch_test"]["test_name"], TEST_NAME)

    def test_any_failed_command_stops_execution_and_saves_failure(self):
        for step in range(1, 5):
            with self.subTest(step=step):
                code, evidence, calls, _ = self.exercise_main(failure_step=step)
                self.assertEqual((code, evidence["status"], calls), (1, "FAIL", step))
                self.assertEqual(evidence["commands"][-1]["exit_code"], 7)

    def test_timeout_cannot_pass_even_with_zero_exit_code(self):
        code, evidence, calls, _ = self.exercise_main(failure_step=2, timed_out=True)
        self.assertEqual((code, evidence["status"], calls), (1, "FAIL", 2))
        self.assertTrue(evidence["commands"][-1]["timed_out"])

    def test_batch_greeting_failure_preserves_single_test_evidence(self):
        code, evidence, calls, saved = self.exercise_main(bad_greeting=True)
        self.assertEqual((code, evidence["status"], calls, saved), (1, "FAIL", 4, True))
        self.assertIn("greeting", evidence["error"])


if __name__ == "__main__":
    unittest.main()
