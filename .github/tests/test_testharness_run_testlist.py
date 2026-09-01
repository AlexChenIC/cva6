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

from flows.recipes import testharness_run_testlist as RECIPE  # noqa: E402
from flows.utils.utils import CompMode, TraceMode  # noqa: E402


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TestHarnessRunTestlistTest(unittest.TestCase):
    def test_public_interface_matches_the_proposed_testlist_recipe(self) -> None:
        parameters = inspect.signature(RECIPE.testharness_run_testlist).parameters
        self.assertEqual(
            list(parameters),
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

    def test_parser_skips_disabled_tests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            testlist = Path(directory) / "tests.yml"
            testlist.write_text(
                "testlist:\n"
                "  - test: enabled\n"
                "    iterations: 2\n"
                "  - test: disabled\n"
                "    iterations: 0\n",
                encoding="utf-8",
            )
            self.assertEqual(RECIPE.enabled_tests(testlist), [("enabled", 2)])

    def test_parser_rejects_negative_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            testlist = Path(directory) / "tests.yml"
            testlist.write_text(
                "testlist:\n  - test: invalid\n    iterations: -1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cannot be negative"):
                RECIPE.enabled_tests(testlist)

    def test_dispatch_uses_compiled_iteration_names_and_aggregates_failure(
        self,
    ) -> None:
        calls: list[str] = []

        def fake_run(**kwargs) -> None:
            calls.append(kwargs["test_name"])
            if kwargs["test_name"] == "second_0":
                raise RECIPE.typer.Exit(code=1)

        with patch.object(RECIPE, "verilator_testharness_run", side_effect=fake_run):
            metric, failed = RECIPE.run_entries(
                tests=[("first", 2), ("second", 1)],
                target="cv32a60x",
                comp_mode=CompMode.rtl,
                trace_mode=TraceMode.notrace,
                iss_enabled=True,
                quiet=True,
            )

        self.assertEqual(calls, ["first_0", "first_1", "second_0"])
        self.assertTrue(failed)
        self.assertEqual([row[0] for row in metric.values], ["pass", "pass", "fail"])

    def test_top_level_writes_failed_report_and_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = "cv32a60x"
            binary = RECIPE.testharness_binary(root, target, CompMode.rtl)
            binary.parent.mkdir(parents=True)
            binary.touch()
            testlist = root / "tests.yml"
            testlist.write_text(
                "testlist:\n  - test: sample\n    iterations: 1\n",
                encoding="utf-8",
            )

            failed_metric = RECIPE.TableStatusMetric("results")
            failed_metric.add_column("Target", "text")
            failed_metric.add_fail(target)
            with (
                working_directory(root),
                patch.object(RECIPE, "run_entries", return_value=(failed_metric, True)),
                self.assertRaises(RECIPE.typer.Exit) as raised,
            ):
                RECIPE.testharness_run_testlist(
                    simulator=RECIPE.Simulator.verilator,
                    target=target,
                    testlist="tests.yml",
                    comp_mode=CompMode.rtl,
                    trace_mode=TraceMode.notrace,
                    iss_enabled=False,
                    quiet=True,
                )

            report = yaml.safe_load(
                RECIPE.report_path(
                    root, target, RECIPE.Simulator.verilator, "tests.yml"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(raised.exception.exit_code, 1)
        self.assertEqual(report["status"], "fail")


if __name__ == "__main__":
    unittest.main()
