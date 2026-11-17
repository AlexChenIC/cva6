# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Recipe integration tests using controlled prerequisites and simulator results."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import typer
import yaml

from flows.recipes import verilator_testharness_run as recipe
from flows.utils.autocompletion import CompMode, TraceMode


class VerilatorRunContractTests(unittest.TestCase):
    def run_case(self, *, live, pk, count=1, interrupt=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config/target/test_target/spike.yaml"
            config.parent.mkdir(parents=True)
            config.write_text("{}")
            mode = "sim_rtl_verilator_testharness" + ("_tandem" if live else "")
            out = root / "build/test_target/simulation" / mode / "test"
            program = MagicMock()
            program.binary = root / "program.elf"
            program.tohost = "80001000"
            program.run_plusargs.return_value = []
            program.htif_args.return_value = [str(program.binary)]
            commands = []

            def simulate(*, cmd, log_file, report, **_):
                commands.append(cmd)
                if interrupt:
                    log_file.write_text("interrupted")
                    report.error("Command failed (130)")
                else:
                    log_file.write_text("*** SUCCESS *** (tohost = 0) after 100 cycles")
                if live:
                    (out / "testharness.log.yaml").write_text(
                        yaml.safe_dump(
                            dict(
                                exit_cause="SUCCESS",
                                exit_code=0,
                                mismatches_count=0,
                                instr_count=count,
                            )
                        )
                    )

            old = Path.cwd()
            try:
                os.chdir(root)
                with (
                    patch.object(recipe, "require_prerequisite"),
                    patch.object(
                        recipe,
                        "read_manifest",
                        side_effect=[
                            {"options": {"tandem_enabled": live}},
                            {"options": {"pk_dir": "pk-build" if pk else None}},
                        ],
                    ),
                    patch.object(
                        recipe, "HarnessProgram", return_value=program
                    ) as factory,
                    patch.object(recipe, "spike_core_name", return_value="cv32a6"),
                    patch.object(recipe, "write_manifest"),
                    patch.object(recipe, "run_cmd", side_effect=simulate),
                ):
                    code = 0
                    try:
                        recipe.verilator_testharness_run(
                            target="test_target",
                            test_name="test",
                            comp_mode=CompMode.rtl,
                            trace_mode=TraceMode.notrace,
                            interactive_gui=False,
                            sim_timeout=5,
                            tandem_enabled=live,
                            run_name=None,
                            quiet=True,
                        )
                    except typer.Exit as error:
                        code = error.exit_code
                    constructed = factory.called
                report = yaml.safe_load((out / "cook_report.yml").read_text())
            finally:
                os.chdir(old)
            return code, commands, report, constructed

    def test_live_pk_rejected_before_program_construction_or_launch(self):
        code, commands, report, constructed = self.run_case(live=True, pk=True)
        self.assertEqual(code, 1)
        self.assertEqual(commands, [])
        self.assertFalse(constructed)
        self.assertEqual(report["status"], "fail")

    def test_ordinary_pk_remains_accepted_and_unwrapped(self):
        code, commands, report, constructed = self.run_case(live=False, pk=True)
        self.assertEqual(code, 0)
        self.assertTrue(constructed)
        self.assertNotIn("tandem_launcher.py", " ".join(commands[0]))
        self.assertEqual(report["status"], "pass")

    def test_live_zero_comparisons_fail_the_recipe(self):
        code, commands, report, _ = self.run_case(live=True, pk=False, count=0)
        self.assertEqual(code, 1)
        self.assertIn("tandem_launcher.py", " ".join(commands[0]))
        self.assertEqual(report["status"], "fail")

    def test_live_positive_comparisons_pass_the_recipe(self):
        code, _, report, _ = self.run_case(live=True, pk=False, count=3)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "pass")

    def test_interruption_overrides_a_successful_native_report(self):
        code, _, report, _ = self.run_case(live=True, pk=False, count=3, interrupt=True)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "fail")


if __name__ == "__main__":
    unittest.main()
