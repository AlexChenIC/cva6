#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read candidate Actions metadata and bounded JSON evidence, never execute artifacts."""

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlencode
import zipfile

from parser import parse_job_name

WORKFLOWS = {"tier1": "openhw-cva6-ci-tier1.yml", "tier2": "openhw-cva6-ci-tier2.yml"}
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_JSON = 1024 * 1024


def gh_api(repo, endpoint):
    result = subprocess.run(
        ["gh", "api", f"repos/{repo}/actions/{endpoint}"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def paged(repo, endpoint, key):
    items = []
    for page in range(1, 11):
        separator = "&" if "?" in endpoint else "?"
        batch = gh_api(repo, f"{endpoint}{separator}per_page=100&page={page}").get(
            key, []
        )
        items.extend(batch)
        if len(batch) < 100:
            return items
    raise ValueError("GitHub pagination exceeds the supported bounded collection")


def artifact_bytes(repo, artifact):
    if not 0 < artifact.get("size_in_bytes", 0) <= MAX_ARCHIVE:
        raise ValueError("Artifact size outside the 32 MiB collection budget")
    with tempfile.TemporaryFile() as output:
        subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/artifacts/{int(artifact['id'])}/zip"],
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=90,
            check=True,
        )
        output.seek(0)
        data = output.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("Downloaded artifact exceeds budget")
    return data


def parse_evidence(payload, *, repo, run, target, suite):
    if len(payload) > MAX_ARCHIVE:
        raise ValueError("Oversized archive")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        entries = [
            entry
            for entry in archive.infolist()
            if entry.filename in {"ci-results/evidence.json", "evidence.json"}
        ]
        if len(entries) != 1 or entries[0].file_size > MAX_JSON:
            raise ValueError("Artifact needs exactly one bounded evidence.json")
        data = json.loads(archive.read(entries[0]))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unknown evidence schema")
    for key, expected in {
        "repository": repo,
        "run_id": str(run["id"]),
        "run_attempt": str(run.get("run_attempt", 1)),
        "target": target,
        "testcase": suite,
        "simulator": "verilator",
        "reference_model": "spike-offline",
    }.items():
        if data.get(key) != expected:
            raise ValueError(f"Evidence identity mismatch: {key}")
    if not isinstance(data.get("source_revision"), str) or not re.fullmatch(
        r"[0-9a-f]{40}", data["source_revision"]
    ):
        raise ValueError("Evidence has no full source revision")
    # PR runs may test a merge commit; event_head_sha preserves the API head identity.
    if run.get("head_sha") not in (data["source_revision"], data.get("event_head_sha")):
        raise ValueError("Evidence belongs to another source revision")
    if data.get("status") == "PASS":
        summary = data.get("results", {})
        if not isinstance(summary, dict):
            raise ValueError("Results must be an object")
        cases = summary.get("cases", [])
        if (
            not isinstance(cases, list)
            or not cases
            or not all(isinstance(c, dict) and c.get("status") == "PASS" for c in cases)
            or any(
                type(summary.get(k)) is not int for k in ("total", "passed", "failed")
            )
            or summary.get("total") != len(cases)
            or summary.get("passed") != len(cases)
            or summary.get("failed") != 0
            or summary.get("status") != "PASS"
            or summary.get("target") != target
            or summary.get("iss_enabled") is not True
        ):
            raise ValueError("Inconsistent successful testlist evidence")
        commands = data.get("commands", [])
        if (
            not isinstance(commands, list)
            or len(commands) != 3
            or any(
                not isinstance(c, dict)
                or type(c.get("exit_code")) is not int
                or c.get("exit_code") != 0
                or c.get("timed_out") is not False
                for c in commands
            )
        ):
            raise ValueError("Successful evidence needs three completed Cook commands")
    elif data.get("status") != "FAIL":
        raise ValueError("Unknown evidence status")
    environment = data.get("environment", {})
    if not isinstance(environment, dict):
        raise ValueError("Environment must be an object")
    for key in ("toolchains", "simulation_tools"):
        tools = environment.get(key, {})
        if not isinstance(tools, dict) or any(
            not isinstance(v, dict) for v in tools.values()
        ):
            raise ValueError(f"Invalid environment {key}")
    if not isinstance(environment.get("required_toolchain", ""), str):
        raise ValueError("Invalid required toolchain")
    return data


def same_collection_scope(path, repo, branch, base_branch):
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(previous, dict) and all(
        previous.get(key) == value
        for key, value in {
            "repo": repo,
            "branch": branch,
            "base_branch": base_branch,
        }.items()
    )


def belongs(run, branch, base):
    if branch:
        return run.get("head_branch") == branch
    return (
        run.get("head_branch") == base
        or any(
            pr.get("base", {}).get("ref") == base for pr in run.get("pull_requests", [])
        )
        or base in run.get("base_branches", [])
    )


def duration(start, end):
    try:
        return max(
            0,
            int(
                (
                    datetime.fromisoformat(end.replace("Z", "+00:00"))
                    - datetime.fromisoformat(start.replace("Z", "+00:00"))
                ).total_seconds()
            ),
        )
    except (TypeError, ValueError, AttributeError):
        return 0


def process_run(repo, run, tier, evidence=False):
    jobs = []
    for job in paged(
        repo, f"runs/{run['id']}/attempts/{run.get('run_attempt', 1)}/jobs", "jobs"
    ):
        parsed = parse_job_name(job.get("name", ""), tier)
        if parsed:
            jobs.append(
                {
                    **parsed,
                    "name": job["name"],
                    "conclusion": job.get("conclusion") or "unknown",
                    "duration_seconds": duration(
                        job.get("started_at"), job.get("completed_at")
                    ),
                    "html_url": f"https://github.com/{repo}/actions/runs/{run['id']}/job/{job['id']}",
                }
            )
    passed = sum(j["conclusion"] == "success" for j in jobs)
    failed = sum(
        j["conclusion"] in {"failure", "timed_out", "action_required"} for j in jobs
    )
    item = {
        **{
            k: run.get(k, "")
            for k in [
                "id",
                "run_number",
                "status",
                "conclusion",
                "head_branch",
                "event",
                "created_at",
                "updated_at",
            ]
        },
        "run_attempt": run.get("run_attempt", 1),
        "head_sha_full": run.get("head_sha", ""),
        "head_sha": run.get("head_sha", "")[:8],
        "jobs": jobs,
        "base_branches": [
            pr.get("base", {}).get("ref") for pr in run.get("pull_requests", [])
        ],
        "html_url": f"https://github.com/{repo}/actions/runs/{run['id']}",
        "duration_seconds": duration(
            run.get("run_started_at", run.get("created_at")), run.get("updated_at")
        ),
        "passed_jobs": passed,
        "failed_jobs": failed,
        "total_jobs": len(jobs),
        "skipped_jobs": len(jobs) - passed - failed,
        "environment": {"available": False},
        "evidence_errors": [],
    }
    if evidence:
        artifacts = paged(repo, f"runs/{run['id']}/artifacts", "artifacts")
        for job in jobs:
            name = f"{tier}-{job['arch']}-{job['config']}-{job['testcase']}"
            matches = [
                a for a in artifacts if a.get("name") == name and not a.get("expired")
            ]
            if not matches:
                item["evidence_errors"].append(f"{name}: artifact missing or expired")
                continue
            try:
                data = parse_evidence(
                    artifact_bytes(repo, max(matches, key=lambda a: a["id"])),
                    repo=repo,
                    run=run,
                    target=job["config"],
                    suite=job["testcase"],
                )
                job["evidence"] = {
                    "status": data["status"],
                    "source_revision": data["source_revision"],
                    "results": data.get("results", {}),
                }
                if data["status"] == "FAIL" and job["conclusion"] == "success":
                    item["evidence_errors"].append(
                        f"{name}: artifact failure conflicts with successful GitHub job"
                    )
                env = data.get("environment", {})
                tools = env.get("simulation_tools", {})
                item["environment"] = {
                    "available": bool(env),
                    "artifact_name": name,
                    "source_revision": data["source_revision"],
                    "gcc_version": env.get("toolchains", {})
                    .get(env.get("required_toolchain"), {})
                    .get("version", ""),
                    "spike_version": tools.get("spike", {}).get("version", ""),
                    "verilator_version": tools.get("verilator", {}).get("version", ""),
                }
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                zipfile.BadZipFile,
                subprocess.SubprocessError,
            ) as error:
                item["evidence_errors"].append(f"{name}: {error}")
        revisions = {j["evidence"]["source_revision"] for j in jobs if "evidence" in j}
        item["tested_source_sha"] = next(iter(revisions)) if len(revisions) == 1 else ""
        item["evidence_complete"] = (
            bool(jobs)
            and all("evidence" in j for j in jobs)
            and not item["evidence_errors"]
        )
    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--branch", default="")
    parser.add_argument("--base-branch", default="master_candidate")
    parser.add_argument("--fetch-count", type=int, default=20)
    args = parser.parse_args()
    if (
        not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo)
        or not 1 <= args.fetch_count <= 50
    ):
        parser.error("Invalid repository or fetch count (1..50)")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    retain_previous = same_collection_scope(
        args.data_dir / "metadata.json", args.repo, args.branch, args.base_branch
    )
    collected = datetime.now(timezone.utc).isoformat()
    errors = []
    for tier, workflow in WORKFLOWS.items():
        output = args.data_dir / f"runs_{tier}.json"
        try:
            selected = []
            for page in range(1, 6):
                query = {"status": "completed", "per_page": 100, "page": page}
                if args.branch:
                    query["branch"] = args.branch
                batch = gh_api(
                    args.repo, f"workflows/{workflow}/runs?{urlencode(query)}"
                ).get("workflow_runs", [])
                selected.extend(
                    r for r in batch if belongs(r, args.branch, args.base_branch)
                )
                if len(selected) >= args.fetch_count or len(batch) < 100:
                    break
            # Re-read attempts and jobs even for an existing run id: reruns change outcomes.
            runs = [
                process_run(args.repo, r, tier, evidence=i == 0)
                for i, r in enumerate(selected[: args.fetch_count])
            ]
            output.write_text(json.dumps(runs, indent=2) + "\n")
        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            subprocess.SubprocessError,
        ) as error:
            errors.append(f"{tier}: {error}")
            if not output.exists() or not retain_previous:
                output.write_text("[]\n")
    (args.data_dir / "metadata.json").write_text(
        json.dumps(
            {
                "collected_at": collected,
                "repo": args.repo,
                "branch": args.branch,
                "base_branch": args.base_branch,
                "errors": errors,
                "collection_mode": "bounded latest 20 completed runs; not real time",
            },
            indent=2,
        )
    )
    for error in errors:
        print(f"WARNING: {error}")


if __name__ == "__main__":
    main()
