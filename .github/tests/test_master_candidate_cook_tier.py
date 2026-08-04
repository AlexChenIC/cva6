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


PLAN = load_module("cook_tier_plan", REPO_ROOT / ".github/scripts/cook-tier-plan.py")
FAILURES = load_module(
    "summarize_cook_failures",
    REPO_ROOT / ".github/scripts/summarize-cook-failures.py",
)
TOOLCHAINS = load_module(
    "prepare_cook_toolchains",
    REPO_ROOT / ".github/scripts/prepare-cook-toolchains.py",
)
RECIPE = load_module(
    "verilator_testharness_run_testlist",
    REPO_ROOT / "flows/recipes/verilator_testharness_run_testlist.py",
)


class TierPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan_path = REPO_ROOT / ".github/ci/master_candidate_cook_tiers.yml"

    def test_plan_matches_all_scoped_thales_testlists(self) -> None:
        with working_directory(REPO_ROOT):
            report = PLAN.validate_plan(self.plan_path)
        self.assertEqual(report["tiers"]["tier1"]["enabled_target_test_pairs"], 10)
        self.assertEqual(report["tiers"]["tier2"]["enabled_target_test_pairs"], 23)
        self.assertEqual(
            report["tiers"]["tier2"]["required_enabled_target_test_pairs"], 10
        )
        self.assertEqual(
            report["tiers"]["tier2"]["diagnostic_enabled_target_test_pairs"],
            13,
        )
        self.assertFalse(report["comparison_boundary"]["full_pipeline_parity_claimed"])

    def test_tier2_rejects_missing_thales_testlist(self) -> None:
        data = yaml.safe_load(self.plan_path.read_text(encoding="utf-8"))
        data["tiers"]["tier2"]["entries"] = [
            entry
            for entry in data["tiers"]["tier2"]["entries"]
            if Path(entry["testlist"]).stem != "base_pmp"
        ]
        data["tiers"]["tier2"]["expected_enabled_tests"] = 18
        data["tiers"]["tier2"]["expected_diagnostic_enabled_tests"] = 8
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.yml"
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
            with working_directory(REPO_ROOT):
                with self.assertRaisesRegex(ValueError, "not testlist-complete"):
                    PLAN.validate_plan(path)

    def test_matrix_is_generated_from_plan(self) -> None:
        with working_directory(REPO_ROOT):
            matrix = PLAN.matrix_for_tier(self.plan_path, "tier2")
        pairs = {
            (entry["target"], Path(entry["testlist"]).stem)
            for entry in matrix["include"]
        }
        self.assertEqual(len(pairs), 5)
        self.assertIn(("cv32a65x_axi", "base_pmp"), pairs)
        self.assertIn(("cv32a60x_axi", "base_zcmt"), pairs)

    def test_matrix_marks_extended_testlists_as_diagnostic(self) -> None:
        with working_directory(REPO_ROOT):
            matrix = PLAN.matrix_for_tier(self.plan_path, "tier2")
        acceptance = {
            (entry["target"], Path(entry["testlist"]).stem): entry["acceptance"]
            for entry in matrix["include"]
        }
        self.assertEqual(acceptance[("cv32a60x_axi", "base_rv32_p")], "required")
        self.assertEqual(acceptance[("cv32a60x_axi", "base_zcmt")], "diagnostic")
        self.assertEqual(acceptance[("cv32a65x_axi", "base_pmp")], "diagnostic")

    def test_diagnostic_entry_requires_a_reason(self) -> None:
        data = yaml.safe_load(self.plan_path.read_text(encoding="utf-8"))
        del data["tiers"]["tier2"]["entries"][1]["acceptance_reason"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.yml"
            path.write_text(yaml.safe_dump(data), encoding="utf-8")
            with working_directory(REPO_ROOT):
                with self.assertRaisesRegex(ValueError, "needs acceptance_reason"):
                    PLAN.validate_plan(path)


class RecipeAdapterTest(unittest.TestCase):
    def test_cycle_independent_isa_normalization(self) -> None:
        self.assertEqual(
            RECIPE.cva6_input_isa("rv32imc_zicsr_zba_zcmt"),
            "rv32imc_zba_zcmt",
        )

    def test_iss_config_uses_canonical_target_spike_yaml(self) -> None:
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
        self.assertTrue(
            all("target spike.yml" in command for command in commands.values())
        )

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


class FailureSummaryTest(unittest.TestCase):
    def test_extracts_failures_without_matching_pass_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "cook.log"
            log.write_text(
                "1 PASSED, 0 FAILED\n"
                "ERROR    ERROR return code: True/2, cmd:make spike\n"
                "granularity_test_0: FAIL (1)\n",
                encoding="utf-8",
            )
            matches = FAILURES.summarize([log])
        self.assertEqual(len(matches), 2)
        self.assertTrue(any("ERROR return code" in match for match in matches))
        self.assertTrue(any("FAIL (1)" in match for match in matches))
        self.assertFalse(any("0 FAILED" in match for match in matches))


class WorkflowContractTest(unittest.TestCase):
    def test_candidate_workflows_use_isolated_helpers(self) -> None:
        reusable_path = (
            REPO_ROOT / ".github/workflows/openhw-cva6-ci-cook-tier-reusable.yml"
        )
        reusable = reusable_path.read_text(encoding="utf-8")
        workflow = yaml.load(reusable, Loader=yaml.BaseLoader)
        execute_job = workflow["jobs"]["execute"]
        regression_step = next(
            step
            for step in execute_job["steps"]
            if step.get("name") == "Run public cook.py tandem regression"
        )
        self.assertIn("setup-cva6-cook-env", reusable)
        self.assertIn("run-cook-tier-regression.sh", reusable)
        self.assertNotIn("setup-cva6-env", reusable)
        self.assertNotIn("run-tier-regression.sh", reusable)
        self.assertIn("actions/upload-artifact@v7", reusable)
        self.assertNotIn("continue-on-error", execute_job)
        self.assertEqual(
            regression_step["continue-on-error"],
            "${{ matrix.acceptance == 'diagnostic' }}",
        )

    def test_tier1_and_tier2_target_master_candidate(self) -> None:
        tier1 = (
            REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier1-master-candidate.yml"
        ).read_text(encoding="utf-8")
        tier2 = (
            REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier2-master-candidate.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("pull_request:", tier1)
        self.assertIn("master_candidate", tier1)
        self.assertNotIn("push:", tier1)
        self.assertNotIn("pull_request:", tier2)
        self.assertIn("push:", tier2)
        self.assertIn("master_candidate", tier2)


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
