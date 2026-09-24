# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Check the checked-in CI matrix against Cook targets and testlists, offline."""

from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow(tier):
    return yaml.safe_load(
        (ROOT / f".github/workflows/openhw-cva6-ci-tier{tier}.yml").read_text()
    )


class MatrixTests(unittest.TestCase):
    def test_rows_have_real_axi_rv32_targets_and_enabled_tests(self):
        for tier in (1, 2):
            rows = workflow(tier)["jobs"]["regression"]["strategy"]["matrix"]["include"]
            self.assertTrue(rows)
            self.assertEqual(
                len(rows), len({(r["config"], r["testcase"]) for r in rows})
            )
            for row in rows:
                with self.subTest(tier=tier, row=row):
                    target = ROOT / "config/target" / row["config"]
                    self.assertEqual(
                        yaml.safe_load((target / "testbench_cfg.yml").read_text())[
                            "hier"
                        ],
                        "axi",
                    )
                    self.assertEqual(
                        yaml.safe_load((target / "isa.yml").read_text())["mabi"],
                        "ilp32",
                    )
                    self.assertTrue(row["march"].startswith("rv32"))
                    self.assertNotIn(
                        "zcmt",
                        row["march"],
                        "The pinned GCC 13 profile does not implement Zcmt",
                    )
                    tests = yaml.safe_load((ROOT / row["testlist"]).read_text())[
                        "testlist"
                    ]
                    enabled = [t for t in tests if t.get("iterations", 1) > 0]
                    self.assertTrue(enabled, "A CI row must execute at least one test")
                    for test in enabled:
                        self.assertIn("gcc_opts", test)
                        sources = (
                            test["asm_tests"]
                            .replace("<path_var>", "verif/tests")
                            .split()
                        )
                        for source in sources:
                            if source.startswith("verif/tests/riscv-tests/"):
                                self.assertEqual(
                                    row["install_script"], "install-riscv-tests"
                                )
                            else:
                                self.assertTrue((ROOT / source).is_file(), source)
                    if row["testlist"] == "verif/tests/base_pmp.yaml":
                        config = (target / "rtl_cfg_pkg.sv").read_text()
                        entries = re.search(
                            r"NrPMPEntries:\s*unsigned'\((\d+)\)", config
                        )
                        self.assertIsNotNone(entries)
                        self.assertGreater(
                            int(entries.group(1)),
                            0,
                            "PMP tests require hardware PMP entries",
                        )

    def test_tier2_includes_tier1_without_changing_row_options(self):
        first = workflow(1)["jobs"]["regression"]["strategy"]["matrix"]["include"]
        second = workflow(2)["jobs"]["regression"]["strategy"]["matrix"]["include"]
        for row in first:
            self.assertIn(row, second)

    def test_triggers_permissions_and_bounded_runtime(self):
        for tier in (1, 2):
            data = workflow(tier)
            triggers = data.get(
                "on", data.get(True)
            )  # PyYAML YAML 1.1 treats on as a boolean.
            self.assertIn("workflow_dispatch", triggers)
            self.assertNotIn("pull_request_target", triggers)
            self.assertNotIn("schedule", triggers)
            if tier == 1:
                self.assertEqual(
                    triggers["pull_request"]["branches"], ["master_candidate"]
                )
            self.assertEqual(data["permissions"], {"contents": "read"})
            self.assertEqual(data["env"]["NUM_JOBS"], "2")
            self.assertLessEqual(
                data["jobs"]["regression"]["strategy"]["max-parallel"], 2
            )
            for job in data["jobs"].values():
                self.assertLessEqual(job["timeout-minutes"], 60)

    def test_workflow_references_only_delivered_tests(self):
        for tier in (1, 2):
            steps = workflow(tier)["jobs"]["checks"]["steps"]
            scripts = [
                p
                for step in steps
                for p in re.findall(r"\.github/tests/[\w_]+\.py", step.get("run", ""))
            ]
            self.assertTrue(scripts)
            for script in scripts:
                self.assertTrue((ROOT / script).is_file(), script)

    def test_artifacts_are_uploaded_on_failure(self):
        for tier in (1, 2):
            uploads = [
                s
                for s in workflow(tier)["jobs"]["regression"]["steps"]
                if s.get("uses", "").startswith("actions/upload-artifact@")
            ]
            self.assertEqual(len(uploads), 1)
            self.assertEqual(uploads[0]["if"], "always()")
            self.assertIn("ci-results/", uploads[0]["with"]["path"])


if __name__ == "__main__":
    unittest.main()
