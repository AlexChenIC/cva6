#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Offline migration checks: mocked gh, real collectors/generators, no CI runs."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github/scripts/dashboard_legacy_migration.py"
REFERENCE = Path(os.environ.get("CVA6_DASHBOARD_REFERENCE", ROOT / "candidate-dashboard-source"))
spec = importlib.util.spec_from_file_location("migration", SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)
NEW_SHA = "a" * 40
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['FAKE_GH_LOG'], 'a') as stream:
    stream.write(json.dumps(args) + '\n')
endpoint = next((arg for arg in args if arg.startswith(('repos/', '/repos/'))), '')
if '/git/ref/' in endpoint:
    print(os.environ['FAKE_SHA'])
elif '/contents/' in endpoint:
    print('{}')
elif '/dispatches' in endpoint:
    pass
elif '/workflows/' in endpoint and '/runs?' in endpoint:
    print(json.dumps({'workflow_runs': json.loads(os.environ['FAKE_RUNS'])}))
elif '/jobs?' in endpoint:
    print(json.dumps({'jobs': [{'name': 'RV32 Tier2 cv32a60x_axi / base-rv32-p', 'conclusion': 'success'}]}))
elif '/artifacts?' in endpoint:
    print(json.dumps({'artifacts': []}))
else:
    raise SystemExit('unexpected gh endpoint: ' + endpoint)
'''


def run_record(identifier, branch, sha=migration.LEGACY_SHA):
    return {"id": identifier, "head_branch": branch, "head_sha": sha[:8],
            "head_sha_full": sha, "event": "workflow_dispatch", "status": "completed",
            "conclusion": "success", "run_number": identifier,
            "created_at": f"2026-10-09T00:{identifier % 60:02d}:00Z",
            "html_url": f"https://github.com/AlexChenIC/cva6/actions/runs/{identifier}",
            "total_jobs": 1, "passed_jobs": 1, "failed_jobs": 0, "skipped_jobs": 0,
            "duration_seconds": 0,
            "environment": {"available": False},
            "jobs": [{"config": "cv32a60x_axi", "testcase": "base-rv32-p",
                      "conclusion": "success"}]}


def workflow(name):
    return yaml.load((ROOT / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "gh.log"
        fake = self.directory / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        self.environment = {**os.environ, "PATH": f"{self.directory}:{os.environ['PATH']}",
                            "FAKE_GH_LOG": str(self.log), "FAKE_SHA": migration.LEGACY_SHA,
                            "GITHUB_REPOSITORY": "AlexChenIC/cva6",
                            "GITHUB_STEP_SUMMARY": str(self.directory / "summary")}

    def write_runs(self, directory, runs, name="runs_tier2.json"):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(json.dumps(runs))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_nightly_dispatches_only_the_frozen_legacy_target(self):
        wf = workflow("fork-only-master-candidate-tier2-nightly.yml")
        self.assertEqual(wf["env"]["TIER_BRANCH"], migration.LEGACY_BRANCH)
        self.assertEqual(wf["env"]["LEGACY_SHA"], migration.LEGACY_SHA)
        steps = wf["jobs"]["dispatch"]["steps"]
        script = "\n".join(step["run"] for step in steps)
        env = {**self.environment, **wf["env"]}
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], env=env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        posts = [call for call in self.calls() if "POST" in call]
        self.assertEqual(len(posts), 1)
        self.assertIn(f"ref={migration.LEGACY_BRANCH}", posts[0])
        self.log.unlink()
        result = subprocess.run(["bash", "-euo", "pipefail", "-c", script],
                                env={**env, "FAKE_SHA": NEW_SHA}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("POST" in call for call in self.calls()))

    def test_dashboard_event_gate_rejects_new_source_and_moved_legacy(self):
        wf = workflow("fork-only-master-candidate-dashboard-overlay.yml")
        trigger = wf["on"]["workflow_run"]
        self.assertEqual(trigger["branches"], [migration.LEGACY_BRANCH])
        self.assertEqual(set(trigger["workflows"]), {"openhw-cva6-ci-tier1", "openhw-cva6-ci-tier2"})
        self.assertEqual(wf["env"]["DASHBOARD_SOURCE_SHA"], migration.DASHBOARD_SOURCE_SHA)
        expression = wf["jobs"]["build"]["if"].replace("&&", "and").replace("||", "or")
        def accepted(branch, sha, event="workflow_run"):
            github = SimpleNamespace(repository="AlexChenIC/cva6", event_name=event,
                                     event=SimpleNamespace(workflow_run=SimpleNamespace(head_branch=branch, head_sha=sha)))
            return eval(expression, {"__builtins__": {}}, {"github": github})
        self.assertTrue(accepted(migration.LEGACY_BRANCH, migration.LEGACY_SHA))
        self.assertFalse(accepted(migration.DEVELOPMENT_BRANCH, migration.LEGACY_SHA))
        self.assertFalse(accepted(migration.DEVELOPMENT_BRANCH, NEW_SHA))
        self.assertFalse(accepted(migration.LEGACY_BRANCH, NEW_SHA))
        self.assertTrue(accepted("master", NEW_SHA, "schedule"))
        self.assertEqual(wf["concurrency"]["cancel-in-progress"], "false")

    def test_real_pinned_collector_preserves_history_beyond_50_records(self):
        history = self.directory / "history"
        old = [run_record(i, migration.DEVELOPMENT_BRANCH) for i in range(1, 61)]
        self.write_runs(history, old)
        fresh = run_record(90001, migration.LEGACY_BRANCH)
        foreign = run_record(90002, migration.DEVELOPMENT_BRANCH, NEW_SHA)
        # GitHub's API returns the full SHA in head_sha (stored data uses a short SHA).
        fresh["head_sha"] = fresh["head_sha_full"]
        foreign["head_sha"] = foreign["head_sha_full"]
        env = {**self.environment, "FAKE_RUNS": json.dumps([fresh, foreign])}
        command = [sys.executable, str(SCRIPT), "collect", "--collector",
                   str(REFERENCE / ".github/scripts/dashboard_tiers/collect_data.py"),
                   "--repo", "AlexChenIC/cva6", "--history-dir", str(history),
                   "--fetch-count", "20", "--branch", migration.LEGACY_BRANCH,
                   "--expected-sha", migration.LEGACY_SHA]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        stored = {run["id"]: run for run in migration.read_runs(history / "runs_tier2.json")}
        self.assertEqual(len(stored), 61)
        for run in old:
            self.assertEqual(stored[run["id"]], run)
        self.assertEqual(stored[90001]["head_branch"], migration.LEGACY_BRANCH)
        self.assertEqual(stored[90001]["head_sha_full"], migration.LEGACY_SHA)
        self.assertNotIn(90002, stored)
        self.assertTrue(any("branch=jchen%2Fpr3480-legacy-ci-e7-20261009" in " ".join(call)
                            for call in self.calls()))
        before = (history / "runs_tier2.json").read_bytes()
        moved = run_record(90003, migration.LEGACY_BRANCH, NEW_SHA)
        moved["head_sha"] = NEW_SHA
        result = subprocess.run(command, env={**env, "FAKE_RUNS": json.dumps([
            moved])}, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((history / "runs_tier2.json").read_bytes(), before)

    def test_persistence_keeps_records_added_after_build_snapshot(self):
        current = self.directory / "current"
        snapshot = self.directory / "snapshot"
        original = run_record(1, migration.DEVELOPMENT_BRANCH)
        late = run_record(2, "master", NEW_SHA)
        fresh = run_record(3, migration.LEGACY_BRANCH)
        self.write_runs(current, [original, late])
        (current / "unrelated.txt").write_text("keep")
        self.write_runs(snapshot, [original, fresh])
        migration.merge_directory(snapshot, current)
        self.assertEqual({run["id"] for run in migration.read_runs(current / "runs_tier2.json")}, {1, 2, 3})
        self.assertEqual((current / "unrelated.txt").read_text(), "keep")
        with self.assertRaises(ValueError):
            migration.merge_history([original], [run_record(1, migration.LEGACY_BRANCH)])
        (current / "runs_tier2.json").write_text("broken JSON")
        with self.assertRaises(json.JSONDecodeError):
            migration.merge_directory(snapshot, current)
        self.assertEqual((current / "runs_tier2.json").read_text(), "broken JSON")

    def test_real_generators_separate_summary_from_full_history(self):
        history, views, site = [self.directory / name for name in ("history", "views", "site")]
        runs = [run_record(1, migration.LEGACY_BRANCH), run_record(2, migration.DEVELOPMENT_BRANCH),
                run_record(3, migration.DEVELOPMENT_BRANCH, NEW_SHA),
                run_record(4, migration.LEGACY_BRANCH, NEW_SHA), run_record(5, "master", NEW_SHA)]
        short = run_record(6, migration.DEVELOPMENT_BRANCH)
        short.pop("head_sha_full")
        runs.append(short)
        for run in runs[2:]:
            run["jobs"][0]["testcase"] = "NEW_OR_UNVERIFIED_SUITE"
        for dataset in migration.DATASETS:
            self.write_runs(history / dataset, runs)
        original = copy.deepcopy(runs)
        migration.prepare_views(history, views)
        self.assertEqual({run["id"] for run in migration.read_runs(views / "master-candidate-data/runs_tier2.json")}, {1})
        for dataset in migration.DATASETS[:2]:
            self.assertEqual({run["id"] for run in migration.read_runs(views / dataset / "runs_tier2.json")}, {5})
        generators = [ROOT / ".github/scripts/dashboard/generate_dashboard.py",
                      ROOT / ".github/scripts/dashboard_tiers/generate_dashboard.py",
                      REFERENCE / ".github/scripts/dashboard_tiers/generate_dashboard.py"]
        for generator, dataset, output in zip(generators, migration.DATASETS, (site, site / "tier", site / "master_candidate")):
            result = subprocess.run([sys.executable, str(generator), "--data-dir", str(views / dataset),
                                     "--output-dir", str(output), "--repo", "AlexChenIC/cva6"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        migration.label_site(site, history, "AlexChenIC/cva6", NEW_SHA)
        candidate = (site / "master_candidate/index.html").read_text()
        self.assertIn("CVA6 legacy e7 Cook CI Dashboard", candidate)
        self.assertNotIn("NEW_OR_UNVERIFIED_SUITE", candidate)
        self.assertIn(migration.LEGACY_BRANCH, candidate)
        self.assertIn(migration.DEVELOPMENT_BRANCH, candidate)
        self.assertIn("legacy PASS does not validate this SHA", candidate)
        self.assertIn(NEW_SHA, candidate)
        archive = (site / "master_candidate/history.html").read_text()
        self.assertIn(NEW_SHA, archive)
        self.assertIn(migration.DEVELOPMENT_BRANCH, archive)
        for dataset in migration.DATASETS:
            stored = migration.read_runs(history / dataset / "runs_tier2.json")
            self.assertEqual(stored, original)
        scope = json.loads((history / "master-candidate-data/legacy_scope.json").read_text())
        self.assertEqual(scope["run_counts"]["runs_tier2"], {"legacy": 1, "original_branch_e7": 1})

    def test_historical_pass_does_not_claim_migrated_scheduler_validation(self):
        history = self.directory / "history"
        site = self.directory / "site"
        for dataset, relative in zip(migration.DATASETS, ("", "tier", "master_candidate")):
            self.write_runs(history / dataset, [run_record(1, migration.DEVELOPMENT_BRANCH)])
            (site / relative).mkdir(parents=True, exist_ok=True)
            (site / relative / "index.html").write_text("<html><body>historical PASS</body></html>")
        migration.label_site(site, history, "AlexChenIC/cva6", NEW_SHA)
        self.assertIn("No completed legacy-branch run has been collected", (site / "master_candidate/index.html").read_text())

    def test_first_legacy_setup_failure_cannot_borrow_original_branch_pass_matrix(self):
        history, views, site = [self.directory / name for name in ("history", "views", "site")]
        old_pass = run_record(1, migration.DEVELOPMENT_BRANCH)
        failure = run_record(2, migration.LEGACY_BRANCH)
        failure.update(conclusion="failure", jobs=[], total_jobs=0, passed_jobs=0)
        for dataset in migration.DATASETS:
            self.write_runs(history / dataset, [failure, old_pass])
        migration.prepare_views(history, views)
        result = subprocess.run([sys.executable, str(REFERENCE / ".github/scripts/dashboard_tiers/generate_dashboard.py"),
                                 "--data-dir", str(views / "master-candidate-data"), "--output-dir", str(site)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("base-rv32-p", (site / "index.html").read_text())
        self.assertEqual(migration.read_runs(history / "master-candidate-data/runs_tier2.json"), [failure, old_pass])


if __name__ == "__main__":
    unittest.main()
