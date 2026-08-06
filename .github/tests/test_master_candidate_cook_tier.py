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

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TEST_CONFIG_DIRECTORY = tempfile.TemporaryDirectory()
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


TOOLCHAINS = load_module(
    "prepare_cook_toolchains",
    REPO_ROOT / ".github/scripts/prepare-cook-toolchains.py",
)
RECIPE = load_module(
    "verilator_testharness_run_testlist",
    REPO_ROOT / "flows/recipes/verilator_testharness_run_testlist.py",
)


def load_workflow(name: str) -> dict:
    path = REPO_ROOT / ".github/workflows" / name
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def matrix_entries(workflow: dict, job: str) -> list[dict[str, str]]:
    return workflow["jobs"][job]["strategy"]["matrix"]["include"]


class WorkflowContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tier1_path = REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier1.yml"
        self.tier2_path = REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier2.yml"
        self.tier1 = load_workflow(self.tier1_path.name)
        self.tier2 = load_workflow(self.tier2_path.name)
        self.tier1_entries = matrix_entries(self.tier1, "execute-rv32-tier1")
        self.tier2_entries = matrix_entries(self.tier2, "execute-rv32-tier2")

    def test_initial_scope_and_tier_subset(self) -> None:
        tier1_pairs = {
            (entry["config"], entry["testlist"]) for entry in self.tier1_entries
        }
        tier2_pairs = {
            (entry["config"], entry["testlist"]) for entry in self.tier2_entries
        }
        self.assertEqual(
            tier1_pairs,
            {
                ("cv32a60x_axi", "verif/tests/base_rv32_p.yaml"),
                ("cv32a65x_axi", "verif/tests/base_rv32_p.yaml"),
            },
        )
        self.assertEqual(len(tier2_pairs), 5)
        self.assertLessEqual(tier1_pairs, tier2_pairs)

    def test_entries_reference_real_axi_targets_and_testlists(self) -> None:
        for entry in self.tier2_entries:
            target_dir = REPO_ROOT / "config/target" / entry["config"]
            testlist = REPO_ROOT / entry["testlist"]
            self.assertTrue(target_dir.is_dir())
            self.assertTrue(testlist.is_file())
            testbench = yaml.safe_load(
                (target_dir / "testbench_cfg.yml").read_text(encoding="utf-8")
            )
            self.assertEqual(testbench["hier"], "axi")
            tests = yaml.safe_load(testlist.read_text(encoding="utf-8"))["testlist"]
            enabled = [test for test in tests if int(test.get("iterations", 1)) > 0]
            self.assertEqual(len(enabled), int(entry["expected_enabled_tests"]))

    def test_compiler_isa_overrides_follow_rtl_extension_contract(self) -> None:
        expected_zifencei = {
            "cv32a60x_axi": False,
            "cv32a65x_axi": True,
        }
        for entry in self.tier2_entries:
            rtl_config = (
                REPO_ROOT / "config/target" / entry["config"] / "rtl_cfg_pkg.sv"
            ).read_text(encoding="utf-8")
            self.assertIn("RVA: bit'(0)", rtl_config)
            self.assertIn("RVZCMT: bit'(1)", rtl_config)

            zifencei_enabled = expected_zifencei[entry["config"]]
            self.assertIn(
                f"RVZifencei: bit'({int(zifencei_enabled)})",
                rtl_config,
            )
            self.assertEqual(
                "zifencei" in entry["compiler_march"],
                zifencei_enabled,
            )

            if entry["testlist"] == "verif/tests/base_zcmt.yaml":
                self.assertIn("zcmt", entry["compiler_march"])

    def test_workflows_keep_truthful_failure_semantics(self) -> None:
        for path in (self.tier1_path, self.tier2_path):
            text = path.read_text(encoding="utf-8")
            self.assertIn("fail-fast: false", text)
            self.assertIn("if: always()", text)
            self.assertNotIn("continue-on-error", text)
            self.assertNotIn("allow_failure", text)

    def test_no_gitlab_matrix_runtime_dependency(self) -> None:
        paths = (
            self.tier1_path,
            self.tier2_path,
            REPO_ROOT / ".github/scripts/run-tier-regression.sh",
            REPO_ROOT / ".github/actions/setup-cva6-env/action.yml",
        )
        for path in paths:
            self.assertNotIn(".gitlab-ci", path.read_text(encoding="utf-8"))

    def test_master_tier_contract_is_extended_in_place(self) -> None:
        runner = (REPO_ROOT / ".github/scripts/run-tier-regression.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("cook-testlist", runner)
        self.assertIn('RESULTS_DIR="${RESULTS_DIR:-ci-results}"', runner)
        self.assertIn("${RESULTS_DIR}/run.log", runner)
        self.assertIn("failure_summary.log", runner)
        self.assertIn("exit_code", runner)


class RecipeAdapterTest(unittest.TestCase):
    def test_isa_normalization_removes_only_zicsr(self) -> None:
        self.assertEqual(
            RECIPE.cva6_input_isa("rv32imc_zicsr_zba_zcmt"),
            "rv32imc_zba_zcmt",
        )

    def test_iss_config_uses_target_spike_yaml(self) -> None:
        source = REPO_ROOT / "verif/sim/cva6.yaml"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cva6.yml"
            spike = Path(directory) / "target spike.yml"
            spike.write_text("spike_param_tree: {}\n", encoding="utf-8")
            RECIPE.write_iss_config(source, output, spike)
            data = yaml.safe_load(output.read_text(encoding="utf-8"))
        commands = {
            entry["iss"]: entry["cmd"]
            for entry in data
            if entry["iss"] in {"spike", "veri-testharness"}
        }
        self.assertEqual(len(commands), 2)
        self.assertTrue(all("spike_yaml=" in command for command in commands.values()))

    def test_precompiled_elf_uses_existing_object_interface(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            elf = Path(directory) / "test.elf"
            elf.write_bytes(b"ELF fixture")
            alias = RECIPE.precompiled_object_alias(elf)
            self.assertEqual(alias.suffix, ".o")
            self.assertEqual(alias.read_bytes(), elf.read_bytes())
            self.assertEqual(alias.stat().st_ino, elf.stat().st_ino)


class ToolchainConfigTest(unittest.TestCase):
    def test_clang_wrapper_forces_lld(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            compiler = Path(directory) / "clang-18"
            compiler.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            compiler.chmod(0o755)
            wrapper = Path(directory) / "clang-riscv32"
            TOOLCHAINS.write_wrapper(wrapper, compiler)
            text = wrapper.read_text(encoding="utf-8")
            self.assertIn("-fuse-ld=lld", text)
            self.assertIn(str(compiler), text)
            self.assertTrue(os.access(wrapper, os.X_OK))


class DependencyContractTest(unittest.TestCase):
    def test_every_cook_requirement_is_constrained(self) -> None:
        requirements = {
            line.strip().lower()
            for line in (REPO_ROOT / "flows/requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.startswith("#")
        }
        constraints = {
            line.split("==", 1)[0].strip().lower()
            for line in (
                REPO_ROOT / ".github/requirements/cook-tier-ci-constraints.txt"
            )
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertLessEqual(requirements, constraints)


class TraceParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sim_dir = REPO_ROOT / "verif/sim"
        sys.path.insert(0, str(sim_dir))
        sys.path.insert(0, str(sim_dir / "dv/scripts"))
        with working_directory(sim_dir):
            cls.parser = load_module(
                "verilator_log_to_trace_csv",
                sim_dir / "verilator_log_to_trace_csv.py",
            )

    def test_cycle_prefixed_and_legacy_trace_lines_match(self) -> None:
        cycle_line = (
            "        79 | core   0: 0x0000000000010000 "
            "(0x00100413) addi    s0, zero, 1"
        )
        legacy_line = "core   0: 0x0000000000010000 " "(0x00100413) addi    s0, zero, 1"
        self.assertIsNotNone(self.parser.CORE_RE.match(cycle_line))
        self.assertIsNotNone(self.parser.CORE_RE.match(legacy_line))

    def test_cycle_prefixed_trampoline_marker_matches(self) -> None:
        marker = (
            "       105 | core   0: 0x0000000080000000 " "(0x0000a835) DASM(0000a835)"
        )
        self.assertIsNotNone(self.parser.END_TRAMPOLINE_RE.match(marker))


if __name__ == "__main__":
    unittest.main()
