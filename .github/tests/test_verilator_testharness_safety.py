# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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

from flows.recipes import testharness_run_testlist as DISPATCHER  # noqa: E402
from flows.recipes import verilator_testharness_comp as COMPILER  # noqa: E402
from flows.recipes import verilator_testharness_run as RUNNER  # noqa: E402
from flows.utils.utils import TraceMode  # noqa: E402


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
    def test_compile_command_invokes_verilator_directly(self) -> None:
        root = Path("/repo")
        command = COMPILER.build_command(
            repo_dir=root,
            target="cv32a60x_axi",
            tandem_enabled=True,
            trace_mode=TraceMode.compact,
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
            run_options=["+max-cycles=2000000"],
        )

        self.assertEqual(command[0], str(binary))
        self.assertIn("--vcd", command)
        self.assertIn(str(elf), command)
        self.assertIn("+tohost_addr=80001000", command)
        self.assertIn("+max-cycles=2000000", command)
        self.assertNotIn("make", command)
        self.assertFalse(any("cva6.py" in argument for argument in command))

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
            binary = RUNNER.verilator_binary(root, target, True)
            binary.parent.mkdir(parents=True)
            binary.touch()

            with working_directory(root):
                result = RUNNER.run_test(
                    target=target,
                    test_name=test_name,
                    tandem_enabled=True,
                    iss_enabled=True,
                    iss_timeout=500,
                    seed="1",
                    trace_mode=TraceMode.notrace,
                    run_options=[],
                )

        self.assertFalse(result.passed)
        self.assertIn("Missing Cook software output", result.detail)

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

            with (
                working_directory(root),
                patch.object(DISPATCHER, "run_test", return_value=failed),
                patch.object(DISPATCHER.Report, "dump"),
                self.assertRaises(DISPATCHER.typer.Exit) as raised,
            ):
                DISPATCHER.testharness_run_testlist(
                    simulator=DISPATCHER.Simulator.verilator,
                    target="cv32a60x_axi",
                    testlist=str(testlist.relative_to(root)),
                    test_name=None,
                    tandem_enabled=True,
                    iss_enabled=True,
                    iss_timeout=500,
                    seed="1",
                    trace_mode=TraceMode.notrace,
                    run_options=[],
                    quiet=True,
                )
        self.assertEqual(raised.exception.exit_code, 1)

    def test_trace_parser_accepts_old_and_cycle_logs(self) -> None:
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
        self.assertIsNotNone(parser.CORE_RE.match(instruction))
        self.assertIsNotNone(parser.CORE_RE.match("        79 | " + instruction))
        marker = "core   0: 0x0000000080000000 (0x0000a835) DASM(0000a835)"
        self.assertIsNotNone(parser.END_TRAMPOLINE_RE.match("       105 | " + marker))


if __name__ == "__main__":
    unittest.main()
