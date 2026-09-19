# SPDX-License-Identifier: Apache-2.0
import copy
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = tempfile.TemporaryDirectory()
unittest.addModuleCleanup(CONFIG.cleanup)
for name in ["compiler.yml", "techno.yml"]:
    Path(CONFIG.name, name).write_text("{}\n")
os.environ["CONFIG_DIR"] = CONFIG.name
spec = importlib.util.spec_from_file_location(
    "cook_tier", ROOT / ".github/scripts/cook_tier.py"
)
tier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tier)


class TierContractTests(unittest.TestCase):
    def test_verilator_installed_before_vendor_spike_dpi_build(self):
        action = yaml.safe_load(
            (ROOT / ".github/actions/setup-cva6-env/action.yml").read_text()
        )
        install = next(
            step["run"]
            for step in action["runs"]["steps"]
            if step.get("name") == "Require tools or install missing entries"
        )
        self.assertLess(
            install.index('if [ "$VERILATOR_HIT"'),
            install.index("source verif/regress/install-spike.sh"),
        )

    def setUp(self):
        self.summary = {
            "schema_version": 1,
            "target": "cv32a60x_axi",
            "testlist": "suite.yml",
            "simulator": "verilator",
            "iss_enabled": True,
            "comp_mode": "rtl",
            "trace_mode": "notrace",
            "status": "PASS",
            "total": 1,
            "passed": 1,
            "failed": 0,
            "cases": [{"test_name": "add_0", "status": "PASS"}],
        }

    def check(self, data):
        return tier.checked_summary(
            data, target="cv32a60x_axi", testlist="suite.yml", expected=["add_0"]
        )

    def test_valid_contract(self):
        self.assertEqual(self.check(self.summary), self.summary)

    def test_rejects_missing_and_mismatched_evidence(self):
        for key, value in [
            ("schema_version", 2),
            ("target", "other"),
            ("testlist", "old.yml"),
            ("simulator", "vcs"),
            ("iss_enabled", False),
            ("trace_mode", "fast"),
            ("total", 0),
            ("total", True),
            ("passed", 0),
            ("failed", 1),
            ("status", "FAIL"),
            ("cases", []),
            ("cases", [{"test_name": "old_0", "status": "PASS"}]),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.check({**self.summary, key: value})

    def test_fail_cannot_be_promoted_to_pass(self):
        summary = copy.deepcopy(self.summary)
        summary["cases"][0]["status"] = "FAIL"
        with self.assertRaises(ValueError):
            self.check(summary)

    def test_nonzero_step_stops_and_records_failure(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                Path("suite.yml").write_text("testlist:\n- test: add\n")

                def failure(command, **kwargs):
                    kwargs["log"].write_text("compile failed\n")
                    return 9, False

                env = {
                    "CONFIG_DIR": CONFIG.name,
                    "TIER_CONFIG": "cv32a60x_axi",
                    "TIER_TESTLIST": "suite.yml",
                    "TIER_TESTCASE": "base",
                    "TIER_NAME": "Tier 1",
                    "TIER_COMPILER_MARCH": "rv32imc",
                    "RESULTS_DIR": "results",
                }
                with patch.dict(os.environ, env), patch.object(
                    tier.subprocess, "check_output", return_value="a" * 40
                ), patch.object(tier, "run_logged_process", side_effect=failure) as run:
                    self.assertEqual(tier.main(), 1)
                    self.assertEqual(run.call_count, 1)
                evidence = tier.json.loads(Path("results/evidence.json").read_text())
                self.assertEqual(evidence["status"], "FAIL")
                self.assertEqual(evidence["commands"][0]["exit_code"], 9)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
