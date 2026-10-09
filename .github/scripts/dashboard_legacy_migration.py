#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Preserve dashboard history while moving the old Cook CI to frozen e7.

Collectors run in empty scratch directories so their branch filters and
50-record retention cannot delete restored history. Generators consume views;
only the complete history directories are published and persisted.
"""

import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


LEGACY_BRANCH = "jchen/pr3480-legacy-ci-e7-20261009"
LEGACY_SHA = "e7c272c93dc0db08d030f1ebe7412af8d78dae6b"
DEVELOPMENT_BRANCH = "jchen/master-candidate-openhw-tier-ci"
DASHBOARD_SOURCE_SHA = "6464894fa0709630c09ea0414691358aec4fa9e7"
DATASETS = ("legacy-data", "tier-data", "master-candidate-data")


def read_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    runs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(runs, list) or any(
        not isinstance(run, dict) or not isinstance(run.get("id"), int)
        for run in runs
    ):
        raise ValueError(f"Invalid run history: {path}")
    if len({run["id"] for run in runs}) != len(runs):
        raise ValueError(f"Duplicate run IDs: {path}")
    return runs


def merge_history(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Retain every old record verbatim, including its original branch/SHA."""
    merged = {run["id"]: run for run in existing}
    for run in incoming:
        previous = merged.get(run["id"])
        if previous is not None:
            old_sha = previous.get("head_sha_full") or previous.get("head_sha", "")
            new_sha = run.get("head_sha_full") or run.get("head_sha", "")
            if previous.get("head_branch") != run.get("head_branch") or (
                old_sha and new_sha
                and not (old_sha.startswith(new_sha) or new_sha.startswith(old_sha))
            ):
                raise ValueError(f"Run {run['id']} changed source identity")
            continue
        merged[run["id"]] = run
    return sorted(merged.values(), key=lambda run: run.get("created_at", ""), reverse=True)


def merge_directory(scratch: Path, history: Path, branch="", expected_sha="") -> None:
    history.mkdir(parents=True, exist_ok=True)
    # Validate every update before changing any restored history file.
    updates = {}
    for path in scratch.glob("runs_*.json"):
        incoming = read_runs(path)
        if expected_sha and any(
            run.get("head_branch") != branch
            or run.get("head_sha_full") != expected_sha
            for run in incoming
        ):
            raise ValueError("Collector returned a run outside the frozen legacy ref/SHA")
        target = history / path.name
        updates[target] = merge_history(read_runs(target), incoming)
    for path, runs in updates.items():
        path.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
    for path in scratch.iterdir():
        if path.is_file() and not path.name.startswith("runs_"):
            shutil.copyfile(path, history / path.name)


def collect(args) -> None:
    history = Path(args.history_dir)
    with tempfile.TemporaryDirectory(prefix="cva6-dashboard-collect-") as directory:
        scratch = Path(directory)
        command = [sys.executable, args.collector, "--repo", args.repo,
                   "--data-dir", str(scratch), "--fetch-count", str(args.fetch_count)]
        if args.branch:
            command.extend(["--branch", args.branch, "--base-branch", args.base_branch])
        subprocess.run(command, check=True)
        merge_directory(scratch, history, args.branch, args.expected_sha)


def is_legacy_evidence(run: dict) -> bool:
    # An eight-character stored SHA is insufficient to establish frozen e7.
    return (run.get("head_branch") in {LEGACY_BRANCH, DEVELOPMENT_BRANCH}
            and run.get("head_sha_full") == LEGACY_SHA)


def prepare_views(history_root: Path, output_root: Path) -> None:
    for dataset in DATASETS:
        source = history_root / dataset
        target = output_root / dataset
        shutil.copytree(source, target, dirs_exist_ok=True)
        for path in target.glob("runs_*.json"):
            runs = read_runs(path)
            if dataset == "master-candidate-data":
                runs = [run for run in runs if is_legacy_evidence(run)]
                # Once this workflow has legacy evidence, do not borrow an old
                # source-branch PASS matrix if the latest legacy setup failed.
                legacy_runs = [run for run in runs if run.get("head_branch") == LEGACY_BRANCH]
                runs = legacy_runs or runs
            else:
                runs = [run for run in runs if run.get("head_branch")
                        not in {LEGACY_BRANCH, DEVELOPMENT_BRANCH}]
            path.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")


def history_page(data_dir: Path) -> str:
    rows = []
    for path in sorted(data_dir.glob("runs_*.json")):
        for run in read_runs(path):
            values = [path.stem, str(run["id"]), run.get("head_branch", ""),
                      run.get("head_sha_full") or run.get("head_sha", ""),
                      run.get("event", ""), run.get("conclusion", ""),
                      run.get("created_at", "")]
            cells = "".join(f"<td>{escape(str(value))}</td>" for value in values)
            link = escape(run.get("html_url", ""), quote=True)
            rows.append(f'<tr>{cells}<td><a href="{link}">Actual run</a></td></tr>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<title>CVA6 preserved run history</title><body><h1>Preserved run history</h1>'
            '<p>This archive contains multiple branches and revisions. Each result applies '
            'only to its recorded branch/SHA. It is not a Stage 1 acceptance summary. '
            'Short stored SHAs are shown as stored, without inferring a full revision.</p>'
            '<p><a href="./">Dashboard</a></p><table border="1"><thead><tr>'
            '<th>Workflow</th><th>Run ID</th><th>Actual branch</th><th>Stored SHA</th>'
            '<th>Event</th><th>Conclusion</th><th>Created</th><th>Evidence</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></body></html>')


def label_site(site: Path, history_root: Path, repo: str, development_sha: str) -> None:
    if len(development_sha) != 40 or any(c not in "0123456789abcdef" for c in development_sha):
        raise ValueError("Development SHA must be a full Git object ID")
    candidate = history_root / "master-candidate-data"
    counts = {}
    for path in sorted(candidate.glob("runs_*.json")):
        runs = read_runs(path)
        counts[path.stem] = {
            "legacy": sum(is_legacy_evidence(run) and run.get("head_branch") == LEGACY_BRANCH
                          for run in runs),
            "original_branch_e7": sum(is_legacy_evidence(run)
                                      and run.get("head_branch") == DEVELOPMENT_BRANCH
                                      for run in runs),
        }
    legacy_count = sum(count["legacy"] for count in counts.values())
    readiness = (f"{legacy_count} completed legacy-branch run(s) retained; inspect their conclusions."
                 if legacy_count else "No completed legacy-branch run has been collected. "
                 "Any e7 result below is historical evidence on its original branch; "
                 "the migrated scheduler has not been validated by this page.")
    scope = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "legacy_branch": LEGACY_BRANCH, "frozen_source_sha": LEGACY_SHA,
        "dashboard_source_sha": DASHBOARD_SOURCE_SHA,
        "publisher_sha": os.environ.get("GITHUB_SHA", "uncommitted-local-preview"),
        "development_branch": DEVELOPMENT_BRANCH, "development_sha_observed": development_sha,
        "development_validation": "not_assessed_by_legacy_dashboard", "run_counts": counts,
    }
    (candidate / "legacy_scope.json").write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8")
    development = (f'<a href="https://github.com/{escape(repo)}/tree/{escape(DEVELOPMENT_BRANCH)}">'
                   '#3480 development branch</a> at '
                   f'<code>{development_sha}</code>. New Cook Stage 1 is in development; '
                   'legacy PASS does not validate this SHA. No Stage 1 acceptance is asserted here.')
    for relative, dataset in zip(("", "tier", "master_candidate"), DATASETS):
        directory = site / relative
        page_path = directory / "index.html"
        page = page_path.read_text(encoding="utf-8")
        if relative == "master_candidate":
            page = page.replace("CVA6 master_candidate Tier CI Dashboard", "CVA6 legacy e7 Cook CI Dashboard")
            page = page.replace("CVA6 master_candidate Tier CI", "CVA6 legacy e7 Cook CI")
            page = page.replace("Pull request sanity", "Frozen e7 historical sanity")
            page = page.replace("master_candidate regression", "Frozen e7 regression")
            text = (f'<strong>Legacy Cook CI — frozen e7</strong><p>Scheduled branch: '
                    f'<a href="https://github.com/{escape(repo)}/tree/{escape(LEGACY_BRANCH)}">'
                    f'{escape(LEGACY_BRANCH)}</a><br>Frozen source revision: '
                    f'<a href="https://github.com/{escape(repo)}/commit/{LEGACY_SHA}"><code>{LEGACY_SHA}</code></a>'
                    f'</p><p>{readiness} Cards and matrix captions identify the actual tested branch/SHA.</p>'
                    '<p>The Thales panel is an independent reference at its own branch/SHA.</p>')
        else:
            text = ('<strong>Other fork branches — separate CI history</strong><p>'
                    '#3480 source and the frozen Cook legacy branch are excluded from '
                    'these summary cards. Each displayed result keeps its actual branch/SHA. '
                    f'<a href="{"../" if relative else ""}master_candidate/">Legacy Cook dashboard</a>.</p>')
        banner = ('<aside id="ci-migration-scope" style="padding:18px;margin:18px;'
                  'border:2px solid #af7400;background:#fff8dd;color:#222">'
                  + text + f'<p>{development}</p><p><a href="history.html">Complete preserved history</a>'
                  '</p></aside>')
        start = page.index("<body")
        body_end = page.index(">", start) + 1
        page_path.write_text(page[:body_end] + banner + page[body_end:], encoding="utf-8")
        (directory / "history.html").write_text(history_page(history_root / dataset), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser("collect")
    collector.add_argument("--collector", required=True)
    collector.add_argument("--history-dir", required=True)
    collector.add_argument("--repo", required=True)
    collector.add_argument("--fetch-count", type=int, required=True)
    collector.add_argument("--branch", default="")
    collector.add_argument("--base-branch", default="master_candidate")
    collector.add_argument("--expected-sha", default="")
    merger = commands.add_parser("merge")
    merger.add_argument("--incoming-dir", required=True)
    merger.add_argument("--history-dir", required=True)
    views = commands.add_parser("views")
    views.add_argument("--history-root", required=True)
    views.add_argument("--output-root", required=True)
    label = commands.add_parser("label")
    label.add_argument("--site-dir", required=True)
    label.add_argument("--history-root", required=True)
    label.add_argument("--repo", required=True)
    label.add_argument("--development-sha", required=True)
    args = parser.parse_args()
    if args.command == "collect":
        collect(args)
    elif args.command == "merge":
        merge_directory(Path(args.incoming_dir), Path(args.history_dir))
    elif args.command == "views":
        prepare_views(Path(args.history_root), Path(args.output_root))
    else:
        label_site(Path(args.site_dir), Path(args.history_root), args.repo, args.development_sha)


if __name__ == "__main__":
    main()
