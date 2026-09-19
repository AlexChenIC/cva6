# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
from contextlib import contextmanager
import inspect
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import typer
from typer.testing import CliRunner
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
CONFIG = tempfile.TemporaryDirectory()
unittest.addModuleCleanup(CONFIG.cleanup)
Path(CONFIG.name, "compiler.yml").write_text("{}\n")
Path(CONFIG.name, "techno.yml").write_text("{}\n")
os.environ["CONFIG_DIR"] = CONFIG.name

from flows.recipes import testharness_run_testlist as recipe
from flows.utils.utils import CompMode, TraceMode


@contextmanager
def workspace():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            yield Path(directory)
        finally:
            os.chdir(previous)


def successful_run(**options):
    output = recipe.simulation_directory(
        Path.cwd(), options["target"], options["test_name"], options["comp_mode"]
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.yml").write_text(
        yaml.safe_dump(
            {
                "target": options["target"],
                "test_name": options["test_name"],
                "status": "PASS",
                "iss_enabled": options["iss_enabled"],
                "detail": "fixture",
            }
        )
    )


class TestlistTests(unittest.TestCase):
    def invoke(self, entries, *, quiet=True):
        Path("tests.yml").write_text(yaml.safe_dump(entries))
        args = ["--simulator", "verilator", "-t", "cv32a60x_axi", "-l", "tests.yml"]
        return CliRunner().invoke(recipe.app, args + (["--quiet"] if quiet else []))

    def test_interface(self):
        self.assertEqual(
            list(inspect.signature(recipe.testharness_run_testlist).parameters),
            [
                "simulator",
                "target",
                "testlist",
                "comp_mode",
                "trace_mode",
                "iss_enabled",
                "quiet",
            ],
        )

    def test_iterations_and_disabled(self):
        with workspace(), patch.object(
            recipe, "verilator_testharness_run", side_effect=successful_run
        ) as run:
            result = self.invoke(
                {
                    "testlist": [
                        {"test": "add", "iterations": 2},
                        {"test": "disabled", "iterations": 0},
                    ]
                }
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(result.output, "")
            self.assertEqual(
                [c.kwargs["test_name"] for c in run.call_args_list], ["add_0", "add_1"]
            )
            summary = yaml.safe_load(
                next(Path("build").rglob("*_summary.yml")).read_text()
            )
            self.assertEqual(
                (summary["total"], summary["passed"], summary["failed"]), (2, 2, 0)
            )
            report = yaml.safe_load(
                next(Path("build").rglob("*_report.yml")).read_text()
            )
            self.assertEqual(report["status"], "pass")

    def test_failure_continues_and_is_visible_when_quiet(self):
        def run(**options):
            if options["test_name"] == "bad_0":
                raise typer.Exit(7)
            successful_run(**options)

        with workspace(), patch.object(
            recipe, "verilator_testharness_run", side_effect=run
        ) as mocked:
            result = self.invoke({"testlist": [{"test": "bad"}, {"test": "good"}]})
            self.assertEqual(result.exit_code, 1)
            self.assertIn("code 7", result.output)
            self.assertEqual(mocked.call_count, 2)
            summary = yaml.safe_load(
                next(Path("build").rglob("*_summary.yml")).read_text()
            )
            self.assertEqual((summary["passed"], summary["failed"]), (1, 1))

    def test_no_receipt_is_not_success(self):
        with workspace(), patch.object(recipe, "verilator_testharness_run"):
            self.assertEqual(self.invoke({"testlist": [{"test": "add"}]}).exit_code, 1)

    def test_stale_receipt_cannot_pass(self):
        with workspace(), patch.object(recipe, "verilator_testharness_run"):
            successful_run(
                target="cv32a60x_axi",
                test_name="add_0",
                comp_mode=CompMode.rtl,
                iss_enabled=False,
            )
            self.assertEqual(self.invoke({"testlist": [{"test": "add"}]}).exit_code, 1)

    def test_bad_receipt_metadata(self):
        def run(**options):
            successful_run(**{**options, "iss_enabled": True})

        with workspace(), patch.object(
            recipe, "verilator_testharness_run", side_effect=run
        ):
            result = self.invoke({"testlist": [{"test": "add"}]})
            self.assertEqual(result.exit_code, 1)
            self.assertIn("inconsistent", result.output)

    def test_invalid_testlists(self):
        for entries in [
            None,
            [],
            {},
            {"testlist": []},
            {"testlist": ["bad"]},
            {"testlist": [{"test": "a", "iterations": 0}]},
            {"testlist": [{"test": "../escape"}]},
            {"testlist": [{"test": "a"}, {"test": "a"}]},
            *[
                {"testlist": [{"test": "a", "iterations": x}]}
                for x in [-1, True, "1", 1.2]
            ],
        ]:
            with self.subTest(entries=entries), workspace(), patch.object(
                recipe, "verilator_testharness_run"
            ) as run:
                result = self.invoke(entries)
                self.assertNotEqual(result.exit_code, 0)
                self.assertTrue(result.output)
                run.assert_not_called()

    def test_symlinked_output_rejected(self):
        with workspace() as root:
            (root / "outside").mkdir()
            (root / "build").symlink_to(root / "outside", target_is_directory=True)
            result = self.invoke({"testlist": [{"test": "add"}]})
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("symbolic link", result.output)
            self.assertEqual(list((root / "outside").iterdir()), [])

    def test_old_summary_removed_on_invalid_list(self):
        with workspace(), patch.object(
            recipe, "verilator_testharness_run", side_effect=successful_run
        ):
            self.assertEqual(self.invoke({"testlist": [{"test": "add"}]}).exit_code, 0)
            self.assertEqual(self.invoke({"testlist": []}).exit_code, 1)
            self.assertEqual(list(Path("build").rglob("*_summary.yml")), [])

    def test_interrupt_not_swallowed(self):
        with workspace(), patch.object(
            recipe, "verilator_testharness_run", side_effect=KeyboardInterrupt
        ):
            with self.assertRaises(KeyboardInterrupt):
                recipe.run_entries(
                    ["add_0"],
                    target="cv32a60x_axi",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=False,
                    quiet=True,
                )

    def test_unknown_backend_rejected_by_cli(self):
        result = CliRunner().invoke(
            recipe.app, ["--simulator", "vcs", "-t", "t", "-l", "x"]
        )
        self.assertNotEqual(result.exit_code, 0)

    def test_report_write_failure_is_nonzero(self):
        with workspace(), patch.object(
            recipe, "verilator_testharness_run", side_effect=successful_run
        ), patch.object(recipe.Report, "dump", side_effect=OSError("disk full")):
            result = self.invoke({"testlist": [{"test": "add"}]})
            self.assertEqual(result.exit_code, 1)
            self.assertIn("disk full", result.output)


if __name__ == "__main__":
    unittest.main()
