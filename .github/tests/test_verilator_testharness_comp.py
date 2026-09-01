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
from unittest.mock import Mock, patch

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

from flows.recipes import verilator_testharness_comp as RECIPE  # noqa: E402
from flows.utils.manifest import MANIFEST_NAME  # noqa: E402
from flows.utils.utils import CompMode, TraceMode  # noqa: E402


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def make_target(root: Path, target: str = "cv32a60x") -> None:
    target_dir = root / "config" / "target" / target
    target_dir.mkdir(parents=True)
    (target_dir / "Flist.cva6").write_text("\n", encoding="utf-8")
    (target_dir / "rtl_cfg_pkg.sv").write_text("\n", encoding="utf-8")


class VerilatorTestHarnessCompTest(unittest.TestCase):
    def test_public_interface_matches_the_proposed_compile_recipe(self) -> None:
        parameters = inspect.signature(RECIPE.verilator_testharness_comp).parameters
        self.assertEqual(
            list(parameters),
            ["target", "comp_mode", "trace_mode", "stats", "quiet"],
        )
        self.assertEqual(parameters["comp_mode"].default.default, CompMode.rtl)
        self.assertEqual(parameters["trace_mode"].default.default, TraceMode.notrace)
        self.assertFalse(parameters["stats"].default.default)

    def test_unsupported_modes_fail_explicitly(self) -> None:
        for mode in (
            CompMode.coverage,
            CompMode.gate_wc_timing,
            CompMode.gate_wc_power,
        ):
            with self.assertRaisesRegex(ValueError, "only rtl"):
                RECIPE.validate_options(mode, TraceMode.notrace, False)

        with self.assertRaisesRegex(ValueError, "interactive GUI"):
            RECIPE.validate_options(CompMode.rtl, TraceMode.gui, False)
        with self.assertRaisesRegex(ValueError, "perf tracer"):
            RECIPE.validate_options(CompMode.rtl, TraceMode.notrace, True)

    def test_target_validation_rejects_path_components(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid target name"):
            RECIPE.target_directory(Path("/repo"), "../cv32a60x")

    def test_testharness_filelist_is_complete(self) -> None:
        filelist = REPO_ROOT / "verif/tb/core/Flist.verilator_testharness"
        self.assertTrue(filelist.is_file())

        sources = [
            line.removeprefix("${CVA6_REPO_DIR}/")
            for line in filelist.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("//")
        ]
        self.assertTrue(sources)
        self.assertTrue(all((REPO_ROOT / source).is_file() for source in sources))

    def test_compile_command_invokes_verilator_directly(self) -> None:
        root = Path("/repo")
        command = RECIPE.build_command(
            repo_dir=root,
            target="cv32a60x",
            comp_mode=CompMode.rtl,
            trace_mode=TraceMode.compact,
            stats=False,
            jobs=4,
            verilator="/tools/verilator/bin/verilator",
            verilator_root=Path("/tools/verilator/share/verilator"),
            riscv=Path("/tools/riscv"),
            spike=Path("/tools/spike"),
        )

        self.assertEqual(command[0], "/tools/verilator/bin/verilator")
        self.assertIn("--build", command)
        self.assertIn(str(root / "config/target/cv32a60x/Flist.cva6"), command)
        self.assertIn(str(root / "verif/tb/core/Flist.verilator_testharness"), command)
        self.assertIn("--trace-fst", command)
        self.assertTrue(any("-lz" in argument for argument in command))
        self.assertIn("ariane_testharness", command)
        self.assertNotIn("make", command)
        self.assertFalse(any("cva6.py" in argument for argument in command))

        package = str(root / "corev_apu/tb/ariane_axi_pkg.sv")
        filelist = str(root / "verif/tb/core/Flist.verilator_testharness")
        cpp = str(root / "corev_apu/tb/ariane_tb.cpp")
        self.assertLess(command.index(package), command.index(filelist))
        self.assertLess(command.index(filelist), command.index(cpp))

    def test_configured_verilator_install_selects_one_tool_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            riscv = root / "riscv"
            spike = root / "spike"
            install = root / "verilator"
            for path in (
                riscv / "include",
                riscv / "lib",
                spike / "include",
                spike / "lib",
                install / "share/verilator/include/vltstd",
            ):
                path.mkdir(parents=True)
            binary = install / "bin/verilator"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "RISCV": str(riscv),
                    "SPIKE_INSTALL_DIR": str(spike),
                    "VERILATOR_INSTALL_DIR": str(install),
                },
            ):
                actual_riscv, actual_spike, actual_binary, actual_root = (
                    RECIPE.tool_paths(root)
                )

        self.assertEqual(actual_riscv, riscv.resolve())
        self.assertEqual(actual_spike, spike.resolve())
        self.assertEqual(actual_binary, str(binary.resolve()))
        self.assertEqual(actual_root, (install / "share/verilator").resolve())

    def test_path_verilator_reports_the_matching_include_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verilator_root = root / "share/verilator"
            (verilator_root / "include/vltstd").mkdir(parents=True)
            completed = Mock(
                stdout=(
                    "Summary of configuration:\n"
                    f"    VERILATOR_ROOT     = {verilator_root}\n"
                )
            )
            with (
                patch.object(RECIPE.shutil, "which", return_value="/usr/bin/verilator"),
                patch.object(RECIPE.subprocess, "run", return_value=completed) as run,
            ):
                binary, actual_root = RECIPE._verilator_from_path()

        self.assertEqual(binary, "/usr/bin/verilator")
        self.assertEqual(actual_root, verilator_root.resolve())
        run.assert_called_once_with(
            ["/usr/bin/verilator", "-V"],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_compile_writes_the_canonical_cook_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_target(root)
            riscv = root / "riscv"
            spike = root / "spike"
            verilator_root = root / "verilator-root"

            def run_compile(*args, **kwargs):
                del args
                binary = RECIPE.testharness_binary(root, "cv32a60x", CompMode.rtl)
                binary.touch()
                kwargs["log_file"].write_text("compiled\n", encoding="utf-8")

            with (
                working_directory(root),
                patch.object(
                    RECIPE,
                    "tool_paths",
                    return_value=(
                        riscv,
                        spike,
                        "/tools/verilator/bin/verilator",
                        verilator_root,
                    ),
                ),
                patch.object(RECIPE, "run_cmd", side_effect=run_compile),
                patch.dict(os.environ, {"NUM_JOBS": "2"}),
            ):
                RECIPE.verilator_testharness_comp(
                    target="cv32a60x",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    stats=False,
                    quiet=True,
                )

            elab_dir = RECIPE.elaboration_directory(root, "cv32a60x", CompMode.rtl)
            manifest = yaml.safe_load(
                (elab_dir / MANIFEST_NAME).read_text(encoding="utf-8")
            )

        self.assertEqual(manifest["recipe"], "verilator-testharness-comp")
        self.assertEqual(
            manifest["options"],
            {
                "target": "cv32a60x",
                "comp_mode": "rtl",
                "trace_mode": "notrace",
                "stats": False,
            },
        )

    def test_compile_failure_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_target(root)
            with (
                working_directory(root),
                patch.object(
                    RECIPE,
                    "tool_paths",
                    return_value=(
                        root / "riscv",
                        root / "spike",
                        "/tools/verilator/bin/verilator",
                        root / "verilator-root",
                    ),
                ),
                patch.object(RECIPE, "run_cmd", side_effect=RuntimeError("failed")),
                self.assertRaises(RECIPE.typer.Exit) as raised,
            ):
                RECIPE.verilator_testharness_comp(
                    target="cv32a60x",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    stats=False,
                    quiet=True,
                )

        self.assertEqual(raised.exception.exit_code, 1)


if __name__ == "__main__":
    unittest.main()
