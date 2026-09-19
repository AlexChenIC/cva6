#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Dispatch same-repository candidate Tier 2 once per UTC day and source SHA."""

import argparse
from datetime import datetime, timezone
import json
import re
import subprocess
from urllib.parse import quote, urlencode

WORKFLOW = "openhw-cva6-ci-tier2.yml"


def gh(repo: str, endpoint: str, body: dict | None = None):
    command = ["gh", "api", f"repos/{repo}/{endpoint}"]
    if body is not None:
        command.extend(["--method", "POST", "--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"GitHub request failed: {result.stderr.strip()}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def validate_ref(ref: str):
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", ref)
        or any(x in ref for x in ("..", "//", "/.", ".lock"))
        or ref.endswith(("/", "."))
    ):
        raise ValueError("Use a valid branch name, not a SHA, tag or expression")


def existing_today(runs: list[dict], ref: str, sha: str, day: str) -> bool:
    return any(
        run.get("event") == "workflow_dispatch"
        and run.get("head_branch") == ref
        and run.get("head_sha") == sha
        and run.get("created_at", "")[:10] == day
        for run in runs
    )


def dispatch(repo: str, ref: str, *, dry_run: bool = True, api=gh, now=None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository")
    validate_ref(ref)
    branch_endpoint = f"git/ref/heads/{quote(ref, safe='/')}"
    sha = api(repo, branch_endpoint)["object"]["sha"]
    # Do not accidentally schedule the legacy flow on master or an old candidate.
    for path in (
        f".github/workflows/{WORKFLOW}",
        ".github/scripts/cook_tier.py",
        "flows/recipes/testharness_run_testlist.py",
    ):
        api(repo, f"contents/{path}?{urlencode({'ref': sha})}")
    day = (
        (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()
    )
    runs = api(
        repo,
        f"actions/workflows/{WORKFLOW}/runs?{urlencode({'branch': ref, 'event': 'workflow_dispatch', 'per_page': 100})}",
    ).get("workflow_runs", [])
    result = {
        "repository": repo,
        "branch": ref,
        "source_sha": sha,
        "utc_day": day,
        "workflow": WORKFLOW,
        "dry_run": dry_run,
    }
    if existing_today(runs, ref, sha, day):
        return {**result, "action": "already-dispatched"}
    if len(runs) == 100 and all(r.get("created_at", "")[:10] >= day for r in runs):
        raise RuntimeError(
            "Run listing is truncated within today; refusing an ambiguous duplicate dispatch"
        )
    if dry_run:
        return {**result, "action": "would-dispatch"}
    if api(repo, branch_endpoint)["object"]["sha"] != sha:
        raise RuntimeError(
            "Branch moved during preflight; retry after checking the new revision"
        )
    api(repo, f"actions/workflows/{WORKFLOW}/dispatches", {"ref": ref})
    return {**result, "action": "dispatched"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ref", default="master_candidate")
    parser.add_argument(
        "--execute", action="store_true", help="Actually dispatch; default is read-only"
    )
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                dispatch(args.repo, args.ref, dry_run=not args.execute), indent=2
            )
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        subprocess.TimeoutExpired,
    ) as error:
        raise SystemExit(f"ERROR: {error}") from error


if __name__ == "__main__":
    main()
