#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Collect completed Tier 1 and Tier 2 runs from the GitHub API."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

from parser import parse_job_name


WORKFLOWS = {
    "tier1": "openhw-cva6-ci-tier1.yml",
    "tier2": "openhw-cva6-ci-tier2.yml",
}
MAX_HISTORY = 50


def gh_api(endpoint: str, repo: str) -> dict:
    url = f"/repos/{repo}/actions/{endpoint}"
    result = subprocess.run(
        ["gh", "api", url],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {url} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def build_runs_endpoint(workflow_file: str, count: int, branch: str = "") -> str:
    params: dict[str, str | int] = {
        "status": "completed",
        "per_page": count,
    }
    if branch:
        params["branch"] = branch
    return f"workflows/{workflow_file}/runs?{urlencode(params)}"


def fetch_runs(repo: str, workflow_file: str, count: int, branch: str = "") -> list[dict]:
    data = gh_api(build_runs_endpoint(workflow_file, count, branch), repo)
    return data.get("workflow_runs", [])[:count]


def fetch_jobs(repo: str, run_id: int) -> list[dict]:
    data = gh_api(f"runs/{run_id}/jobs?per_page=100", repo)
    return data.get("jobs", [])


def duration_seconds(started_at: str, completed_at: str) -> int:
    if not started_at or not completed_at:
        return 0
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    return max(0, int((end - start).total_seconds()))


def process_run(repo: str, run: dict, workflow_name: str) -> dict:
    jobs = []
    for job in fetch_jobs(repo, run["id"]):
        parsed = parse_job_name(job["name"], workflow_name)
        if parsed is None:
            continue
        conclusion = job.get("conclusion") or "unknown"
        jobs.append(
            {
                **parsed,
                "name": job["name"],
                "conclusion": conclusion,
                "started_at": job.get("started_at", ""),
                "completed_at": job.get("completed_at", ""),
                "duration_seconds": duration_seconds(
                    job.get("started_at", ""), job.get("completed_at", "")
                ),
                "html_url": job.get("html_url", ""),
            }
        )

    passed_jobs = sum(job["conclusion"] == "success" for job in jobs)
    failed_jobs = sum(
        job["conclusion"] in {"failure", "timed_out", "action_required"}
        for job in jobs
    )
    total_jobs = len(jobs)

    return {
        "id": run["id"],
        "source": "github-actions",
        "simulator": "verilator-testharness",
        "run_number": run.get("run_number", 0),
        "status": run.get("status", ""),
        "conclusion": run.get("conclusion") or "unknown",
        "html_url": run.get("html_url", ""),
        "head_branch": run.get("head_branch", ""),
        "base_branches": base_branches(run),
        "head_sha": run.get("head_sha", "")[:8],
        "head_sha_full": run.get("head_sha", ""),
        "event": run.get("event", ""),
        "created_at": run.get("created_at", ""),
        "updated_at": run.get("updated_at", ""),
        "run_started_at": run.get("run_started_at", run.get("created_at", "")),
        "duration_seconds": duration_seconds(
            run.get("run_started_at", run.get("created_at", "")),
            run.get("updated_at", ""),
        ),
        "total_jobs": total_jobs,
        "passed_jobs": passed_jobs,
        "failed_jobs": failed_jobs,
        "skipped_jobs": total_jobs - passed_jobs - failed_jobs,
        "jobs": jobs,
    }


def load_existing(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def base_branches(run: dict) -> list[str]:
    stored = run.get("base_branches", [])
    if isinstance(stored, list) and stored:
        return sorted({branch for branch in stored if isinstance(branch, str)})

    branches = set()
    for pull_request in run.get("pull_requests", []):
        branch = pull_request.get("base", {}).get("ref", "")
        if branch:
            branches.add(branch)
    return sorted(branches)


def filter_runs(
    runs: list[dict], branch: str = "", base_branch: str = ""
) -> list[dict]:
    if branch:
        return [run for run in runs if run.get("head_branch") == branch]
    if not base_branch:
        return runs
    return [
        run
        for run in runs
        if run.get("head_branch") == base_branch
        or base_branch in base_branches(run)
    ]


def merge_runs(existing: list[dict], new_runs: list[dict]) -> list[dict]:
    merged = {run["id"]: run for run in existing}
    merged.update({run["id"]: run for run in new_runs})
    return sorted(
        merged.values(), key=lambda run: run.get("created_at", ""), reverse=True
    )[:MAX_HISTORY]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "openhwgroup/cva6"),
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--fetch-count", type=int, default=10)
    parser.add_argument("--branch", default="")
    parser.add_argument("--base-branch", default="master_candidate")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        for name, workflow_file in WORKFLOWS.items():
            json_path = data_dir / f"runs_{name}.json"
            existing = filter_runs(
                load_existing(json_path), args.branch, args.base_branch
            )
            existing_ids = {run["id"] for run in existing}
            api_count = (
                args.fetch_count
                if args.branch or not args.base_branch
                else min(100, max(args.fetch_count * 5, args.fetch_count))
            )
            fetched = fetch_runs(args.repo, workflow_file, api_count, args.branch)
            fetched = filter_runs(
                fetched, args.branch, args.base_branch
            )[: args.fetch_count]
            new_runs = [
                process_run(args.repo, run, name)
                for run in fetched
                if run["id"] not in existing_ids
            ]
            merged = merge_runs(existing, new_runs)
            json_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
            print(f"{name}: {len(new_runs)} new, {len(merged)} stored")
    except (json.JSONDecodeError, KeyError, OSError, RuntimeError) as error:
        raise SystemExit(f"ERROR: {error}") from error

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo": args.repo,
        "branch": args.branch,
        "base_branch": args.base_branch,
        "workflows": list(WORKFLOWS),
    }
    (data_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
