# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Orchestration contracts; expected failures are not DUT acceptance tests."""

from contextlib import chdir
import copy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import typer
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flows.utils.testharness import (
    build_directory,
    check_manifests,
    prepare_spike_config,
    read_tandem_report,
    run_test,
    run_testharness_and_trace,
    simulation_directory,
)
from flows.utils.autocompletion import CompMode, TraceMode
from flows.recipes.testharness_run_testlist import testharness_run_testlist, Simulator
from flows.recipes.verilator_testharness_run import verilator_testharness_run
from flows.recipes.verilator_testharness_comp import verilator_testharness_comp
from prepare_stage1 import materialize, names
from check_native_failures import has_instruction_divergence
from flows.utils.logged_process import run_logged_process


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.native = dict(
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
        path.write_text(yaml.safe_dump(data))

    def test_native_requires_strict_nonzero_comparison(self):
        path = self.root / "native.yml"
        self.write(path, self.native)
        self.assertEqual(read_tandem_report(path), self.native)
        for key, value in (
            ("instr_count", 0),
            ("instr_count", True),
            ("exit_code", False),
            ("exit_code", 1),
            ("exit_cause", "MISMATCH"),
            ("mismatches_count", 1),
            ("mismatches", [{}]),
            ("mismatch_description", "wrong"),
        ):
            with self.subTest(key=key, value=value):
                self.write(path, dict(self.native, **{key: value}))
                with self.assertRaises(ValueError):
                    read_tandem_report(path)

    def test_native_missing_and_symlink_rejected(self):
        with self.assertRaises(OSError):
            read_tandem_report(self.root / "absent")
        self.write(self.root / "real", self.native)
        (self.root / "link").symlink_to(self.root / "real")
        with self.assertRaises(ValueError):
            read_tandem_report(self.root / "link")

    def test_forced_failure_wins_over_success_text(self):
        for result in ((143, False), (124, True), (1, False)):
            with self.subTest(result=result):
                with patch(
                    "flows.utils.testharness.run_logged_process", return_value=result
                ):
                    passed, detail = run_testharness_and_trace(
                        command=["unused"],
                        output_dir=self.root,
                        env={},
                        spike_install=self.root,
                        compiler_isa="rv32imc",
                        timeout=1,
                        tandem_enabled=True,
                    )
                self.assertFalse(passed)

    def test_zero_exit_without_report_is_not_live_pass(self):
        (self.root / "testharness.log").write_text("*** SUCCESS *** (tohost = 0)")
        with patch(
            "flows.utils.testharness.run_logged_process", return_value=(0, False)
        ):
            passed, _ = run_testharness_and_trace(
                command=["unused"],
                output_dir=self.root,
                env={},
                spike_install=self.root,
                compiler_isa="rv32imc",
                timeout=1,
                tandem_enabled=True,
            )
        self.assertFalse(passed)

    def test_real_process_timeout_is_reaped_and_recorded(self):
        code, timed_out = run_logged_process(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            cwd=self.root,
            env=os.environ.copy(),
            log=self.root / "timeout.log",
            timeout=0.1,
        )
        self.assertEqual((code, timed_out), (124, True))

    def test_failed_compiler_cannot_accept_leftover_binary(self):
        module = "flows.recipes.verilator_testharness_comp"
        (self.root / "tools/spike/lib").mkdir(parents=True)
        directory = self.root / "build/t/elab/sim_rtl_verilator_testharness"

        def compiler(*, cmd, report, **kwargs):
            if "--version" in cmd:
                return "Verilator test"
            self.assertIs(kwargs["check"], True)
            (directory / "Variane_testharness").write_text("partial build")
            (directory / "compilation.log").write_text("compiler exited 1")
            report.error("Command failed (1)")
            return ""

        with chdir(self.root), patch(
            module + ".shutil.which", return_value="unused"
        ), patch(
            module + ".read_config_or_exit_testbench_cfg",
            return_value=SimpleNamespace(value="axi"),
        ), patch(
            module + ".run_cmd", side_effect=compiler
        ), self.assertRaises(
            typer.Exit
        ):
            verilator_testharness_comp(
                target="t",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                stats=False,
                jobs=1,
                tandem_enabled=False,
                quiet=True,
            )
        self.assertFalse((directory / "cook_manifest.yml").exists())
        self.assertEqual(
            yaml.safe_load((directory / "cook_report.yml").read_text())["status"],
            "fail",
        )

    def test_stale_success_invalidated_before_missing_prerequisites(self):
        with chdir(self.root):
            output = simulation_directory(self.root, "t", "n", CompMode.rtl, True)
            for name in ("result.yml", "cook_manifest.yml", "cook_report.yml"):
                self.write(output / name, {"status": "PASS"})
            with self.assertRaises(ValueError):
                run_test(
                    target="t",
                    test_name="n",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=False,
                    interactive_gui=False,
                    tandem_enabled=True,
                )
            self.assertFalse(
                any(
                    (output / name).exists()
                    for name in ("result.yml", "cook_manifest.yml", "cook_report.yml")
                )
            )

    def test_target_yaml_bytes_preserved(self):
        source = self.root / "config/target/t/spike.yaml"
        self.write(
            source, {"spike_param_tree": {"core_configs": [{"pmpregions_writable": 8}]}}
        )
        snapshot = prepare_spike_config(self.root, "t", self.root)
        self.assertEqual(snapshot.read_bytes(), source.read_bytes())

    def test_prerequisites_require_passing_reports_and_matching_live_mode(self):
        software, hardware = self.root / "compile", self.root / "elab"
        for directory, recipe, options in (
            (software, "sw-compile", dict(target="t", test_name="n")),
            (
                hardware,
                "verilator-testharness-comp",
                dict(target="t", comp_mode="rtl", tandem_enabled=True),
            ),
        ):
            self.write(
                directory / "cook_manifest.yml", dict(recipe=recipe, options=options)
            )
            self.write(
                directory / "cook_report.yml", dict(recipe=recipe, status="pass")
            )
        arguments = dict(
            target="t",
            test_name="n",
            comp_mode=CompMode.rtl,
            trace_mode=TraceMode.notrace,
            compile_dir=software,
            elab_dir=hardware,
            tandem_enabled=True,
        )
        check_manifests(**arguments)
        with self.assertRaises(ValueError):
            check_manifests(**dict(arguments, tandem_enabled=False))
        self.write(
            software / "cook_report.yml", dict(recipe="sw-compile", status="fail")
        )
        with self.assertRaises(ValueError):
            check_manifests(**arguments)

    def test_invalid_timeout_cannot_leave_stale_receipt(self):
        with chdir(self.root):
            directory = simulation_directory(self.root, "t", "n", CompMode.rtl, True)
            self.write(directory / "result.yml", dict(status="PASS"))
            with self.assertRaises(typer.Exit):
                verilator_testharness_run(
                    target="t",
                    test_name="n",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    interactive_gui=False,
                    sim_timeout=0,
                    run_name=None,
                    tandem_enabled=True,
                    quiet=True,
                )
            self.assertFalse((directory / "result.yml").exists())
            self.assertEqual(
                yaml.safe_load((directory / "cook_report.yml").read_text())["status"],
                "fail",
            )

    def test_missing_child_report_fails_batch_and_continues(self):
        path = self.root / "list.yml"
        self.write(path, {"testlist": [{"test": "a"}, {"test": "b"}]})
        with chdir(self.root), patch(
            "flows.recipes.testharness_run_testlist.verilator_testharness_run"
        ) as child, self.assertRaises(typer.Exit):
            testharness_run_testlist(
                simulator=Simulator.verilator,
                target="t",
                testlist=str(path),
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                sim_timeout=2,
                tandem_enabled=True,
                quiet=True,
            )
        self.assertEqual(child.call_count, 2)
        report = yaml.safe_load(
            next(self.root.glob("build/**/cook_report.yml")).read_text()
        )
        self.assertEqual(report["status"], "fail")
        rows = next(m["data"] for m in report["metrics"] if m["name"] == "Test results")
        self.assertEqual([r["status"] for r in rows], ["fail", "fail"])

    def test_missing_target_yaml_has_explicit_provenance(self):
        self.assertIsNone(prepare_spike_config(self.root, "t", self.root))
        self.assertEqual(
            yaml.safe_load((self.root / "spike-config-source.yml").read_text()),
            {"mode": "rtl-derived"},
        )

    def test_path_and_symlink_escape_rejected(self):
        for part in ("..", "../outside", "/tmp/outside", ""):
            with self.assertRaises(ValueError):
                build_directory(self.root, part)
        (self.root / "build").symlink_to(self.root / "elsewhere")
        with self.assertRaises(ValueError):
            build_directory(self.root, "t")

    def test_invalid_testlists_and_disabled_entries(self):
        self.assertEqual(
            names(
                {
                    "testlist": [
                        {"test": "a", "iterations": 2},
                        {"test": "b", "iterations": 0},
                    ]
                }
            ),
            ["a_0", "a_1"],
        )
        for entries in (
            [{"test": "a", "iterations": True}],
            [{"test": "../bad"}],
            [{"test": "a"}, {"test": "a"}],
            [{"test": "a", "iterations": -1}],
            [],
        ):
            with self.assertRaises(ValueError):
                names({"testlist": entries})

    def test_all_declared_suites_have_reviewed_counts(self):
        config = yaml.safe_load(Path(".github/cook/stage1.yml").read_text())
        for selection in ("profiles", "diagnostics", "pilots"):
            for profile in config[selection]:
                with self.subTest(selection=selection, profile=profile):
                    conf, lists = materialize(profile, self.root / profile, selection)
                    self.assertEqual(set(lists), set(conf["suites"]))
                    for suite, path in lists.items():
                        self.assertEqual(
                            len(names(yaml.safe_load(Path(path).read_text()))),
                            conf["suites"][suite]["enabled"],
                        )

    def test_batch_preflight_rejects_bool_iterations(self):
        path = self.root / "list.yml"
        self.write(path, {"testlist": [{"test": "a", "iterations": True}]})
        with chdir(self.root), self.assertRaises(typer.Exit):
            testharness_run_testlist(
                simulator=Simulator.verilator,
                target="t",
                testlist=str(path),
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                sim_timeout=2,
                tandem_enabled=True,
                quiet=True,
            )
        reports = list(self.root.glob("build/**/cook_report.yml"))
        self.assertEqual(len(reports), 1)
        self.assertEqual(yaml.safe_load(reports[0].read_text())["status"], "fail")

    def test_native_injection_requires_divergent_operands(self):
        data = {
            "mismatches": [
                {
                    "core": {"insn": 1, "pc_rdata": 2},
                    "reference_model": {"insn": 3, "pc_rdata": 2},
                }
            ]
        }
        self.assertTrue(has_instruction_divergence(data))
        with self.assertRaises(ValueError):
            has_instruction_divergence({"mismatches": []})


if __name__ == "__main__":
    unittest.main()
