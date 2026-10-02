# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Orchestration checks, not RTL ISA tests. Expected failures are asserted."""

from contextlib import chdir
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import typer
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flows.recipes import testharness_run_testlist as batch
from flows.recipes.sw_compile import run_compile_tool
from flows.recipes.verilator_testharness_comp import (
    build_command,
    elaboration_directory,
    verilator_testharness_comp,
)
from flows.recipes.verilator_testharness_run import (
    check_manifests,
    read_tandem_report,
    prepare_spike_config,
    run_test,
    run_testharness_and_trace,
    simulation_directory,
    testharness_command,
)
from flows.utils.logged_process import run_logged_process
from flows.utils.utils import CompMode, TraceMode
from prepare_testlists import materialize
from run_tier1 import checked_suite
from check_native_failures import has_instruction_divergence, wait_for_initialization


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

    def test_live_stack_capacity_does_not_change_rtl_only(self):
        for live in (False, True):
            command = build_command(
                repo_dir=self.root,
                target="t",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                stats=False,
                jobs=1,
                verilator="verilator",
                verilator_root=self.root / "verilator",
                riscv=self.root / "riscv",
                spike=self.root / "spike",
                tandem_enabled=live,
            )
            self.assertEqual(
                "-DCVA6_TANDEM_STACK_BYTES=268435456"
                in command[command.index("-CFLAGS") + 1],
                live,
            )
            self.assertEqual("+define+SPIKE_TANDEM=1" in command, live)
            self.assertEqual("-fno-inline-funcs-eager" in command, live)

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

    def test_target_spike_parameters_are_preserved_and_selected(self):
        source = self.root / "config/target/t/spike.yaml"
        self.write(
            source,
            dict(
                spike_param_tree=dict(
                    core_configs=[dict(pmpregions_max=64, pmpregions_writable=0)]
                )
            ),
        )
        snapshot = prepare_spike_config(self.root, "t", self.root)
        self.assertEqual(snapshot.read_bytes(), source.read_bytes())
        self.assertEqual(
            yaml.safe_load((self.root / "spike-config-source.yml").read_text()),
            {
                "mode": "target-yaml",
                "source": "config/target/t/spike.yaml",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
        )
        command = testharness_command(
            Path("binary"),
            Path("elf"),
            target="t",
            tohost="80001000",
            trace_mode=TraceMode.notrace,
            spike_config=snapshot,
        )
        self.assertIn(f"+config_file={snapshot}", command)
        command = testharness_command(
            Path("binary"),
            Path("elf"),
            target="t",
            tohost="80001000",
            trace_mode=TraceMode.notrace,
        )
        self.assertFalse(any(arg.startswith("+config_file=") for arg in command))

    def test_missing_spike_parameters_use_explicit_auto_provenance(self):
        self.assertIsNone(prepare_spike_config(self.root, "t", self.root))
        self.assertEqual(
            yaml.safe_load((self.root / "spike-config-source.yml").read_text()),
            {"mode": "rtl-derived"},
        )

    def test_invalid_spike_parameters_do_not_fall_back_to_auto(self):
        source = self.root / "config/target/t/spike.yaml"
        for data in (None, [], {}, {"spike_param_tree": []}):
            self.write(source, data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                prepare_spike_config(self.root, "t", self.root)
        source.unlink()
        source.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            prepare_spike_config(self.root, "t", self.root)

    def test_native_mismatch_yaml_sibling_operands(self):
        report = yaml.safe_load("""
mismatches:
  - 00000000:
    core:
      pc_rdata: "0000000080000118"
      insn: "0000000000004081"
    reference_model:
      pc_rdata: "0000000080000118"
      insn: "0000000000003097"
""")
        self.assertTrue(has_instruction_divergence(report))
        entry = report["mismatches"][0]
        entry["reference_model"] = dict(entry["core"])
        self.assertFalse(has_instruction_divergence(report))
        entry["reference_model"]["pc_rdata"] = "000000008000011c"
        self.assertTrue(has_instruction_divergence(report))
        del entry["reference_model"]["insn"]
        with self.assertRaises(ValueError):
            has_instruction_divergence(report)
        for entries in (None, [], [None], [{"core": {}, "reference_model": {}}]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                has_instruction_divergence({"mismatches": entries})

    def test_signal_injection_waits_for_initialization(self):
        log = self.root / "startup.log"
        log.write_text("Spike is still initializing\n")
        process = Mock()
        process.poll.return_value = None
        with patch(
            "check_native_failures.time.sleep",
            side_effect=lambda _: log.write_text(
                "TestHarness initialized; starting execution\n"
            ),
        ) as sleep:
            wait_for_initialization(process, log)
            sleep.assert_called_once()
        process.poll.return_value = 1
        with self.assertRaises(ValueError):
            wait_for_initialization(process, log)
        process.poll.return_value = None
        log.write_text("No readiness marker\n")
        with patch("check_native_failures.time.monotonic", side_effect=[0, 31]):
            with self.assertRaises(ValueError):
                wait_for_initialization(process, log)

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

    def test_failed_rebuild_invalidates_old_hardware_manifest(self):
        with chdir(self.root):
            path = (
                elaboration_directory(self.root, "t", CompMode.rtl)
                / "cook_manifest.yml"
            )
            self.write(path, dict(recipe="verilator-testharness-comp"))
            with self.assertRaises(typer.Exit):
                verilator_testharness_comp(
                    target="t",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    stats=False,
                    quiet=True,
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
                config, lists = materialize(
                    profile, self.root / profile, diagnostic=True
                )
                self.assertEqual(len(batch.enabled_tests(Path(lists["basic"]))), 6)
                self.assertEqual(len(batch.enabled_tests(Path(lists["arch"]))), count)

    def test_supported_lists_match_complete_thales_sources(self):
        for profile in ("rv32", "rv64"):
            with self.subTest(profile=profile):
                config, lists = materialize(profile, self.root / profile)
                source = yaml.safe_load(Path(config["basic_source"]).read_text())[
                    "testlist"
                ]
                actual = yaml.safe_load(Path(lists["basic"]).read_text())["testlist"]
                self.assertEqual(list(lists), ["basic"])
                self.assertEqual(len(batch.enabled_tests(Path(lists["basic"]))), 5)
                self.assertEqual(
                    actual,
                    [
                        dict(entry, march=config["march"], mabi=config["mabi"])
                        for entry in source
                    ],
                )
                provenance = yaml.safe_load(
                    (self.root / profile / f"{profile}-provenance.yml").read_text()
                )
                self.assertEqual(provenance["selection"], "profiles")
                self.assertEqual(provenance["renamed_duplicate_invocations"], [])

    def test_supported_scope_drift_is_not_silently_filtered(self):
        import prepare_testlists

        original = prepare_testlists.read

        def changed(path):
            data = original(path)
            if path.name == "base_rv32_p.yaml":
                data["testlist"].append(dict(data["testlist"][0], test="new-case"))
            return data

        with patch.object(prepare_testlists, "read", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "Thales base list changed"):
                materialize("rv32", self.root)

    def test_evidence_reconciliation_rejects_changed_native_result(self):
        with chdir(self.root):
            self.write(Path("list.yml"), dict(testlist=[dict(test="a", iterations=1)]))
            directory = simulation_directory(self.root, "t", "a_0", CompMode.rtl, True)
            self.write(
                directory / "result.yml",
                dict(
                    target="t",
                    test_name="a_0",
                    status="PASS",
                    detail="native ok",
                    tandem_enabled=True,
                    iss_enabled=False,
                ),
            )
            self.write(
                directory / "cook_manifest.yml",
                dict(
                    recipe="verilator-testharness-run",
                    options=dict(
                        target="t",
                        test_name="a_0",
                        comp_mode="rtl",
                        trace_mode="notrace",
                        tandem_enabled=True,
                        iss_enabled=False,
                        interactive_gui=False,
                    ),
                ),
            )
            self.write(directory / "execution.yml", dict(exit_code=0, timed_out=False))
            (directory / "testharness.log").write_text("*** SUCCESS *** (tohost = 0)\n")
            self.write(directory / "testharness.log.yaml", self.good)
            self.write(directory / "spike-config-source.yml", {"mode": "rtl-derived"})
            (directory / "simulation.command.json").write_text('["binary"]')
            output = batch.report_path(
                self.root, "t", batch.Simulator.verilator, "list.yml", True
            )
            batch.write_reports(
                output,
                [dict(test_name="a_0", status="PASS", detail="native ok")],
                dict(
                    target="t",
                    testlist="list.yml",
                    simulator="verilator",
                    comp_mode="rtl",
                    trace_mode="notrace",
                    tandem_enabled=True,
                    iss_enabled=False,
                ),
                True,
            )
            self.assertEqual(checked_suite(self.root, "t", "list.yml")["passed"], 1)
            self.write(
                directory / "testharness.log.yaml", {**self.good, "mismatches_count": 1}
            )
            with self.assertRaises(ValueError):
                checked_suite(self.root, "t", "list.yml")


if __name__ == "__main__":
    unittest.main()
