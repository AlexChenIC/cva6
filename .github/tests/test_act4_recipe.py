# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import typer
import yaml

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

from flows.act4.corpus import CorpusError  # noqa: E402
from flows.act4.runner import TestResult  # noqa: E402
from flows.recipes import act4 as recipe  # noqa: E402


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class Act4RecipeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.corpus_directory = self.root / "corpus"
        self.simulator = self.root / "work-ver/Variane_testharness"

    @staticmethod
    def prepared_corpus():
        return SimpleNamespace(
            tests=(SimpleNamespace(),),
            manifest=SimpleNamespace(
                generation=SimpleNamespace(profile_sha256="a" * 64),
                archive_sha256="b" * 64,
            ),
        )

    def invoke(self) -> None:
        recipe.act4_run(
            target="cv32a65x_axi",
            corpus_directory=self.corpus_directory,
            simulator=self.simulator,
            cycle_timeout=12345,
            wall_timeout_seconds=60,
            quiet=True,
        )

    def invoke_package(self, *, target: str = "cv32a65x_axi") -> None:
        recipe.act4_package(
            target=target,
            elf_directory=Path("act-work/cv32a65x_axi/elfs"),
            resolved_profile=Path("act-work/cv32a65x_axi/resolved-profile.json"),
            act_commit="a" * 40,
            cva6_commit="b" * 40,
            image_digest="sha256:" + "c" * 64,
            output_directory=None,
            replace=False,
            quiet=True,
        )

    def report(self) -> dict[str, object]:
        path = self.root / "artifacts/reports/report_act4_cv32a65x_axi.yml"
        return yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_success_writes_passing_cook_report(self) -> None:
        log = self.root / "artifacts/act4/test.log"
        log.parent.mkdir(parents=True)
        log.write_text("fixture\n", encoding="utf-8")
        result = TestResult(
            test_id="I-add-01",
            elf="elfs/I-add-01.elf",
            passed=True,
            detail="exact marker matched",
            return_code=0,
            timed_out=False,
            duration_seconds=0.25,
            log_path=log,
            command=("testharness", "I-add-01.elf"),
        )
        with working_directory(self.root), patch.object(
            recipe, "prepare_corpus", return_value=self.prepared_corpus()
        ) as prepare, patch.object(recipe, "run_corpus", return_value=(result,)) as run:
            self.invoke()

        self.assertEqual(self.report()["status"], "pass")
        self.assertEqual(prepare.call_args.kwargs["expected_target"], "cv32a65x_axi")
        self.assertEqual(run.call_args.kwargs["cycle_timeout"], 12345)
        self.assertEqual(run.call_args.kwargs["wall_timeout_seconds"], 60)

    def test_failed_elf_writes_report_and_propagates_nonzero(self) -> None:
        log = self.root / "artifacts/act4/fail.log"
        log.parent.mkdir(parents=True)
        log.write_text("fixture\n", encoding="utf-8")
        result = TestResult(
            test_id="I-add-01",
            elf="elfs/I-add-01.elf",
            passed=False,
            detail="missing current ELF marker",
            return_code=0,
            timed_out=False,
            duration_seconds=0.25,
            log_path=log,
            command=("testharness", "I-add-01.elf"),
        )
        with working_directory(self.root), patch.object(
            recipe, "prepare_corpus", return_value=self.prepared_corpus()
        ), patch.object(recipe, "run_corpus", return_value=(result,)):
            with self.assertRaises(typer.Exit) as raised:
                self.invoke()

        self.assertEqual(raised.exception.exit_code, 1)
        self.assertEqual(self.report()["status"], "fail")

    def test_preflight_failure_writes_report_and_propagates_nonzero(self) -> None:
        with working_directory(self.root), patch.object(
            recipe,
            "prepare_corpus",
            side_effect=CorpusError("manifest target mismatch"),
        ):
            with self.assertRaises(typer.Exit) as raised:
                self.invoke()

        self.assertEqual(raised.exception.exit_code, 1)
        report = self.report()
        self.assertEqual(report["status"], "fail")
        values = report["metrics"][0]["value"]
        self.assertIn("manifest target mismatch", values[0]["col"][4])

    def test_unsupported_target_is_rejected_before_corpus_access(self) -> None:
        with working_directory(self.root), patch.object(
            recipe, "prepare_corpus"
        ) as prepare:
            with self.assertRaises(typer.Exit) as raised:
                recipe.act4_run(
                    target="cv32a60x_axi",
                    corpus_directory=self.corpus_directory,
                    simulator=self.simulator,
                    cycle_timeout=1,
                    wall_timeout_seconds=1,
                    quiet=True,
                )

        self.assertEqual(raised.exception.exit_code, 1)
        prepare.assert_not_called()
        path = self.root / "artifacts/reports/report_act4_cv32a60x_axi.yml"
        self.assertEqual(yaml.safe_load(path.read_text())["status"], "fail")

    def test_packager_command_uses_repo_paths_and_never_invokes_git(self) -> None:
        expected_output = self.root / "verif/tests/act4/cv32a65x_axi/corpus"
        result = SimpleNamespace(
            test_count=2,
            archive_path=expected_output / "act4-elfs-cv32a65x_axi.tar.gz",
            manifest_path=expected_output / "corpus-manifest.json",
        )
        with working_directory(self.root), patch.object(
            recipe, "package_corpus", return_value=result
        ) as package:
            self.invoke_package()

        self.assertEqual(
            package.call_args.args,
            (
                self.root / "act-work/cv32a65x_axi/elfs",
                self.root / "act-work/cv32a65x_axi/resolved-profile.json",
                expected_output,
            ),
        )
        self.assertEqual(package.call_args.kwargs["target"], "cv32a65x_axi")
        self.assertFalse(package.call_args.kwargs["replace"])

    def test_packager_failure_and_unsupported_target_propagate_nonzero(self) -> None:
        with working_directory(self.root), patch.object(
            recipe,
            "package_corpus",
            side_effect=recipe.PackageError("zero final .elf files"),
        ) as package:
            with self.assertRaises(typer.Exit) as raised:
                self.invoke_package()
        self.assertEqual(raised.exception.exit_code, 1)
        package.assert_called_once()

        with working_directory(self.root), patch.object(
            recipe, "package_corpus"
        ) as package:
            with self.assertRaises(typer.Exit) as raised:
                self.invoke_package(target="cv32a60x_axi")
        self.assertEqual(raised.exception.exit_code, 1)
        package.assert_not_called()


if __name__ == "__main__":
    unittest.main()
