# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "dashboard_candidate"))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collect = load("candidate_collect", SCRIPTS / "dashboard_candidate/collect_data.py")
generate = load(
    "candidate_generate", SCRIPTS / "dashboard_candidate/generate_dashboard.py"
)
thales = load("thales", SCRIPTS / "dashboard_candidate/collect_thales_reference.py")
master = load("master_collect", SCRIPTS / "dashboard_tiers/collect_data.py")


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.run = {"id": 123, "run_attempt": 2, "head_sha": "a" * 40}
        self.data = {
            "schema_version": 1,
            "repository": "o/cva6",
            "run_id": "123",
            "run_attempt": "2",
            "target": "cv32a60x_axi",
            "testcase": "base-rv32-p",
            "simulator": "verilator",
            "reference_model": "spike-offline",
            "source_revision": "a" * 40,
            "status": "PASS",
            "commands": [{"exit_code": 0, "timed_out": False}] * 3,
            "results": {
                "target": "cv32a60x_axi",
                "status": "PASS",
                "iss_enabled": True,
                "total": 1,
                "passed": 1,
                "failed": 0,
                "cases": [{"status": "PASS"}],
            },
        }

    def payload(self, data, name="ci-results/evidence.json"):
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(name, json.dumps(data))
        return buffer.getvalue()

    def parse(self, data):
        return collect.parse_evidence(
            self.payload(data),
            repo="o/cva6",
            run=self.run,
            target="cv32a60x_axi",
            suite="base-rv32-p",
        )

    def test_evidence_identity_and_counts(self):
        self.assertEqual(self.parse(self.data)["status"], "PASS")
        for key, value in [
            ("repository", "evil/repo"),
            ("run_id", "124"),
            ("run_attempt", "1"),
            ("source_revision", "b" * 40),
            ("schema_version", 99),
            ("target", "other"),
            ("commands", []),
            ("results", {}),
            ("status", "unknown"),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.parse({**self.data, key: value})

    def test_pr_merge_sha_is_preserved_not_replaced_by_head(self):
        data = {**self.data, "event_head_sha": "a" * 40, "source_revision": "b" * 40}
        self.assertEqual(self.parse(data)["source_revision"], "b" * 40)

    def test_malformed_evidence_fails_closed(self):
        for key in ("results", "commands", "environment", "source_revision"):
            for value in (None, [], 1):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    self.parse({**self.data, key: value})
        with self.assertRaises(ValueError):
            self.parse(
                {**self.data, "results": {**self.data["results"], "total": True}}
            )

    def test_failed_preview_cannot_reuse_production_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text(
                json.dumps(
                    {"repo": "o/cva6", "branch": "", "base_branch": "master_candidate"}
                )
            )
            self.assertTrue(
                collect.same_collection_scope(path, "o/cva6", "", "master_candidate")
            )
            self.assertFalse(
                collect.same_collection_scope(
                    path, "o/cva6", "preview", "master_candidate"
                )
            )

    def test_path_traversal_archive_is_not_extracted(self):
        with self.assertRaises(ValueError):
            collect.parse_evidence(
                self.payload(self.data, "../evidence.json"),
                repo="o/cva6",
                run=self.run,
                target="cv32a60x_axi",
                suite="base-rv32-p",
            )

    def test_oversize_payload_rejected(self):
        with patch.object(collect, "MAX_ARCHIVE", 1), self.assertRaises(ValueError):
            self.parse(self.data)
        with patch.object(collect, "MAX_JSON", 1), self.assertRaises(ValueError):
            self.parse(self.data)

    def test_job_pagination_and_attempt_specific_endpoint(self):
        with patch.object(
            collect,
            "gh_api",
            side_effect=[
                {"jobs": [{"id": i} for i in range(100)]},
                {"jobs": [{"id": 100}]},
            ],
        ) as api:
            self.assertEqual(
                len(collect.paged("o/cva6", "runs/123/attempts/2/jobs", "jobs")), 101
            )
            self.assertIn("attempts/2/jobs", api.call_args.args[1])
            self.assertIn("page=2", api.call_args.args[1])

    def test_branch_lanes_never_mix(self):
        candidate = {
            "head_branch": "work",
            "pull_requests": [{"base": {"ref": "master_candidate"}}],
        }
        self.assertTrue(collect.belongs(candidate, "", "master_candidate"))
        self.assertFalse(master.is_master_run(candidate))
        self.assertFalse(
            collect.belongs({"head_branch": "master"}, "", "master_candidate")
        )
        self.assertTrue(collect.belongs(candidate, "work", "master_candidate"))

    def test_rerun_replaces_old_master_outcome(self):
        old = {"id": 1, "head_branch": "master", "conclusion": "failure"}
        new = {**old, "conclusion": "success"}
        self.assertEqual(master.merge_runs([old], [new]), [new])

    def test_empty_latest_matrix_does_not_borrow_old_pass(self):
        data = {
            "tier1": [
                {"jobs": []},
                {"jobs": [{"config": "c", "testcase": "s", "conclusion": "success"}]},
            ]
        }
        matrix, order = generate.build_matrix(data)
        self.assertEqual(matrix, {})
        self.assertEqual(order["tier1"]["configs"], [])

    def test_zero_jobs_is_missing_chart_data_not_zero_percent(self):
        chart = generate.build_chart_data(
            {"tier1": [{"total_jobs": 0, "duration_seconds": 0}]}
        )
        self.assertEqual(chart["tier1"]["pass_rates"], [None])

    def test_comparison_uses_tested_not_event_sha(self):
        workflows = [{"latest": {"head_sha_full": "a", "tested_source_sha": "b"}}]
        self.assertEqual(
            generate.source_relation(workflows, {"head_sha_full": "a"})["kind"],
            "different",
        )
        self.assertEqual(
            generate.source_relation([{"latest": {}}], {"head_sha_full": "a"})["kind"],
            "unknown",
        )

    def test_public_thales_parser_accepts_current_org_and_quoted_link(self):
        card = """<div class="list-group-item list-group-item-action py-3">
        <button class="btn btn-danger">FAIL</button>
        <strong>Change <span class="badge bg-warning">dev/test</span></strong>
        <a href="https://github.com/openhwfoundation/cva6/commit/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">sha</a>
        <a href="https://gitlab.thales-invia.fr/riscv-ci/cva6/-/pipelines/123">id</a>
        timeDifference_from_now(1787000000) timeDifference_absolute(90)
        """
        result = thales.parse_public_dashboard(card)
        self.assertEqual((result["pipeline_id"], result["status_label"]), (123, "FAIL"))
        self.assertNotIn("testlist", result)

    def test_thales_markup_failure_is_explicit(self):
        with self.assertRaises(ValueError):
            thales.parse_public_dashboard("<html>changed structure</html>")
        with self.assertRaises(ValueError):
            thales.fetch_page("http://localhost/", 1)

    def test_jinja_escapes_untrusted_branch_and_script_context(self):
        from jinja2 import Environment, FileSystemLoader

        env = Environment(
            loader=FileSystemLoader(SCRIPTS / "dashboard_candidate/templates"),
            autoescape=True,
        )
        workflows = generate.build_workflows_context(
            {
                "tier1": [
                    {
                        "head_branch": "<script>alert(1)</script>",
                        "conclusion": "unknown",
                        "jobs": [],
                        "failed_jobs": 0,
                        "total_jobs": 0,
                        "passed_jobs": 0,
                        "skipped_jobs": 0,
                        "environment": {"available": False},
                    }
                ]
            },
            datetime.now(timezone.utc),
        )
        html = env.get_template("index.html").render(
            workflows=workflows,
            thales={"available": False},
            collection={},
            source_relation={"kind": "unknown"},
            matrix_data={},
            matrix_orders={},
            matrix_metadata={},
            chart_data=generate.build_chart_data({}),
            default_matrix_wf="tier1",
        )
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("Latest testlist evidence", html)
        self.assertIn("No matrix job results are available for the latest runs.", html)
        self.assertNotIn("No CI run data available yet.", html)


if __name__ == "__main__":
    unittest.main()
