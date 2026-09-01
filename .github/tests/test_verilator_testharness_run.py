# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from contextlib import contextmanager
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

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

from flows.recipes import verilator_testharness_run as RECIPE  # noqa: E402
from flows.utils.manifest import MANIFEST_NAME, write_manifest  # noqa: E402
from flows.utils.utils import CompMode, TraceMode  # noqa: E402


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def prepare_run_tree(root: Path, test_name: str = "hello-world") -> tuple[Path, Path]:
    target = "cv32a60x"
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
    (compile_dir / f"{test_name}.add_tohost").write_text("80001000\n", encoding="utf-8")
    write_manifest(
        compile_dir,
        "sw-compile",
        {"target": target, "test_name": test_name},
        quiet=True,
    )

    elab_dir = RECIPE.elaboration_directory(root, target, CompMode.rtl)
    elab_dir.mkdir(parents=True)
    binary = RECIPE.testharness_binary(root, target, CompMode.rtl)
    binary.touch()
    write_manifest(
        elab_dir,
        "verilator-testharness-comp",
        {
            "target": target,
            "comp_mode": CompMode.rtl,
            "trace_mode": TraceMode.notrace,
            "stats": False,
        },
        quiet=True,
    )
    return compile_dir, elab_dir


class VerilatorTestHarnessRunTest(unittest.TestCase):
    def test_public_interface_matches_the_proposed_run_recipe(self) -> None:
        parameters = inspect.signature(RECIPE.verilator_testharness_run).parameters
        self.assertEqual(
            list(parameters),
            [
                "target",
                "test_name",
                "comp_mode",
                "trace_mode",
                "iss_enabled",
                "interactive_gui",
                "quiet",
            ],
        )
        self.assertFalse(parameters["iss_enabled"].default.default)
        self.assertFalse(parameters["interactive_gui"].default.default)

    def test_run_command_invokes_the_compiled_binary_directly(self) -> None:
        binary = Path("/build/Variane_testharness")
        elf = Path("/build/hello-world.elf")
        command = RECIPE.testharness_command(
            binary,
            elf,
            target="cv32a60x",
            spike_yaml=Path("/repo/config/target/cv32a60x/spike.yaml"),
            tohost="80001000",
            trace_mode=TraceMode.fast,
        )

        self.assertEqual(command[0], str(binary))
        self.assertIn("--vcd", command)
        self.assertIn(str(elf), command)
        self.assertLess(command.index("--seed"), command.index(str(elf)))
        self.assertIn("+tohost_addr=80001000", command)
        self.assertIn("+core_name=cv32a60x", command)
        self.assertTrue(
            all(
                argument.startswith("+")
                for argument in command[command.index(str(elf)) + 1 :]
            )
        )
        self.assertNotIn("make", command)
        self.assertFalse(any("cva6.py" in argument for argument in command))

    def test_log_requires_an_explicit_success_without_failure_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "testharness.log"
            log.write_text(
                "hello-world *** SUCCESS *** (tohost = 0) after 10 cycles\n",
                encoding="utf-8",
            )
            self.assertTrue(RECIPE.testharness_log_passed(log)[0])

            log.write_text(
                "UVM_FATAL\nhello-world *** SUCCESS *** (tohost = 0)\n",
                encoding="utf-8",
            )
            self.assertFalse(RECIPE.testharness_log_passed(log)[0])

    def test_comparison_rejects_failure_and_zero_match_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "iss_regr.log"
            report.write_text("[PASSED]: 24 matched\n", encoding="utf-8")
            self.assertTrue(RECIPE.comparison_report_passed(report)[0])

            report.write_text("[PASSED]: 0 matched\n", encoding="utf-8")
            self.assertFalse(RECIPE.comparison_report_passed(report)[0])

            report.write_text("[FAILED]: mismatch\n", encoding="utf-8")
            self.assertFalse(RECIPE.comparison_report_passed(report)[0])

    def test_nonzero_child_is_not_reported_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            return_code, timed_out = RECIPE.run_logged_process(
                [sys.executable, "-c", "raise SystemExit(7)"],
                cwd=root,
                env=os.environ.copy(),
                log=root / "child.log",
                timeout=5,
            )

        self.assertEqual(return_code, 7)
        self.assertFalse(timed_out)

    def test_standalone_spike_uses_target_configuration_without_dtb_override(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike_yaml = root / "spike.yaml"
            spike_yaml.touch()
            with (
                patch.object(
                    RECIPE,
                    "run_logged_process",
                    return_value=(0, False),
                ) as run_process,
                patch.object(RECIPE, "filter_spike_log"),
            ):
                passed, detail = RECIPE.run_standalone_spike(
                    spike=root / "spike",
                    elf=root / "hello-world.elf",
                    compiler_isa="rv32imc",
                    privilege="msu",
                    spike_yaml=spike_yaml,
                    simulation_dir=root,
                    env=os.environ.copy(),
                    timeout=10,
                )

        command = run_process.call_args.args[0]
        self.assertTrue(passed)
        self.assertEqual(detail, "Spike completed")
        self.assertIn("--disable-dtb", command)
        self.assertEqual(command[command.index("--param-file") + 1], str(spike_yaml))

    def test_manifest_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compile_dir, elab_dir = prepare_run_tree(root)
            manifest_path = elab_dir / MANIFEST_NAME
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest["options"]["target"] = "cv32a65x"
            manifest_path.write_text(
                yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
            )

            with self.assertRaises(RECIPE.typer.Exit):
                RECIPE.check_manifests(
                    target="cv32a60x",
                    test_name="hello-world",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    compile_dir=compile_dir,
                    elab_dir=elab_dir,
                )

    def test_run_without_iss_stops_after_testharness_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_run_tree(root)
            run_spike = patch.object(RECIPE, "run_standalone_spike")
            with (
                working_directory(root),
                patch.object(
                    RECIPE,
                    "runtime_environment",
                    return_value=(os.environ.copy(), root / "spike"),
                ),
                patch.object(
                    RECIPE,
                    "run_testharness_and_trace",
                    return_value=(True, "TestHarness and trace completed"),
                ),
                run_spike as standalone,
            ):
                passed, detail, output_dir = RECIPE.run_test(
                    target="cv32a60x",
                    test_name="hello-world",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=False,
                    interactive_gui=False,
                )

        self.assertTrue(passed)
        self.assertIn("trace completed", detail)
        self.assertEqual(output_dir.name, "hello-world")
        standalone.assert_not_called()

    def test_iss_result_is_required_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_run_tree(root)
            with (
                working_directory(root),
                patch.object(
                    RECIPE,
                    "runtime_environment",
                    return_value=(os.environ.copy(), root / "spike"),
                ),
                patch.object(
                    RECIPE,
                    "run_testharness_and_trace",
                    return_value=(True, "TestHarness and trace completed"),
                ),
                patch.object(
                    RECIPE,
                    "run_standalone_spike",
                    return_value=(True, "Spike completed"),
                ) as spike,
                patch.object(
                    RECIPE,
                    "postprocess_and_compare",
                    return_value=(False, "comparison failed"),
                ) as compare,
            ):
                passed, detail, _ = RECIPE.run_test(
                    target="cv32a60x",
                    test_name="hello-world",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=True,
                    interactive_gui=False,
                    timeout=37,
                )

        self.assertFalse(passed)
        self.assertEqual(detail, "comparison failed")
        self.assertEqual(spike.call_args.kwargs["timeout"], 37)
        compare.assert_called_once()

    def test_top_level_failure_is_nonzero_and_writes_a_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with (
                patch.object(
                    RECIPE,
                    "run_test",
                    return_value=(False, "simulation failed", output_dir),
                ),
                self.assertRaises(RECIPE.typer.Exit) as raised,
            ):
                RECIPE.verilator_testharness_run(
                    target="cv32a60x",
                    test_name="hello-world",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=False,
                    interactive_gui=False,
                    quiet=True,
                )

            manifest = yaml.safe_load(
                (output_dir / MANIFEST_NAME).read_text(encoding="utf-8")
            )

        self.assertEqual(raised.exception.exit_code, 1)
        self.assertEqual(manifest["recipe"], "verilator-testharness-run")

    def test_path_like_test_name_is_rejected_before_cleanup(self) -> None:
        root = Path("/repo")
        with self.assertRaisesRegex(ValueError, "Invalid test name"):
            RECIPE.simulation_directory(
                root,
                "cv32a60x",
                "../victim",
                CompMode.rtl,
            )


if __name__ == "__main__":
    unittest.main()
