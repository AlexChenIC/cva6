# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Infrastructure contracts, not processor functional regression cases."""

from contextlib import chdir
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import typer
from typer.testing import CliRunner
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".github/cook"))
from prepare_testlists import materialize, names
from flows.utils.autocompletion import CompMode, TraceMode, UvmVerbosity
from flows.utils.testharness_tandem import (
    read_tandem_report,
    snapshot_spike_config,
    testharness_mode,
)
from flows.recipes import verilator_testharness_run as run_recipe
from flows.recipes import verilator_testharness_comp as comp_recipe
from flows.recipes import testharness_run_testlist as batch_recipe

NATIVE = {
    "exit_cause": "SUCCESS",
    "exit_code": 0,
    "instr_count": 12,
    "csrs_match_count": 1,
    "mismatches_count": 0,
    "mismatches": None,
    "mismatch_description": "",
}


class TestSelection(unittest.TestCase):
    def test_three_profiles_keep_eight_tests_with_explicit_startup(self):
        with tempfile.TemporaryDirectory() as directory, chdir(ROOT):
            for profile in ("rv32-60x", "rv32-65x", "rv64"):
                config, lists = materialize(profile, Path(directory) / profile)
                tests = [
                    entry
                    for path in lists.values()
                    for entry in yaml.safe_load(Path(path).read_text())["testlist"]
                ]
                self.assertEqual(len(tests), 8)
                if profile == "rv64":
                    self.assertEqual(config["environment"], "stage1-integer-m")
                    self.assertTrue(
                        all(
                            "-I.github/cook/env/m/" in entry["gcc_opts"]
                            and "/env/p/" not in entry["gcc_opts"]
                            for entry in tests
                        )
                    )
                    self.assertTrue(
                        all(
                            entry["test"].startswith("rv64ui-m-stage1-")
                            for entry in tests
                        )
                    )
                    for entry in tests:
                        for key in ("gcc_opts", "llvm_opts"):
                            if key not in entry:
                                continue
                            tokens = entry[key].split()
                            self.assertIn("-I.github/cook/env/m/", tokens)
                            self.assertIn(
                                "-I<path_var>/riscv-tests/isa/macros/scalar/", tokens
                            )
                            self.assertTrue(
                                all(
                                    "'" not in token and '"' not in token
                                    for token in tokens
                                )
                            )
                    snapshot = Path(directory) / profile / "riscv_test.h"
                    self.assertEqual(
                        hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                        config["startup_sha256"],
                    )
                    provenance = yaml.safe_load(
                        (snapshot.parent / "provenance.yml").read_text()
                    )
                    self.assertEqual(len(provenance["adaptations"]), 8)
                else:
                    self.assertEqual(config["environment"], "upstream-riscv-tests-p")
                    self.assertTrue(
                        all("/env/p/" in entry["gcc_opts"] for entry in tests)
                    )
                self.assertFalse(
                    any(
                        entry["test"] in ("mcause_warl", "irq_mtval_zero")
                        for entry in tests
                    )
                )

    def test_pilot_is_finite(self):
        with tempfile.TemporaryDirectory() as directory, chdir(ROOT):
            _, lists = materialize("rv32-extra", Path(directory), "pilots")
            self.assertEqual(
                sum(
                    len(names(yaml.safe_load(Path(p).read_text())))
                    for p in lists.values()
                ),
                11,
            )

    def test_bad_iteration_and_names(self):
        for entry in (
            {"test": "../escape"},
            {"test": "x", "iterations": True},
            {"test": "x", "iterations": -1},
        ):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                names({"testlist": [entry]})


class TestNativeReport(unittest.TestCase):
    def test_reject_inactive_or_divergent_native_results(self):
        bad = [
            {"instr_count": 0},
            {"instr_count": True},
            {"mismatches_count": 1},
            {"exit_cause": "TIMEOUT"},
            {"exit_code": 1},
            {"mismatches": [{"core": "wrong"}]},
            {"mismatch_description": "wrong"},
            {"csrs_match_count": "1"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "native.yml"
            path.write_text(yaml.safe_dump(NATIVE))
            self.assertEqual(read_tandem_report(path)["instr_count"], 12)
            for delta in bad:
                with self.subTest(delta=delta):
                    path.write_text(yaml.safe_dump({**NATIVE, **delta}))
                    with self.assertRaises(ValueError):
                        read_tandem_report(path)
            path.unlink()
            with self.assertRaises(OSError):
                read_tandem_report(path)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_text(yaml.safe_dump(NATIVE))
            link = Path(directory) / "link"
            link.symlink_to(source)
            with self.assertRaises(ValueError):
                read_tandem_report(link)

    def test_model_configuration_is_copied_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            source = repo / "config/target/target/spike.yaml"
            source.parent.mkdir(parents=True)
            source.write_text("spike_param_tree:\n  isa: rv64imc\n")
            output = repo / "out"
            output.mkdir()
            snapshot = snapshot_spike_config(repo, "target", output)
            self.assertEqual(snapshot.read_bytes(), source.read_bytes())
            source.unlink()
            self.assertIsNone(snapshot_spike_config(repo, "target", output))


class TestRunVerdict(unittest.TestCase):
    def simulate(self, mode):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            root = Path(directory)
            for subdir, recipe, options in (
                (
                    "compile/case",
                    "sw-compile",
                    {
                        "target": "target",
                        "test_name": "case",
                        "march": "rv32imc",
                        "symbols": {"tohost": "80001000"},
                    },
                ),
                (
                    f"elab/{testharness_mode(True)}",
                    "verilator-testharness-comp",
                    {"target": "target", "comp_mode": "rtl", "tandem_enabled": True},
                ),
            ):
                path = root / "build/target" / subdir
                path.mkdir(parents=True)
                (path / "cook_report.yml").write_text(
                    yaml.safe_dump({"recipe": recipe, "status": "pass"})
                )
                (path / "cook_manifest.yml").write_text(
                    yaml.safe_dump({"recipe": recipe, "options": options})
                )
            (root / "build/target/compile/case/case.elf").touch()
            (
                root
                / "build/target/elab"
                / testharness_mode(True)
                / "Variane_testharness"
            ).touch()

            def fake_run(cmd, *, report, cwd, log_file, **kwargs):
                log_file.write_text("*** SUCCESS *** (tohost = 0) after 20 cycles\n")
                native = copy.deepcopy(NATIVE)
                if mode == "mismatch":
                    native["mismatches_count"] = 1
                if mode != "missing":
                    (cwd / "testharness.log.yaml").write_text(yaml.safe_dump(native))
                if mode in ("timeout", "exit"):
                    report.error(
                        "Command timed out"
                        if mode == "timeout"
                        else "Command failed (2)"
                    )
                return ""

            failure = None
            with patch.object(run_recipe, "run_cmd", side_effect=fake_run):
                try:
                    run_recipe.verilator_testharness_run(
                        target="target",
                        test_name="case",
                        comp_mode=CompMode.rtl,
                        trace_mode=TraceMode.notrace,
                        interactive_gui=False,
                        sim_timeout=10,
                        tandem_enabled=True,
                        run_name=None,
                        quiet=True,
                    )
                except typer.Exit as error:
                    failure = error.exit_code
            report = yaml.safe_load(
                (
                    root
                    / "build/target/simulation"
                    / testharness_mode(True)
                    / "case/cook_report.yml"
                ).read_text()
            )
            return failure, report["status"]

    def test_success_needs_both_rtl_and_native_success(self):
        self.assertEqual(self.simulate("pass"), (None, "pass"))

    def test_success_text_cannot_override_timeout_exit_or_missing_native(self):
        for mode in ("timeout", "exit", "missing", "mismatch"):
            with self.subTest(mode=mode):
                self.assertEqual(self.simulate(mode), (1, "fail"))

    def test_new_boolean_defaults_are_plain_false_for_python_callers(self):
        import inspect

        for function in (
            run_recipe.verilator_testharness_run,
            comp_recipe.verilator_testharness_comp,
            batch_recipe.testharness_run_testlist,
        ):
            self.assertIs(
                inspect.signature(function).parameters["tandem_enabled"].default, False
            )

    def test_cli_options(self):
        for app in (run_recipe.app, comp_recipe.app, batch_recipe.app):
            result = CliRunner().invoke(app, ["--help"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("tandem", result.output)


class TestBatchVerdict(unittest.TestCase):
    def test_failure_is_retained_and_next_test_still_runs(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            testlist = Path(directory) / "tests.yml"
            testlist.write_text(
                yaml.safe_dump(
                    {
                        "testlist": [
                            {"test": "first"},
                            {"test": "second"},
                            {"test": "disabled", "iterations": 0},
                        ]
                    }
                )
            )
            seen = []

            def fake_run(**kwargs):
                seen.append((kwargs["test_name"], kwargs["tandem_enabled"]))
                if kwargs["test_name"] == "first_0":
                    raise typer.Exit(1)

            with patch.object(
                batch_recipe, "verilator_testharness_run", side_effect=fake_run
            ):
                with self.assertRaises(typer.Exit):
                    batch_recipe.testharness_run_testlist(
                        simulator=batch_recipe.Simulator.verilator,
                        target="target",
                        testlist=str(testlist),
                        comp_mode=CompMode.rtl,
                        trace_mode=TraceMode.notrace,
                        sim_timeout=10,
                        tandem_enabled=True,
                        uvm_verbosity=UvmVerbosity.low,
                        quiet=True,
                    )
            self.assertEqual(seen, [("first_0", True), ("second_0", True)])
            report = yaml.safe_load(
                (
                    Path(directory)
                    / "build/target/simulation/testharness_verilator_tests_tandem/cook_report.yml"
                ).read_text()
            )
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["label"], "1/2 PASS")


if __name__ == "__main__":
    unittest.main()
