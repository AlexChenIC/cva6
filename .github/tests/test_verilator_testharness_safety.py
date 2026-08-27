# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TEST_CONFIG_DIRECTORY = tempfile.TemporaryDirectory()
unittest.addModuleCleanup(TEST_CONFIG_DIRECTORY.cleanup)
TEST_CONFIG_PATH = Path(TEST_CONFIG_DIRECTORY.name)
(TEST_CONFIG_PATH / "compiler.yml").write_text(
    "test_toolchain:\n"
    "  TOOLS_PATH: /tmp\n"
    "  CLANG: null\n"
    "  GCC: gcc\n"
    "  OBJDUMP: objdump\n"
    "  NM: nm\n"
    "  TARGET_TOOLCHAIN: riscv32-unknown-elf\n",
    encoding="utf-8",
)
(TEST_CONFIG_PATH / "techno.yml").write_text("{}\n", encoding="utf-8")
os.environ["CONFIG_DIR"] = str(TEST_CONFIG_PATH)

from flows.recipes import testharness_common as COMMON  # noqa: E402
from flows.recipes import testharness_run_testlist as DISPATCHER  # noqa: E402
from flows.recipes import verilator_testharness_comp as COMPILER  # noqa: E402
from flows.recipes import verilator_testharness_run as RUNNER  # noqa: E402
from flows.utils.utils import CompMode, TraceMode  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class VerilatorTestHarnessSafetyTest(unittest.TestCase):
    def test_public_interfaces_use_shared_cook_modes(self) -> None:
        compile_parameters = inspect.signature(
            COMPILER.verilator_testharness_comp
        ).parameters
        run_parameters = inspect.signature(
            RUNNER.verilator_testharness_run
        ).parameters
        testlist_parameters = inspect.signature(
            DISPATCHER.testharness_run_testlist
        ).parameters

        self.assertLess(
            list(compile_parameters).index("comp_mode"),
            list(compile_parameters).index("trace_mode"),
        )
        self.assertIn("stats", compile_parameters)
        self.assertLess(
            list(run_parameters).index("comp_mode"),
            list(run_parameters).index("trace_mode"),
        )
        self.assertIn("interactive_gui", run_parameters)
        self.assertEqual(run_parameters["iss_enabled"].default.default, False)
        self.assertIn("comp_mode", testlist_parameters)
        self.assertIn("trace_mode", testlist_parameters)
        self.assertEqual(testlist_parameters["iss_enabled"].default.default, False)

    def test_unsupported_verilator_modes_fail_explicitly(self) -> None:
        for comp_mode in (
            CompMode.coverage,
            CompMode.gate_wc_timing,
            CompMode.gate_wc_power,
        ):
            with self.assertRaisesRegex(ValueError, "only rtl"):
                COMMON.validate_verilator_options(
                    comp_mode=comp_mode, trace_mode=TraceMode.notrace
                )

        with self.assertRaisesRegex(ValueError, "Interactive GUI"):
            COMMON.validate_verilator_options(
                comp_mode=CompMode.rtl, trace_mode=TraceMode.gui
            )
        with self.assertRaisesRegex(ValueError, "perf tracer"):
            COMMON.validate_verilator_options(
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                stats=True,
            )

    def test_tandem_requires_iss_enabled(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires --iss-enabled"):
            COMMON.validate_iss_options(
                iss_enabled=False, tandem_enabled=True
            )
        COMMON.validate_iss_options(iss_enabled=True, tandem_enabled=True)
        COMMON.validate_iss_options(iss_enabled=False, tandem_enabled=False)

    def test_build_manifest_is_the_compile_run_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            build_dir = Path(directory)
            COMMON.write_build_manifest(
                build_dir,
                target="cv32a60x_axi",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.fast,
                tandem_enabled=True,
            )
            COMMON.require_matching_build(
                build_dir,
                target="cv32a60x_axi",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.fast,
                tandem_enabled=True,
            )
            manifest = build_dir / COMMON.BUILD_MANIFEST
            manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_data["verilator_version"] = "5.050"
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
            COMMON.require_matching_build(
                build_dir,
                target="cv32a60x_axi",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.fast,
                tandem_enabled=True,
            )
            with self.assertRaisesRegex(ValueError, "do not match"):
                COMMON.require_matching_build(
                    build_dir,
                    target="cv32a60x_axi",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.compact,
                    tandem_enabled=True,
                )

    def test_compile_command_invokes_verilator_directly(self) -> None:
        root = Path("/repo")
        command = COMPILER.build_command(
            repo_dir=root,
            target="cv32a60x_axi",
            comp_mode=CompMode.rtl,
            tandem_enabled=True,
            trace_mode=TraceMode.compact,
            stats=False,
            jobs=4,
            verilator="/tools/verilator/bin/verilator",
            riscv=Path("/tools/riscv"),
            verilator_install=Path("/tools/verilator"),
            spike_install=Path("/tools/spike"),
        )

        self.assertEqual(command[0], "/tools/verilator/bin/verilator")
        self.assertIn("--build", command)
        self.assertIn(str(root / "config/target/cv32a60x_axi/Flist.cva6"), command)
        self.assertIn(
            str(root / "verif/tb/core/Flist.verilator_testharness"), command
        )
        self.assertIn(str(root / "corev_apu/tb/common/spike.sv"), command)
        self.assertIn("+define+SPIKE_TANDEM", command)
        self.assertTrue(any("-lz" in argument for argument in command))
        package = str(root / "corev_apu/tb/ariane_axi_pkg.sv")
        tandem = str(root / "verif/tb/core/uvma_core_cntrl_pkg.sv")
        filelist = str(root / "verif/tb/core/Flist.verilator_testharness")
        self.assertLess(command.index(package), command.index(tandem))
        self.assertLess(command.index(tandem), command.index(filelist))
        self.assertNotIn("make", command)
        self.assertFalse(any("cva6.py" in argument for argument in command))

    def test_run_command_invokes_testharness_directly(self) -> None:
        binary = Path("/build/Variane_testharness")
        elf = Path("/build/example.elf")
        command = RUNNER.testharness_command(
            binary,
            elf,
            target="cv32a60x_axi",
            spike_yaml=Path("/repo/config/target/cv32a60x_axi/spike.yaml"),
            tohost="80001000",
            seed="17",
            trace_mode=TraceMode.fast,
            run_options=["+max-cycles=2000000", "+UVM_VERBOSITY=UVM_LOW"],
        )

        self.assertEqual(command[0], str(binary))
        self.assertIn("--vcd", command)
        self.assertIn(str(elf), command)
        self.assertIn("+tohost_addr=80001000", command)
        self.assertIn("+max-cycles=2000000", command)
        self.assertLess(command.index("+max-cycles=2000000"), command.index(str(elf)))
        self.assertGreater(
            command.index("+UVM_VERBOSITY=UVM_LOW"), command.index(str(elf))
        )
        self.assertNotIn("make", command)
        self.assertFalse(any("cva6.py" in argument for argument in command))

    def test_single_test_cli_accepts_the_proposed_interface(self) -> None:
        result = COMMON.TestHarnessResult(
            "rv32ui-p-add_0",
            "rv32imc",
            "ilp32",
            "verilator+spike-tandem",
            True,
            "live Spike tandem completed",
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with (
                patch.object(RUNNER, "run_test", return_value=result) as run_test,
                patch.object(
                    RUNNER,
                    "test_simulation_directory",
                    return_value=output,
                ),
            ):
                cli = CliRunner().invoke(
                    RUNNER.app,
                    [
                        "--target",
                        "cv32a60x_axi",
                        "--testname",
                        "rv32ui-p-add_0",
                        "--comp-mode",
                        "rtl",
                        "--trace-mode",
                        "notrace",
                        "--tandem-enabled",
                        "--iss-enabled",
                    ],
                )

        self.assertEqual(cli.exit_code, 0, cli.output)
        self.assertEqual(run_test.call_args.kwargs["comp_mode"], CompMode.rtl)
        self.assertEqual(run_test.call_args.kwargs["trace_mode"], TraceMode.notrace)
        self.assertTrue(run_test.call_args.kwargs["iss_enabled"])
        self.assertTrue(run_test.call_args.kwargs["tandem_enabled"])

    def test_tier1_exercises_the_single_test_recipe(self) -> None:
        workflow = (
            REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier1.yml"
        ).read_text(encoding="utf-8")
        runner = (
            REPO_ROOT / ".github/scripts/run-tier-regression.sh"
        ).read_text(encoding="utf-8")

        self.assertEqual(workflow.count("single_test_smoke: hello-world"), 1)
        self.assertIn("TIER_SINGLE_TEST_SMOKE", workflow)
        self.assertEqual(runner.count('./cook.py "${TIER_SINGLE_TEST_SMOKE}"'), 1)
        self.assertEqual(
            runner.count("./cook.py verilator-testharness-run"), 1
        )

    def test_nonzero_child_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            return_code, timed_out = RUNNER.run_logged_process(
                [sys.executable, "-c", "raise SystemExit(7)"],
                cwd=root,
                env=os.environ.copy(),
                log=root / "child.log",
                timeout=5,
            )
        self.assertEqual(return_code, 7)
        self.assertFalse(timed_out)

    def test_tandem_success_with_uvm_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "testharness.log"
            log.write_text(
                "Running binary in tandem mode\n"
                "[SPIKE] Starting 'spike_create'...\n"
                "example.elf *** SUCCESS *** (tohost = 0) after 10 cycles\n",
                encoding="utf-8",
            )
            self.assertEqual(
                RUNNER.testharness_log_passed(log, tandem_enabled=True),
                (True, "live Spike tandem completed"),
            )

            log.write_text(
                "Running binary in tandem mode\n"
                "example.elf *** SUCCESS *** (tohost = 0) after 10 cycles\n",
                encoding="utf-8",
            )
            passed, detail = RUNNER.testharness_log_passed(
                log, tandem_enabled=True
            )
            self.assertFalse(passed)
            self.assertIn("missing live Spike tandem markers", detail)

    def test_tandem_mismatch_overrides_tohost_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "testharness.log"
            log.write_text(
                "Running binary in tandem mode\n"
                "[SPIKE] Starting 'spike_create'...\n"
                "UVM_INFO [spike_tandem] PC Mismatch [REF]: 0x1 [CORE]: 0x2\n"
                "UVM_WARNING [spike_tandem] continuing after mismatch\n"
                "example.elf *** SUCCESS *** (tohost = 0) after 10 cycles\n",
                encoding="utf-8",
            )
            passed, detail = RUNNER.testharness_log_passed(
                log, tandem_enabled=True
            )
            self.assertFalse(passed)
            self.assertIn("tandem mismatch", detail)

    def test_unrelated_uvm_warning_does_not_override_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "testharness.log"
            log.write_text(
                "Running binary in tandem mode\n"
                "[SPIKE] Starting 'spike_create'...\n"
                "UVM_WARNING [unrelated_component] informational warning\n"
                "example.elf *** SUCCESS *** (tohost = 0) after 10 cycles\n",
                encoding="utf-8",
            )
            self.assertTrue(
                RUNNER.testharness_log_passed(log, tandem_enabled=True)[0]
            )

    def test_tandem_trace_requires_a_committed_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "tandem.log"
            log.write_text("core   0: 0x80000000 (0x00000013) nop\n", encoding="utf-8")
            self.assertTrue(RUNNER.tandem_trace_passed(log)[0])

            log.write_text("tandem started\n", encoding="utf-8")
            passed, detail = RUNNER.tandem_trace_passed(log)
            self.assertFalse(passed)
            self.assertIn("no committed instruction", detail)

    def test_boot_pc_check_requires_a_cycle_prefixed_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "verilator.log"
            log.write_text(
                "       105 | core   0: 0x0000000080000000 "
                "(0x00000013) nop\n",
                encoding="utf-8",
            )
            self.assertTrue(RUNNER.boot_pc_reached(log)[0])

            log.write_text(
                "core   0: 0x0000000080000000 (0x00000013) nop\n",
                encoding="utf-8",
            )
            passed, detail = RUNNER.boot_pc_reached(log)
            self.assertFalse(passed)
            self.assertIn("did not reach boot PC", detail)

    def test_missing_tohost_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = "cv32a60x_axi"
            test_name = "example"
            target_dir = root / "config" / "target" / target
            target_dir.mkdir(parents=True)
            (target_dir / "isa.yml").write_text("mabi: ilp32\n", encoding="utf-8")
            (target_dir / "spike.yaml").write_text(
                "spike_param_tree:\n  priv: MSU\n", encoding="utf-8"
            )
            compile_dir = root / "build" / target / "compile" / test_name
            compile_dir.mkdir(parents=True)
            (compile_dir / f"{test_name}.elf").touch()
            (compile_dir / "isa_string").write_text("rv32imc\n", encoding="utf-8")
            binary = RUNNER.verilator_binary(root, target, CompMode.rtl, True)
            binary.parent.mkdir(parents=True)
            binary.touch()

            with working_directory(root):
                result = RUNNER.run_test(
                    target=target,
                    test_name=test_name,
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    tandem_enabled=True,
                    iss_enabled=True,
                    iss_timeout=500,
                    seed="1",
                    run_options=[],
                )

        self.assertFalse(result.passed)
        self.assertIn("Missing Cook software output", result.detail)

    def test_invalid_test_name_cannot_escape_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = (
                root
                / "build/cv32a60x_axi/simulation"
                / "victim/sentinel"
            )
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text("keep\n", encoding="utf-8")

            with working_directory(root):
                result = RUNNER.run_test(
                    target="cv32a60x_axi",
                    test_name="../victim",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    tandem_enabled=True,
                    iss_enabled=True,
                    iss_timeout=500,
                    seed="1",
                    run_options=[],
                )

            self.assertTrue(sentinel.is_file())
            self.assertFalse(result.passed)
            self.assertIn("Invalid test name", result.detail)

    def test_testlist_rejects_path_like_test_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid test name"):
            DISPATCHER.enabled_tests(
                {"testlist": [{"test": "../victim", "iterations": 1}]}, None
            )

    def test_testlist_rejects_path_like_target_before_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            testlist = root / "verif/tests/example.yaml"
            testlist.parent.mkdir(parents=True)
            testlist.write_text(
                "testlist:\n  - test: example\n    iterations: 1\n",
                encoding="utf-8",
            )
            run_test = Mock()

            with (
                working_directory(root),
                patch.dict(
                    DISPATCHER.RUNNERS,
                    {DISPATCHER.Simulator.verilator: run_test},
                    clear=True,
                ),
                self.assertRaises(DISPATCHER.typer.Exit) as raised,
            ):
                DISPATCHER.testharness_run_testlist(
                    simulator=DISPATCHER.Simulator.verilator,
                    target="../../../victim",
                    testlist=str(testlist.relative_to(root)),
                    test_name=None,
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    tandem_enabled=True,
                    iss_enabled=True,
                    iss_timeout=500,
                    seed="1",
                    run_options=[],
                    quiet=True,
                )

            self.assertEqual(raised.exception.exit_code, 1)
            run_test.assert_not_called()

    def test_tandem_and_non_tandem_outputs_are_isolated(self) -> None:
        root = Path("/repo")
        tandem = COMMON.test_simulation_directory(
            root, "cv32a60x_axi", "example_0", CompMode.rtl, True
        )
        standalone = COMMON.test_simulation_directory(
            root, "cv32a60x_axi", "example_0", CompMode.rtl, False
        )
        self.assertNotEqual(tandem, standalone)
        self.assertEqual(tandem.parent.name, "sim_rtl_verilator_testharness_tandem")
        self.assertEqual(standalone.parent.name, "sim_rtl_verilator_testharness")

    def test_standalone_spike_uses_the_requested_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = "cv32a60x_axi"
            test_name = "example"
            target_dir = root / "config" / "target" / target
            target_dir.mkdir(parents=True)
            (target_dir / "isa.yml").write_text("mabi: ilp32\n", encoding="utf-8")
            (target_dir / "spike.yaml").write_text(
                "spike_param_tree:\n  priv: MSU\n", encoding="utf-8"
            )
            compile_dir = root / "build" / target / "compile" / test_name
            compile_dir.mkdir(parents=True)
            (compile_dir / f"{test_name}.elf").touch()
            (compile_dir / "isa_string").write_text("rv32imc\n", encoding="utf-8")
            (compile_dir / f"{test_name}.add_tohost").write_text(
                "80001000\n", encoding="utf-8"
            )
            binary = RUNNER.verilator_binary(root, target, CompMode.rtl, False)
            binary.parent.mkdir(parents=True)
            binary.touch()
            COMMON.write_build_manifest(
                binary.parent,
                target=target,
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                tandem_enabled=False,
            )
            run_spike = Mock(return_value=(False, "probe complete"))

            with (
                working_directory(root),
                patch.object(
                    RUNNER,
                    "_runtime_environment",
                    return_value=(os.environ.copy(), root / "riscv", root / "spike"),
                ),
                patch.object(RUNNER, "run_logged_process", return_value=(0, False)),
                patch.object(
                    RUNNER,
                    "testharness_log_passed",
                    return_value=(True, "TestHarness completed"),
                ),
                patch.object(RUNNER, "_run_spike_dasm", return_value=True),
                patch.object(
                    RUNNER,
                    "boot_pc_reached",
                    return_value=(True, "boot PC reached"),
                ),
                patch.object(RUNNER, "_run_standalone_spike", run_spike),
            ):
                result = RUNNER.run_test(
                    target=target,
                    test_name=test_name,
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    tandem_enabled=False,
                    iss_enabled=True,
                    iss_timeout=37,
                    seed="1",
                    run_options=[],
                )

            self.assertFalse(result.passed)
            self.assertEqual(run_spike.call_args.kwargs["timeout"], 37)

    def test_zero_match_is_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "iss_regr.log"
            report.write_text(
                "[PASSED]: 24 matched\n[PASSED]: 0 matched\n", encoding="utf-8"
            )
            passed, detail = RUNNER.comparison_report_passed(report)
            self.assertFalse(passed)
            self.assertIn("zero-match", detail)

            report.write_text("[PASSED]: 24 matched\n", encoding="utf-8")
            self.assertTrue(RUNNER.comparison_report_passed(report)[0])

    def test_dispatcher_exits_when_a_case_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            testlist = root / "verif/tests/example.yaml"
            testlist.parent.mkdir(parents=True)
            testlist.write_text(
                "testlist:\n  - test: example\n    iterations: 1\n",
                encoding="utf-8",
            )
            failed = RUNNER.TestHarnessResult(
                "example_0", "rv32imc", "ilp32", "verilator", False, "failed"
            )
            run_test = Mock(return_value=failed)

            with (
                working_directory(root),
                patch.dict(
                    DISPATCHER.RUNNERS,
                    {DISPATCHER.Simulator.verilator: run_test},
                    clear=True,
                ),
                patch.object(DISPATCHER.Report, "dump"),
                self.assertRaises(DISPATCHER.typer.Exit) as raised,
            ):
                DISPATCHER.testharness_run_testlist(
                    simulator=DISPATCHER.Simulator.verilator,
                    target="cv32a60x_axi",
                    testlist=str(testlist.relative_to(root)),
                    test_name=None,
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    tandem_enabled=True,
                    iss_enabled=True,
                    iss_timeout=500,
                    seed="1",
                    run_options=[],
                    quiet=True,
                )
        self.assertEqual(raised.exception.exit_code, 1)
        self.assertEqual(run_test.call_args.kwargs["comp_mode"], CompMode.rtl)
        self.assertEqual(run_test.call_args.kwargs["trace_mode"], TraceMode.notrace)
        self.assertTrue(run_test.call_args.kwargs["iss_enabled"])
        self.assertTrue(run_test.call_args.kwargs["tandem_enabled"])

    def test_trace_parser_requires_cycle_prefixed_instruction_lines(self) -> None:
        sim_dir = REPO_ROOT / "verif/sim"
        sys.path.insert(0, str(sim_dir))
        sys.path.insert(0, str(sim_dir / "dv/scripts"))
        with working_directory(sim_dir):
            parser = load_module(
                "verilator_log_to_trace_csv", sim_dir / "verilator_log_to_trace_csv.py"
            )

        instruction = (
            "core   0: 0x0000000000010000 "
            "(0x00100413) addi    s0, zero, 1"
        )
        self.assertIsNone(parser.CORE_RE.match(instruction))
        self.assertIsNotNone(parser.CORE_RE.match("        79 | " + instruction))
        self.assertIsNone(parser.CORE_RE.match("core INTERRUPT 3"))


if __name__ == "__main__":
    unittest.main()
