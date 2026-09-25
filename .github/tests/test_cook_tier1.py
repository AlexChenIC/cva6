# SPDX-License-Identifier: Apache-2.0
"""CI orchestration fixtures; real RTL execution is a separate workflow job."""

import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml

from test_verilator_testharness_run import REPO_ROOT, working_directory
from test_cook_testharness_smoke import run_result

TIER = runpy.run_path(str(REPO_ROOT / ".github/scripts/cook_tier1.py"))
MATRIX = json.loads((REPO_ROOT / TIER["MATRIX"]).read_text())


def batch_fixture(root, target, testlist, names):
    cases = []
    for name in names:
        directory = TIER["simulation_directory"](
            root, target, name, TIER["CompMode"].rtl
        )
        run_result(directory)
        for filename in ("result.yml", "cook_manifest.yml"):
            path = directory / filename
            data = yaml.safe_load(path.read_text())
            options = data["options"] if filename == "cook_manifest.yml" else data
            options.update(target=target, test_name=name)
            path.write_text(yaml.safe_dump(data))
        if name != TIER["HELLO_NAME"]:
            (directory / "testharness.log").write_text("*** SUCCESS *** (tohost = 0)\n")
        cases.append({"test_name": name, "status": "PASS", "detail": "fixture"})
    summary = {
        "schema_version": 1,
        "target": target,
        "testlist": testlist,
        "simulator": "verilator",
        "comp_mode": "rtl",
        "trace_mode": "notrace",
        "iss_enabled": False,
        "status": "PASS",
        "total": len(names),
        "passed": len(names),
        "failed": 0,
        "cases": cases,
    }
    report = {
        "status": "pass",
        "metrics": [
            {
                "status": "pass",
                "type": "table_status",
                "value": [
                    {
                        "status": "pass",
                        "label": "PASS",
                        "col": [target, name, "fixture"],
                    }
                    for name in names
                ],
            }
        ],
    }
    path = TIER["report_path"](root, target, TIER["Simulator"].verilator, testlist)
    path.write_text(yaml.safe_dump(report))
    path.with_name(path.name.replace("_report.yml", "_summary.yml")).write_text(
        yaml.safe_dump(summary)
    )
    return summary


class Tier1Tests(unittest.TestCase):
    def test_matrix_is_two_targets_and_five_real_tests(self):
        self.assertEqual(
            [r["target"] for r in MATRIX["include"]], ["cv32a60x_axi", "cv32a65x_axi"]
        )
        self.assertEqual(
            MATRIX["expected_tests"],
            [f"rv32ui-p-{n}_0" for n in ("add", "lw", "sw", "beq", "jal")],
        )
        for row in MATRIX["include"]:
            matrix, checked = TIER["matrix_row"](REPO_ROOT, row["target"])
            self.assertEqual((matrix, checked), (MATRIX, row))
            self.assertNotIn("zcmt", row["march"])
        self.assertEqual([r["hello_world"] for r in MATRIX["include"]], [False, True])
        with self.assertRaises(ValueError):
            TIER["matrix_row"](REPO_ROOT, "unknown")

    def test_declared_cases_cannot_silently_disappear(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (TIER["MATRIX"], MATRIX["testlist"], TIER["HELLO_TESTLIST"]):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO_ROOT / name, dest)
            path = root / MATRIX["testlist"]
            data = yaml.safe_load(path.read_text())
            data["testlist"][0]["iterations"] = 0
            path.write_text(yaml.safe_dump(data))
            with self.assertRaises(ValueError):
                TIER["matrix_row"](root, "cv32a60x_axi")

    def test_commands_build_hardware_once_and_do_not_compare_iss(self):
        for row in MATRIX["include"]:
            commands = TIER["cook_commands"](MATRIX, row)
            recipes = [c[2] for c in commands]
            self.assertEqual(recipes.count("verilator-testharness-comp"), 1)
            self.assertEqual(len(commands), 6 if row["hello_world"] else 3)
            for command in commands:
                if command[2] in (
                    "testharness-run-testlist",
                    "verilator-testharness-run",
                ):
                    self.assertIn("--no-iss-enabled", command)
                    self.assertIn("notrace", command)
                if command[2] == "sw-compile-testlist":
                    self.assertEqual(
                        command[command.index("--march") + 1], row["march"]
                    )
            self.assertNotIn("cva6.py", str(commands))
            self.assertNotIn("verilator-run", recipes)

    def test_test_sources_require_pinned_revision_and_patches(self):
        subprocess = TIER["subprocess"]
        with patch.object(subprocess, "check_output", return_value="wrong\n"):
            with self.assertRaisesRegex(ValueError, "revision"):
                TIER["test_sources"](REPO_ROOT)
        with (
            patch.object(
                subprocess, "check_output", return_value=TIER["RISCV_TESTS_SHA"]
            ),
            patch.object(
                subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "git apply"),
            ),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                TIER["test_sources"](REPO_ROOT)
        with (
            patch.object(
                subprocess,
                "check_output",
                side_effect=[TIER["RISCV_TESTS_SHA"], "-missing env\n"],
            ),
            patch.object(subprocess, "run"),
        ):
            with self.assertRaisesRegex(ValueError, "submodules"):
                TIER["test_sources"](REPO_ROOT)
        with (
            patch.object(
                subprocess,
                "check_output",
                side_effect=[
                    TIER["RISCV_TESTS_SHA"],
                    " pinned env\n",
                    b"test patch",
                    b"env patch",
                ],
            ),
            patch.object(subprocess, "run") as run,
        ):
            result = TIER["test_sources"](REPO_ROOT)
            self.assertEqual(result["revision"], TIER["RISCV_TESTS_SHA"])
            self.assertEqual(len(result["patched_tree_diff_sha256"]), 64)
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertIn("--reverse", call.args[0])
                self.assertIn("--check", call.args[0])
                self.assertTrue(call.kwargs["check"])

    def test_summary_requires_exact_names_counts_and_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            target = MATRIX["include"][0]["target"]
            names = MATRIX["expected_tests"]
            summary = batch_fixture(Path(directory), target, MATRIX["testlist"], names)
            check = lambda data: TIER["checked_summary"](
                data, target, MATRIX["testlist"], names
            )
            check(summary)
            for change in (
                {"cases": summary["cases"][:-1]},
                {"cases": list(reversed(summary["cases"]))},
                {"cases": [summary["cases"][0]] * 5},
                {"total": True},
                {"passed": 4},
                {"failed": 1},
                {"schema_version": True},
                {"iss_enabled": 0},
                {"status": "FAIL"},
                {"target": "other"},
            ):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    check({**summary, **change})

    def test_batch_checks_every_receipt_log_manifest_and_report(self):
        target = MATRIX["include"][0]["target"]
        names = MATRIX["expected_tests"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = TIER["simulation_directory"](
                root, target, names[-1], TIER["CompMode"].rtl
            )
            for filename, replacement in (
                ("result.yml", "status: FAIL"),
                ("cook_manifest.yml", "recipe: other"),
                ("testharness.log", "*** FAILED ***"),
                ("result.yml", None),
            ):
                batch_fixture(root, target, MATRIX["testlist"], names)
                path = run_dir / filename
                if replacement is None:
                    path.unlink()
                else:
                    path.write_text(replacement)
                with (
                    self.subTest(filename=filename),
                    self.assertRaises((ValueError, OSError)),
                ):
                    TIER["check_batch"](root, target, MATRIX["testlist"], names)
            batch_fixture(root, target, MATRIX["testlist"], names)
            receipt = run_dir / "result.yml"
            data = yaml.safe_load(receipt.read_text())
            data["detail"] = "different"
            receipt.write_text(yaml.safe_dump(data))
            with self.assertRaisesRegex(ValueError, "disagrees"):
                TIER["check_batch"](root, target, MATRIX["testlist"], names)
            batch_fixture(root, target, MATRIX["testlist"], names)
            report = TIER["report_path"](
                root, target, TIER["Simulator"].verilator, MATRIX["testlist"]
            )
            report.write_text("status: pass\nmetrics: []")
            with self.assertRaises(ValueError):
                TIER["check_batch"](root, target, MATRIX["testlist"], names)

    def exercise(self, row, failure=None, timeout=False, missing_case=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (TIER["MATRIX"], MATRIX["testlist"], TIER["HELLO_TESTLIST"]):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO_ROOT / name, dest)
            config = root / "ci-results/cook-config"
            config.mkdir(parents=True)
            (config / "environment.yml").write_text(
                "validation_mode: rtl-only\nrequired_toolchain: github_actions_gcc\n"
            )
            calls = []

            def execute(command, **kwargs):
                calls.append(command)
                kwargs["log"].write_text("fixture\n")
                if len(calls) == failure:
                    return (0 if timeout else 9), timeout
                if len(command) > 2 and command[2] == "testharness-run-testlist":
                    testlist = command[command.index("-l") + 1]
                    names = (
                        [TIER["HELLO_NAME"]]
                        if testlist == TIER["HELLO_TESTLIST"]
                        else MATRIX["expected_tests"]
                    )
                    batch_fixture(
                        root,
                        row["target"],
                        testlist,
                        names[:-1] if missing_case else names,
                    )
                elif len(command) > 2 and command[2] == "verilator-testharness-run":
                    batch_fixture(
                        root,
                        row["target"],
                        TIER["HELLO_TESTLIST"],
                        [TIER["HELLO_NAME"]],
                    )
                return 0, False

            with (
                working_directory(root),
                patch.dict(os.environ, {"CONFIG_DIR": str(config)}, clear=True),
                patch.object(
                    TIER["subprocess"], "check_output", return_value="fixture-sha\n"
                ),
                patch.dict(
                    TIER["main"].__globals__,
                    {
                        "run_logged_process": execute,
                        "test_sources": lambda _: {"revision": TIER["RISCV_TESTS_SHA"]},
                    },
                ),
            ):
                code = TIER["main"](row["target"])
            evidence = json.loads((root / "ci-results/tier1-evidence.json").read_text())
            saved = (root / "ci-results/hello-single/testharness.log").is_file()
            return code, evidence, len(calls), saved

    def test_both_matrix_rows_pass_with_complete_evidence(self):
        for row in MATRIX["include"]:
            code, evidence, calls, saved = self.exercise(row)
            self.assertEqual((code, evidence["status"]), (0, "PASS"))
            self.assertEqual(evidence["base_batch"]["total"], 5)
            self.assertEqual(calls, 8 if row["hello_world"] else 5)
            self.assertEqual(saved, row["hello_world"])
            self.assertEqual("hello_batch" in evidence, row["hello_world"])

    def test_every_command_failure_is_fatal_and_recorded(self):
        row = MATRIX["include"][1]
        for failure in range(1, 9):
            with self.subTest(step=failure):
                code, evidence, calls, _ = self.exercise(row, failure=failure)
                self.assertEqual(
                    (code, evidence["status"], calls), (1, "FAIL", failure)
                )
                self.assertEqual(evidence["commands"][-1]["exit_code"], 9)

    def test_timeout_and_incomplete_batch_cannot_pass(self):
        row = MATRIX["include"][0]
        for options in ({"failure": 4, "timeout": True}, {"missing_case": True}):
            code, evidence, _, _ = self.exercise(row, **options)
            self.assertEqual((code, evidence["status"]), (1, "FAIL"))

    def test_workflow_uses_declared_matrix_and_fail_closed_gate(self):
        path = REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier1.yml"
        workflow = yaml.safe_load(path.read_text())
        jobs = workflow["jobs"]
        self.assertEqual(
            jobs["regression"]["strategy"]["matrix"],
            "${{ fromJSON(needs.checks.outputs.matrix) }}",
        )
        self.assertFalse(jobs["regression"]["strategy"]["fail-fast"])
        self.assertEqual(jobs["tier1"]["if"], "always()")
        self.assertEqual(
            jobs["tier1"]["needs"], ["checks", "setup-tools", "regression"]
        )
        text = path.read_text()
        self.assertNotIn("continue-on-error", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("pull_request_target:", text)
        self.assertIn("contents: read", text)
        self.assertIn("cook-tier1.json", text)


if __name__ == "__main__":
    unittest.main()
