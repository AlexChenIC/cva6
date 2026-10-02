# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Orchestration checks, not RTL ISA tests. Expected failures are asserted."""

from contextlib import chdir
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import typer
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flows.recipes import testharness_run_testlist as batch
from flows.recipes.sw_compile import run_compile_tool
from flows.recipes.verilator_testharness_comp import elaboration_directory
from flows.recipes.verilator_testharness_run import (
    check_manifests,
    read_tandem_report,
    run_test,
    run_testharness_and_trace,
    simulation_directory,
)
from flows.utils.logged_process import run_logged_process
from flows.utils.utils import CompMode, TraceMode
from prepare_testlists import materialize


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "native.yaml"
        self.good = dict(
            exit_cause="SUCCESS",
            exit_code=0,
            instr_count=8,
            csrs_match_count=4,
            mismatches_count=0,
            mismatches=None,
            mismatch_description="",
        )

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

    def test_native_success_requires_comparisons(self):
        self.write(self.report, self.good)
        self.assertEqual(read_tandem_report(self.report), self.good)
        for key, value in [
            ("instr_count", 0),
            ("instr_count", True),
            ("instr_count", "8"),
            ("csrs_match_count", -1),
            ("exit_code", 1),
            ("exit_code", False),
            ("exit_cause", "MISMATCH"),
            ("mismatches_count", 1),
            ("mismatches", [{"pc": 1}]),
            ("mismatch_description", "wrong"),
        ]:
            with self.subTest(key=key, value=value):
                self.write(self.report, {**self.good, key: value})
                with self.assertRaises(ValueError):
                    read_tandem_report(self.report)

    def test_missing_malformed_or_symlink_report_rejected(self):
        with self.assertRaises(FileNotFoundError):
            read_tandem_report(self.report)
        self.write(self.report, [])
        with self.assertRaises(ValueError):
            read_tandem_report(self.report)
        link = self.root / "link"
        link.symlink_to(self.report)
        with self.assertRaises(ValueError):
            read_tandem_report(link)

    def test_modes_use_distinct_paths(self):
        self.assertNotEqual(
            elaboration_directory(self.root, "target", CompMode.rtl),
            elaboration_directory(self.root, "target", CompMode.rtl, True),
        )
        self.assertNotEqual(
            simulation_directory(self.root, "target", "test", CompMode.rtl),
            simulation_directory(self.root, "target", "test", CompMode.rtl, True),
        )
        self.assertNotEqual(
            batch.report_path(self.root, "target", batch.Simulator.verilator, "a.yml"),
            batch.report_path(
                self.root, "target", batch.Simulator.verilator, "a.yml", True
            ),
        )

    def test_manifest_mode_mismatch_rejected(self):
        sw, hw = self.root / "sw", self.root / "hw"
        self.write(
            sw / "cook_manifest.yml",
            dict(recipe="sw-compile", options=dict(target="t", test_name="n")),
        )
        self.write(
            hw / "cook_manifest.yml",
            dict(
                recipe="verilator-testharness-comp",
                options=dict(
                    target="t",
                    comp_mode="rtl",
                    trace_mode="notrace",
                    tandem_enabled=False,
                ),
            ),
        )
        with self.assertRaises(ValueError):
            check_manifests(
                target="t",
                test_name="n",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                compile_dir=sw,
                elab_dir=hw,
                tandem_enabled=True,
            )

    def test_failed_preflight_removes_stale_success(self):
        with chdir(self.root):
            path = (
                simulation_directory(self.root, "t", "n", CompMode.rtl) / "result.yml"
            )
            self.write(path, dict(status="PASS"))
            with self.assertRaises(ValueError):
                run_test(
                    target="t",
                    test_name="n",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=True,
                    interactive_gui=False,
                )
            self.assertFalse(path.exists())

    def test_nonzero_compiler_is_failure_even_with_output(self):
        artifact = self.root / "bad.elf"
        command = [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys; Path(sys.argv[1]).touch(); sys.exit(3)",
            str(artifact),
        ]
        with self.assertRaises(typer.Exit):
            run_compile_tool(command, self.root / "compile.log", True)
        self.assertTrue(artifact.exists())

    def test_wall_clock_timeout_without_output(self):
        code, timed_out = run_logged_process(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=self.root,
            env=os.environ.copy(),
            log=self.root / "timeout.log",
            timeout=0.1,
        )
        self.assertEqual((code, timed_out), (124, True))

    def test_success_text_does_not_override_process_failure(self):
        passed, detail = run_testharness_and_trace(
            command=[
                sys.executable,
                "-c",
                "import sys; print('*** SUCCESS *** (tohost = 0)'); sys.exit(7)",
            ],
            output_dir=self.root,
            env=os.environ.copy(),
            spike_install=self.root,
            compiler_isa="rv32im",
            timeout=5,
            tandem_enabled=False,
        )
        self.assertFalse(passed)
        self.assertIn("returned 7", detail)

    def test_live_cannot_pass_without_native_report(self):
        passed, detail = run_testharness_and_trace(
            command=[sys.executable, "-c", "print('*** SUCCESS *** (tohost = 0)')"],
            output_dir=self.root,
            env=os.environ.copy(),
            spike_install=self.root,
            compiler_isa="rv32im",
            timeout=5,
            tandem_enabled=True,
        )
        self.assertFalse(passed)
        self.assertIn("Live tandem evidence failed", detail)

    def test_batch_continues_and_refuses_failed_run_receipt(self):
        seen = []

        def fake(**kwargs):
            name = kwargs["test_name"]
            seen.append(name)
            self.write(
                simulation_directory(self.root, "t", name, CompMode.rtl, True)
                / "result.yml",
                dict(
                    target="t",
                    test_name=name,
                    status="PASS",
                    detail="ok",
                    iss_enabled=False,
                    tandem_enabled=True,
                ),
            )
            if name == "bad":
                raise typer.Exit(code=1)

        with chdir(self.root), patch.object(
            batch, "verilator_testharness_run", side_effect=fake
        ):
            results = batch.run_entries(
                ["bad", "good"],
                target="t",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                iss_enabled=False,
                quiet=True,
                tandem_enabled=True,
            )
        self.assertEqual(seen, ["bad", "good"])
        self.assertEqual([case["status"] for case in results], ["FAIL", "PASS"])

    def test_iteration_and_disabled_entry_selection(self):
        self.write(
            self.report,
            dict(
                testlist=[dict(test="a", iterations=2), dict(test="off", iterations=0)]
            ),
        )
        self.assertEqual(batch.enabled_tests(self.report), ["a_0", "a_1"])
        self.write(self.report, dict(testlist=[dict(test="a", iterations=True)]))
        with self.assertRaises(ValueError):
            batch.enabled_tests(self.report)

    def test_legacy_lists_keep_enabled_counts(self):
        for profile, count in (("rv32", 104), ("rv64", 193)):
            with self.subTest(profile=profile):
                config, lists = materialize(profile, self.root / profile)
                self.assertEqual(len(batch.enabled_tests(Path(lists["basic"]))), 6)
                self.assertEqual(len(batch.enabled_tests(Path(lists["arch"]))), count)


if __name__ == "__main__":
    unittest.main()
