#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / ".github" / "scripts" / "dashboard_tiers"
sys.path.insert(0, str(DASHBOARD_DIR))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_module("tier_dashboard_collector", DASHBOARD_DIR / "collect_data.py")
generator = load_module(
    "tier_dashboard_generator", DASHBOARD_DIR / "generate_dashboard.py"
)
thales_collector = load_module(
    "thales_dashboard_collector", DASHBOARD_DIR / "collect_thales_reference.py"
)


class GitHubCollectorTest(unittest.TestCase):
    def test_only_tier_workflows_are_collected(self) -> None:
        self.assertEqual(
            collector.WORKFLOWS,
            {
                "tier1": "openhw-cva6-ci-tier1.yml",
                "tier2": "openhw-cva6-ci-tier2.yml",
            },
        )

    def test_branch_filter_is_encoded(self) -> None:
        endpoint = collector.build_runs_endpoint(
            "openhw-cva6-ci-tier1.yml", 20, "jchen/candidate preview"
        )
        self.assertEqual(
            endpoint,
            "workflows/openhw-cva6-ci-tier1.yml/runs?"
            "status=completed&per_page=20&branch=jchen%2Fcandidate+preview",
        )

    def test_target_branch_keeps_pushes_and_prs(self) -> None:
        runs = [
            {"id": 1, "head_branch": "master_candidate"},
            {
                "id": 2,
                "head_branch": "jchen/change",
                "pull_requests": [{"base": {"ref": "master_candidate"}}],
            },
            {"id": 3, "head_branch": "master"},
        ]
        self.assertEqual(
            [
                run["id"]
                for run in collector.filter_runs(
                    runs, base_branch="master_candidate"
                )
            ],
            [1, 2],
        )
        self.assertEqual(
            [
                run["id"]
                for run in collector.filter_runs(
                    runs,
                    branch="jchen/change",
                    base_branch="master_candidate",
                )
            ],
            [2],
        )

    def test_current_tier_job_name_is_parsed(self) -> None:
        parsed = collector.parse_job_name(
            "RV32 Tier2 cv32a65x_axi / base-pmp", "tier2"
        )
        self.assertEqual(
            parsed,
            {
                "arch": "rv32",
                "config": "cv32a65x_axi",
                "testcase": "base-pmp",
            },
        )
        self.assertIsNone(
            collector.parse_job_name(
                "execute-riscv32-tests (base, config, simulator)", "tier2"
            )
        )


class ThalesCollectorTest(unittest.TestCase):
    PAGE = """
    <main class="col px-md-4"id=accordion>
    <div class="list-group-item list-group-item-action py-3">
      <button class="btn btn-success m-1">PASS</button>
      <strong>Candidate validation
        <span class="badge bg-warning text-white rounded-pill"> dev/pipeline_mc</span>
        <a href=https://github.com/openhwgroup/cva6/commit/0123456789abcdef0123456789abcdef01234567>sha</a>
      </strong>
      <small>Authored by CI User | Pipeline ID:
        <a href=https://gitlab.thales-invia.fr/riscv-ci/cva6/-/pipelines/58367>58367</a>
      </small>
      <script>timeDifference_absolute(125)</script>
      <script>timeDifference_from_now(1786881790)</script>
    </div>
    """

    RELEVANT_PAGE = PAGE + """
    <div class="list-group-item list-group-item-action py-3">
      <button class="btn btn-danger m-1">FAIL</button>
      <strong>Feature validation
        <span class="badge bg-warning text-white rounded-pill"> dev/relevant</span>
        <a href=https://github.com/openhwgroup/cva6/commit/89abcdef0123456789abcdef0123456789abcdef>sha</a>
      </strong>
      <small>Authored by CI User | Pipeline ID:
        <a href=https://gitlab.thales-invia.fr/riscv-ci/cva6/-/pipelines/58298>58298</a>
      </small>
      <script>timeDifference_absolute(5916)</script>
      <script>timeDifference_from_now(1786631841)</script>
      <div class="col-12 border-top p-1">
        <button class="btn btn-success m-1"><small>PASS</small></button>
        <strong>Testlist RTL run - cv32a60x_axi - base_rv32_p</strong>
        <a href=https://gitlab.thales-invia.fr/riscv-ci/cva6/-/jobs/296314>job</a>
        <script>timeDifference_absolute(25)</script>
      </div>
      <div class="col-12 border-top p-1">
        <button class="btn btn-success m-1"><small>PASS</small></button>
        <strong>Testlist RTL run - cv32a65x_axi - base_rv32_p</strong>
        <a href=https://gitlab.thales-invia.fr/riscv-ci/cva6/-/jobs/296333>job</a>
        <script>timeDifference_absolute(26)</script>
      </div>
      <div class="col-12 border-top p-1">
        <button class="btn btn-success m-1"><small>PASS</small></button>
        <strong>Testlist RTL run - cv32a65x_axi - base_pmp</strong>
        <a href=https://gitlab.thales-invia.fr/riscv-ci/cva6/-/jobs/296335>job</a>
        <script>timeDifference_absolute(29)</script>
      </div>
      <div class="col-12 border-top p-1">
        <button class="btn btn-danger m-1"><small>FAIL</small></button>
        <strong>Testlist RTL run - cv32a60x - base_zcmt</strong>
        <script>timeDifference_absolute(31)</script>
      </div>
    </div>
    """

    def test_latest_public_pipeline_is_parsed(self) -> None:
        result = thales_collector.parse_latest_pipeline(self.PAGE)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["branch"], "dev/pipeline_mc")
        self.assertEqual(result["head_sha"], "01234567")
        self.assertEqual(result["pipeline_id"], 58367)
        self.assertEqual(result["backend"], "VCS/UVM")
        self.assertNotIn("pipeline_url", result)

    def test_all_testlist_jobs_feed_public_history(self) -> None:
        result = thales_collector.parse_public_dashboard(self.RELEVANT_PAGE)
        snapshot = result["latest_matrix_snapshot"]

        self.assertEqual(result["pipeline_id"], 58367)
        self.assertEqual(snapshot["pipeline_id"], 58298)
        self.assertEqual(snapshot["total_jobs"], 4)
        self.assertEqual(snapshot["passed_jobs"], 3)
        self.assertEqual(snapshot["failed_jobs"], 1)
        self.assertEqual(snapshot["pass_rate"], 75.0)
        self.assertEqual(
            {(job["config"], job["testcase"]) for job in snapshot["jobs"]},
            {
                ("cv32a60x_axi", "base_rv32_p"),
                ("cv32a65x_axi", "base_rv32_p"),
                ("cv32a65x_axi", "base_pmp"),
                ("cv32a60x", "base_zcmt"),
            },
        )
        self.assertEqual(len(result["history"]), 1)
        self.assertEqual(result["matrix_snapshot"], {})
        self.assertNotIn("pipeline_url", json.dumps(result))
        self.assertNotIn("/-/jobs/", json.dumps(result))

    def test_master_candidate_matrix_is_read_from_gitlab_ci(self) -> None:
        definition = thales_collector.parse_matrix_definition(
            (REPO_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8"),
            "master_candidate",
            "67625b2a344772ad7776cb7f5df5670623781185",
        )

        self.assertEqual(definition["backend"], "VCS/UVM")
        self.assertEqual(definition["total_configs"], 20)
        self.assertEqual(definition["total_testlists"], 10)
        self.assertEqual(definition["total_jobs"], 59)
        self.assertIn("cv32a60x", definition["configs"])
        self.assertIn("cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi", definition["configs"])
        self.assertIn("base_rv64_amo_v", definition["testlists"])

    def test_previous_reference_survives_fetch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "thales.json"
            output.write_text('{"available": true}', encoding="utf-8")
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "collect_thales_reference.py",
                        "--input-html",
                        str(Path(directory) / "missing.html"),
                        "--output",
                        str(output),
                    ],
                ),
            ):
                thales_collector.main()
            retained = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(retained["available"])
            self.assertTrue(retained["stale"])
            self.assertIn("missing.html", retained["last_error"])


class GeneratorTest(unittest.TestCase):
    def test_dashboard_renders_two_backends_without_legacy_workflow(self) -> None:
        branch = "jchen/master-candidate-openhw-tier-ci"
        full_sha = "e7c272c93dc0db08d030f1ebe7412af8d78dae6b"

        def run(run_id: int, testcase: str) -> dict:
            return {
                "id": run_id,
                "run_number": run_id,
                "conclusion": "success",
                "head_branch": branch,
                "head_sha": full_sha[:8],
                "head_sha_full": full_sha,
                "passed_jobs": 1,
                "failed_jobs": 0,
                "skipped_jobs": 0,
                "total_jobs": 1,
                "duration_seconds": 60,
                "created_at": "2026-08-18T10:00:00Z",
                "html_url": f"https://github.com/AlexChenIC/cva6/actions/runs/{run_id}",
                "event": "workflow_dispatch",
                "jobs": [
                    {
                        "arch": "rv32",
                        "config": "cv32a65x_axi",
                        "testcase": testcase,
                        "conclusion": "success",
                        "duration_seconds": 30,
                        "html_url": "https://github.com/AlexChenIC/cva6/actions/jobs/1",
                    }
                ],
            }

        matrix_definition = thales_collector.parse_matrix_definition(
            (REPO_ROOT / ".gitlab-ci.yml").read_text(encoding="utf-8"),
            "master_candidate",
            "67625b2a344772ad7776cb7f5df5670623781185",
        )
        thales = thales_collector.parse_public_dashboard(
            ThalesCollectorTest.RELEVANT_PAGE,
            matrix_definition=matrix_definition,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir = root / "data"
            output_dir = root / "site"
            data_dir.mkdir()
            (data_dir / "runs_tier1.json").write_text(
                json.dumps([run(1, "base-rv32-p")]), encoding="utf-8"
            )
            (data_dir / "runs_tier2.json").write_text(
                json.dumps([run(2, "base-pmp</script>")]), encoding="utf-8"
            )
            (data_dir / "thales_reference.json").write_text(
                json.dumps(thales), encoding="utf-8"
            )

            subprocess.run(
                [
                    sys.executable,
                    str(DASHBOARD_DIR / "generate_dashboard.py"),
                    "--data-dir",
                    str(data_dir),
                    "--output-dir",
                    str(output_dir),
                    "--repo",
                    "AlexChenIC/cva6",
                ],
                cwd=REPO_ROOT,
                check=True,
            )
            page = (output_dir / "index.html").read_text(encoding="utf-8")

        self.assertIn(">Tier 1<", page)
        self.assertIn(">Tier 2<", page)
        self.assertNotIn("Tier 1 (Verilator)", page)
        self.assertNotIn("Tier 2 (Verilator)", page)
        self.assertIn("GitHub Actions · Verilator/TestHarness", page)
        self.assertIn("Verilator/TestHarness", page)
        self.assertIn("Thales GitLab Reference", page)
        self.assertNotIn("Thales GitLab (Reference, VCS/UVM)", page)
        self.assertIn("GitLab CI · VCS/UVM", page)
        self.assertIn("VCS/UVM", page)
        self.assertIn("Thales GitLab", page)
        self.assertIn("Thales GitLab Testlist Trend", page)
        self.assertIn("59 configured jobs", page)
        self.assertIn("No public pipeline matched this exact revision", page)
        self.assertNotIn("Independent evidence lanes", page)
        self.assertNotIn("GitLab pipeline", page)
        self.assertNotIn("gitlab.thales-invia.fr/riscv-ci/cva6/-/pipelines", page)
        self.assertIn(thales_collector.DEFAULT_URL, page)
        self.assertNotIn("runs_ci.json", page)
        self.assertNotIn("openhw-cva6-ci.yml", page)
        self.assertNotIn("</script><script>", page)
        self.assertIn(r"\u003c/script\u003e", page)

    def test_source_relation_requires_the_same_sha(self) -> None:
        workflows = [{"latest": {"head_sha_full": "github-sha"}}]
        self.assertEqual(
            generator.source_relation(
                workflows, {"head_sha_full": "thales-sha"}
            )["kind"],
            "different",
        )
        self.assertEqual(
            generator.source_relation(
                workflows, {"head_sha_full": "github-sha"}
            )["kind"],
            "match",
        )
        self.assertEqual(
            generator.source_relation(
                [
                    {"latest": {"head_sha_full": "github-sha"}},
                    {"latest": {"head_sha_full": "other-github-sha"}},
                ],
                {"head_sha_full": "github-sha"},
            )["kind"],
            "different",
        )


class WorkflowTest(unittest.TestCase):
    def test_workflow_tracks_tiers_and_collects_reference(self) -> None:
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "openhw-cva6-tier-dashboard.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("openhw-cva6-ci-tier1", workflow)
        self.assertIn("openhw-cva6-ci-tier2", workflow)
        self.assertIn("collect_thales_reference.py", workflow)
        self.assertIn("repository: openhwgroup/cva6", workflow)
        self.assertIn(
            "--matrix-file upstream-master-candidate/.gitlab-ci.yml", workflow
        )
        self.assertIn("PyYAML==6.0.3", workflow)
        self.assertIn("DASHBOARD_TARGET_BRANCH: master_candidate", workflow)
        self.assertIn('--base-branch "$DASHBOARD_TARGET_BRANCH"', workflow)
        self.assertNotIn("openhw-cva6-ci.yml", workflow)
        self.assertNotIn("\n      - ci\n", workflow)


if __name__ == "__main__":
    unittest.main()
