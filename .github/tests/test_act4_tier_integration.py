# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / ".github/scripts/run-tier-regression.sh"
TIER1_WORKFLOW = REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier1.yml"
TIER2_WORKFLOW = REPO_ROOT / ".github/workflows/openhw-cva6-ci-tier2.yml"


def write_executable(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o755)


class Act4TierIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / "verif/sim").mkdir(parents=True)
        (self.root / "verif/sim/setup-env.sh").write_text(
            "export RISCV=/fixture/riscv\n", encoding="utf-8"
        )

        self.corpus = self.root / "verif/tests/act4/cv32a65x_axi/corpus"
        self.corpus.mkdir(parents=True)
        manifest = {
            "schema_version": 1,
            "target": "cv32a65x_axi",
            "scope": "basic-architectural-subset",
            "certification_claim": False,
            "archive": {"name": "fixture.tar.gz", "sha256": "a" * 64},
            "generation": {
                "act_commit": "b" * 40,
                "cva6_commit": "c" * 40,
                "profile_sha256": "d" * 64,
                "image_digest": "sha256:" + "e" * 64,
                "image_platform": "linux/arm64",
            },
            "tests": [{"id": "I-add-00"}],
        }
        (self.corpus / "corpus-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        self.bin_directory = self.root / "fixture-bin"
        self.bin_directory.mkdir()
        write_executable(
            self.bin_directory / "git",
            "#!/usr/bin/env bash\n"
            'if [[ "$*" == "rev-parse HEAD" ]]; then\n'
            "  echo 0123456789abcdef0123456789abcdef01234567\n"
            "  exit 0\n"
            "fi\n"
            "exit 2\n",
        )
        write_executable(
            self.bin_directory / "make",
            "#!/usr/bin/env bash\n"
            "set -u\n"
            'if [[ -n "${SPIKE_TANDEM+x}" ]]; then\n'
            "  echo 'SPIKE_TANDEM leaked into TestHarness build' >&2\n"
            "  exit 91\n"
            "fi\n"
            "printf '%s\\n' \"$@\" > fixture-make-args.txt\n"
            'if [[ "${FAKE_MAKE_RC:-0}" != 0 ]]; then\n'
            '  exit "${FAKE_MAKE_RC}"\n'
            "fi\n"
            "mkdir -p work-ver\n"
            "printf '#!/usr/bin/env bash\\nexit 0\\n' > work-ver/Variane_testharness\n"
            "chmod +x work-ver/Variane_testharness\n",
        )
        write_executable(
            self.root / "cook.py",
            "#!/usr/bin/env bash\n"
            "set -u\n"
            'if [[ -n "${SPIKE_TANDEM+x}" ]]; then\n'
            "  echo 'SPIKE_TANDEM leaked into ACT4 runtime' >&2\n"
            "  exit 92\n"
            "fi\n"
            "printf '%s\\n' \"$@\" > fixture-cook-args.txt\n"
            'if [[ "${FAKE_SKIP_OUTPUTS:-0}" != 1 ]]; then\n'
            "  mkdir -p artifacts/reports\n"
            "  mkdir -p artifacts/act4/cv32a65x_axi/profile/logs\n"
            "  printf 'status: pass\\n' > "
            "artifacts/reports/report_act4_cv32a65x_axi.yml\n"
            "  printf 'fixture self-check success\\n' > "
            "artifacts/act4/cv32a65x_axi/profile/logs/I-add-00.log\n"
            "fi\n"
            'exit "${FAKE_COOK_RC:-0}"\n',
        )

    def run_runner(self, **overrides: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.update(
            {
                "PATH": f"{self.bin_directory}{os.pathsep}{environment['PATH']}",
                "TIER_NAME": "Tier 1 ACT4 fixture",
                "TIER_MODE": "act4-prebuilt",
                "TIER_CONFIG": "cv32a65x_axi",
                "TIER_ACT4_CORPUS": str(self.corpus),
                "TIER_ACT4_CYCLE_TIMEOUT": "123456",
                "TIER_ACT4_WALL_TIMEOUT_SECONDS": "45",
                "NUM_JOBS": "3",
                # The dedicated mode must remove this inherited opt-in from
                # both the build and runtime command environments.
                "SPIKE_TANDEM": "1",
            }
        )
        environment.update(overrides)
        return subprocess.run(
            ["bash", str(RUNNER)],
            cwd=self.root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_success_uses_frozen_corpus_without_live_tandem(self) -> None:
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.root / "fixture-make-args.txt").read_text().splitlines(),
            ["-j3", "verilate", "target=cv32a65x_axi"],
        )
        self.assertEqual(
            (self.root / "fixture-cook-args.txt").read_text().splitlines(),
            [
                "act4-run",
                "--target",
                "cv32a65x_axi",
                "--corpus-directory",
                str(self.corpus),
                "--simulator",
                "work-ver/Variane_testharness",
                "--cycle-timeout",
                "123456",
                "--wall-timeout-seconds",
                "45",
            ],
        )
        metadata = (self.root / "ci-results/metadata.txt").read_text()
        self.assertIn("mode=act4-prebuilt\n", metadata)
        self.assertIn("simulator=work-ver/Variane_testharness\n", metadata)
        self.assertNotIn("simulator=veri-testharness,spike\n", metadata)
        self.assertIn("act4_live_reference_model=disabled\n", metadata)
        self.assertIn("act4_testharness_spike_tandem=disabled\n", metadata)
        self.assertIn("act4_build_jobs=3\n", metadata)
        self.assertIn("act4_runtime_result=pass\n", metadata)
        self.assertIn("act4_manifest_status=validated\n", metadata)
        self.assertIn("act4_scope=basic-architectural-subset\n", metadata)
        self.assertIn("act4_certification_claim=false\n", metadata)
        self.assertIn("act4_generation_image_platform=linux/arm64\n", metadata)
        self.assertIn("act4_test_count=1\n", metadata)
        self.assertEqual((self.root / "ci-results/exit_code").read_text(), "0\n")
        self.assertTrue((self.root / "ci-results/act4-corpus-manifest.json").is_file())
        self.assertTrue(
            (self.root / "ci-results/reports/report_act4_cv32a65x_axi.yml").is_file()
        )

    def test_unsupported_target_stops_before_build(self) -> None:
        result = self.run_runner(TIER_CONFIG="cv32a60x_axi")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("currently supports only cv32a65x_axi", result.stdout)
        self.assertFalse((self.root / "fixture-make-args.txt").exists())
        self.assertFalse((self.root / "fixture-cook-args.txt").exists())

    def test_invalid_timeout_stops_before_build(self) -> None:
        result = self.run_runner(TIER_ACT4_WALL_TIMEOUT_SECONDS="0")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn(
            "TIER_ACT4_WALL_TIMEOUT_SECONDS must be a positive integer", result.stdout
        )
        self.assertFalse((self.root / "fixture-make-args.txt").exists())

    def test_testharness_build_failure_stops_before_cook(self) -> None:
        result = self.run_runner(FAKE_MAKE_RC="6")
        self.assertEqual(result.returncode, 6, result.stdout)
        self.assertFalse((self.root / "fixture-cook-args.txt").exists())
        metadata = (self.root / "ci-results/metadata.txt").read_text()
        self.assertIn("act4_runtime_result=not-run\n", metadata)
        self.assertIn("act4_manifest_status=present-unvalidated\n", metadata)
        self.assertEqual((self.root / "ci-results/exit_code").read_text(), "6\n")

    def test_cook_failure_is_propagated_and_evidence_is_collected(self) -> None:
        result = self.run_runner(FAKE_COOK_RC="9")
        self.assertEqual(result.returncode, 9, result.stdout)
        metadata = (self.root / "ci-results/metadata.txt").read_text()
        self.assertIn("act4_runtime_result=fail\n", metadata)
        self.assertIn("act4_manifest_status=present-unvalidated\n", metadata)
        self.assertEqual((self.root / "ci-results/exit_code").read_text(), "9\n")
        self.assertTrue(
            (self.root / "ci-results/reports/report_act4_cv32a65x_axi.yml").is_file()
        )
        self.assertTrue((self.root / "ci-results/act4-corpus-manifest.json").is_file())

    def test_zero_result_success_is_rejected(self) -> None:
        result = self.run_runner(FAKE_SKIP_OUTPUTS="1")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("produced no ACT4 Cook report", result.stdout)
        self.assertEqual((self.root / "ci-results/exit_code").read_text(), "1\n")

    def test_existing_script_mode_preserves_sourced_environment(self) -> None:
        regression = self.root / "verif/regress/fixture.sh"
        regression.parent.mkdir(parents=True)
        regression.write_text(
            "#!/usr/bin/env bash\n"
            '[[ "${RISCV:-}" == /fixture/riscv ]]\n'
            "mkdir -p verif/sim/out-fixture\n",
            encoding="utf-8",
        )
        stale_act4_log = self.root / "artifacts/act4/old/profile/logs/stale.log"
        stale_act4_log.parent.mkdir(parents=True)
        stale_act4_log.write_text("fixture *** FAILED *** log\n", encoding="utf-8")
        result = self.run_runner(
            TIER_MODE="script",
            TIER_CONFIG="cv32a65x_axi",
            TIER_TESTCASE="fixture",
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((self.root / "ci-results/exit_code").read_text(), "0\n")

    def test_existing_script_mode_propagates_child_failure(self) -> None:
        regression = self.root / "verif/regress/fixture-fail.sh"
        regression.parent.mkdir(parents=True)
        regression.write_text("#!/usr/bin/env bash\nexit 7\n", encoding="utf-8")
        result = self.run_runner(
            TIER_MODE="script",
            TIER_CONFIG="cv32a65x_axi",
            TIER_TESTCASE="fixture-fail",
        )
        self.assertEqual(result.returncode, 7, result.stdout)
        self.assertEqual((self.root / "ci-results/exit_code").read_text(), "7\n")

    def test_act4_lane_is_owned_by_tier1_workflow(self) -> None:
        tier1 = yaml.safe_load(TIER1_WORKFLOW.read_text(encoding="utf-8"))
        tier2 = yaml.safe_load(TIER2_WORKFLOW.read_text(encoding="utf-8"))
        job_name = "execute-cv32a65x-axi-act4-tier1"

        self.assertIn(job_name, tier1["jobs"])
        self.assertNotIn("execute-cv32a65x-axi-act4-tier2", tier2["jobs"])

        setup_steps = tier1["jobs"]["setup-tools"]["steps"]
        checkout = next(step for step in setup_steps if "uses" in step)
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        self.assertTrue(
            any(
                step.get("name") == "Test ACT4 frozen-corpus safety"
                for step in setup_steps
            )
        )
        self.assertFalse(
            any(
                step.get("name") == "Test ACT4 frozen-corpus safety"
                for step in tier2["jobs"]["setup-tools"]["steps"]
            )
        )

        act4_job = tier1["jobs"][job_name]
        run_step = next(
            step
            for step in act4_job["steps"]
            if step.get("name") == "Run cv32a65x_axi ACT4 frozen corpus"
        )
        self.assertEqual(run_step["env"]["TIER_NAME"], "Tier 1 ACT4")
        self.assertEqual(run_step["env"]["TIER_MODE"], "act4-prebuilt")
        self.assertEqual(run_step["env"]["TIER_CONFIG"], "cv32a65x_axi")
        upload_step = next(
            step
            for step in act4_job["steps"]
            if step.get("name") == "Upload ACT4 Results"
        )
        self.assertEqual(upload_step["with"]["name"], "tier1-act4-cv32a65x-axi")


if __name__ == "__main__":
    unittest.main()
