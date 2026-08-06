#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Tests for the fork-only master_candidate dashboard preview."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / ".github" / "scripts" / "dashboard_tiers"
WORKFLOW = (
    REPO_ROOT
    / ".github"
    / "workflows"
    / "fork-only-master-candidate-dashboard-preview.yml"
)

sys.path.insert(0, str(DASHBOARD_DIR))


def load_module(name: str, path: Path):
    """Load a dashboard script without requiring it to be a Python package."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collect_data = load_module("tier_collect_data", DASHBOARD_DIR / "collect_data.py")
generate_dashboard = load_module(
    "tier_generate_dashboard", DASHBOARD_DIR / "generate_dashboard.py"
)


class CollectorTests(unittest.TestCase):
    def test_branch_filter_is_url_encoded(self):
        endpoint = collect_data.build_runs_endpoint(
            "openhw-cva6-ci-tier1.yml",
            "jchen/master-candidate-tier-ci-master-adapter-v1",
        )
        self.assertEqual(
            endpoint,
            "workflows/openhw-cva6-ci-tier1.yml/runs?"
            "status=completed&branch="
            "jchen%2Fmaster-candidate-tier-ci-master-adapter-v1",
        )

    def test_fetch_count_is_passed_to_api(self):
        api_result = {"workflow_runs": [{"id": 1}, {"id": 2}, {"id": 3}]}
        with mock.patch.object(
            collect_data, "gh_api_list", return_value=api_result
        ) as api:
            runs = collect_data.fetch_runs(
                "AlexChenIC/cva6", "openhw-cva6-ci-tier2.yml", 2, "candidate"
            )

        self.assertEqual([run["id"] for run in runs], [1, 2])
        api.assert_called_once_with(
            "workflows/openhw-cva6-ci-tier2.yml/runs?"
            "status=completed&branch=candidate",
            "AlexChenIC/cva6",
            per_page=2,
        )

    def test_existing_history_is_filtered_to_requested_branch(self):
        runs = [
            {"id": 1, "head_branch": "master"},
            {"id": 2, "head_branch": "candidate"},
            {"id": 3, "head_branch": "another-candidate"},
        ]

        self.assertEqual(
            collect_data.filter_runs_by_branch(runs, "candidate"),
            [{"id": 2, "head_branch": "candidate"}],
        )
        self.assertIs(collect_data.filter_runs_by_branch(runs, ""), runs)


class GeneratorTests(unittest.TestCase):
    def test_master_candidate_profile_names_are_explicit(self):
        labels = [
            item["display_name"]
            for item in generate_dashboard.WORKFLOW_PROFILES["master-candidate"]
        ]
        self.assertEqual(
            labels,
            ["Tier 1 (cook.py)", "Tier 2 (cook.py)"],
        )

    def test_job_parser_accepts_adapter_names(self):
        parsed = collect_data.parse_job_name(
            "RV32 Tier1 cv32a60x_axi / base_rv32_p", "tier1"
        )
        self.assertEqual(
            parsed,
            {
                "arch": "rv32",
                "config": "cv32a60x_axi",
                "testcase": "base_rv32_p",
            },
        )

    def test_candidate_page_renders_scope_and_escapes_script_data(self):
        branch = "jchen/master-candidate-tier-ci-master-adapter-v1"
        unsafe_testcase = "base_rv32_p</script><script>alert(1)</script>"

        def run(run_id, conclusion, job):
            return {
                "id": run_id,
                "run_number": run_id,
                "conclusion": conclusion,
                "head_branch": branch,
                "head_sha": "c8aa646c",
                "passed_jobs": 1 if conclusion == "success" else 0,
                "failed_jobs": 1 if conclusion == "failure" else 0,
                "skipped_jobs": 0,
                "total_jobs": 1,
                "duration_seconds": 60,
                "created_at": "2026-08-06T10:33:48Z",
                "html_url": f"https://example.invalid/runs/{run_id}",
                "jobs": [job],
            }

        job = {
            "name": "candidate job",
            "arch": "rv32",
            "config": "cv32a60x_axi",
            "testcase": unsafe_testcase,
            "conclusion": "success",
            "duration_seconds": 30,
            "html_url": "https://example.invalid/jobs/1",
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "data"
            output_dir = tmp_path / "site"
            data_dir.mkdir()
            (data_dir / "runs_tier1.json").write_text(
                json.dumps([run(1, "success", job)]), encoding="utf-8"
            )
            (data_dir / "runs_tier2.json").write_text("[]", encoding="utf-8")

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
                    "--profile",
                    "master-candidate",
                    "--page-title",
                    "CVA6 master_candidate Tier CI Dashboard",
                    "--dashboard-title",
                    "CVA6 master_candidate Tier CI",
                    "--branch-label",
                    branch,
                    "--notice",
                    "Fork-only preview.",
                    "--back-link",
                    "../",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("CVA6 master_candidate Tier CI Dashboard", html)
            self.assertIn("Fork-only preview.", html)
            self.assertIn(branch, html)
            self.assertIn('href="../"', html)
            self.assertIn("Tier 1 (cook.py)", html)
            self.assertNotIn("</script><script>alert(1)</script>", html)
            self.assertIn(r"\u003c/script\u003e", html)
            self.assertTrue((output_dir / "assets" / "openhw-landscape.svg").is_file())


class WorkflowTests(unittest.TestCase):
    def test_preview_workflow_is_fork_scoped_and_non_persistent(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("jchen/master-candidate-dashboard-preview-v1", text)
        self.assertIn("/tmp/dash-site/master-candidate", text)  # nosec B108
        self.assertIn("--branch \"$MASTER_CANDIDATE_CI_BRANCH\"", text)
        self.assertIn("--workflows tier1 tier2", text)
        self.assertIn("github.repository == 'AlexChenIC/cva6'", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("git push", text)


if __name__ == "__main__":
    unittest.main()
