# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Check real Cook report verdicts without launching a simulator."""

from pathlib import Path
import tempfile
import unittest

import typer
import yaml

from flows.utils.recipe_report import RecipeReport
from flows.utils.tandem import analyze_tandem_report


class TandemVerdictTests(unittest.TestCase):
    def verdict(self, count, expected_failure, *, strict=True, omit=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dict(exit_cause="SUCCESS", exit_code=0, mismatches_count=0)
            if not omit:
                data["instr_count"] = count
            native = root / "native.yml"
            native.write_text(yaml.safe_dump(data))
            report = RecipeReport("test-tandem", out_dir=root, quiet=True)
            problem = analyze_tandem_report(native, report, require_comparisons=strict)
            self.assertEqual(problem, expected_failure)
            if expected_failure:
                with self.assertRaises(typer.Exit) as error:
                    report.end()
                self.assertEqual(error.exception.exit_code, 1)
            else:
                report.end()
            saved = yaml.safe_load((root / "cook_report.yml").read_text())
            self.assertEqual(saved["status"], "fail" if expected_failure else "pass")

    def test_positive_counts_pass(self):
        for count in [1, 502, "0x 10"]:
            with self.subTest(count=count):
                self.verdict(count, False)

    def test_invalid_counts_fail(self):
        for count in [0, -1, None, True, False, "", "invalid", 1.5, [], {}]:
            with self.subTest(count=count):
                self.verdict(count, True)
        self.verdict(None, True, omit=True)

    def test_existing_uvm_policy_is_unchanged(self):
        self.verdict(0, False, strict=False)
        self.verdict(None, False, strict=False, omit=True)


if __name__ == "__main__":
    unittest.main()
