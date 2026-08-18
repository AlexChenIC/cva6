#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Collect public Thales GitLab pipeline data as a reference."""

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

import yaml


DEFAULT_URL = "https://riscv-ci.pages.thales-invia.fr/dashboard/dashboard_cva6.html"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
PIPELINE_MARKER = '<div class="list-group-item list-group-item-action py-3">'
JOB_MARKER = '<div class="col-12 border-top p-1">'
HISTORY_LIMIT = 20


def clean_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]*>", "", value)
    return " ".join(html.unescape(without_tags).split())


def split_pipeline_cards(page: str) -> list[str]:
    if PIPELINE_MARKER not in page:
        raise ValueError("pipeline entries were not found")
    return page.split(PIPELINE_MARKER)[1:]


def parse_pipeline_summary(card: str, dashboard_url: str) -> dict:
    header = card.split(JOB_MARKER, 1)[0]

    status_match = re.search(
        r'<button class="btn btn-(?:success|danger|warning)[^"]*"[^>]*>'
        r"([^<]+)</button>",
        header,
    )
    commit_match = re.search(
        r"github\.com/openhwgroup/cva6/commit/([0-9a-f]{40})", header
    )
    pipeline_match = re.search(
        r"href=(https://gitlab\.thales-invia\.fr/riscv-ci/cva6/-/pipelines/([0-9]+))",
        header,
    )
    branch_match = re.search(
        r'<span class="badge bg-warning[^>]*>\s*([^<]+)</span>', header
    )
    title_match = re.search(r"<strong>(.*?)<span class=\"badge bg-warning", header)
    timestamp_match = re.search(r"timeDifference_from_now\(([0-9]+)\)", header)
    duration_match = re.search(r"timeDifference_absolute\(([0-9]+)\)", header)
    author_match = re.search(r"Authored by ([^|<]+)", header)

    required = (status_match, commit_match, pipeline_match, branch_match)
    if not all(required):
        raise ValueError("latest pipeline summary is incomplete")

    status_label = clean_text(status_match.group(1)).upper()
    status = {"PASS": "success", "FAIL": "failure"}.get(status_label, "unknown")
    full_sha = commit_match.group(1)
    timestamp = int(timestamp_match.group(1)) if timestamp_match else 0

    return {
        "available": True,
        "source": "thales-gitlab",
        "backend": "VCS/UVM",
        "scope": "latest public pipeline",
        "status": status,
        "status_label": status_label,
        "title": clean_text(title_match.group(1)) if title_match else "",
        "branch": clean_text(branch_match.group(1)),
        "head_sha": full_sha[:8],
        "head_sha_full": full_sha,
        "commit_url": f"https://github.com/openhwgroup/cva6/commit/{full_sha}",
        "pipeline_id": int(pipeline_match.group(2)),
        "dashboard_url": dashboard_url,
        "author": clean_text(author_match.group(1)) if author_match else "",
        "created_at": (
            datetime.fromtimestamp(timestamp, timezone.utc).isoformat()
            if timestamp
            else ""
        ),
        "duration_seconds": int(duration_match.group(1)) if duration_match else 0,
    }


def parse_testlist_jobs(card: str) -> list[dict]:
    jobs = []
    for block in card.split(JOB_MARKER)[1:]:
        name_match = re.search(
            r"<strong>\s*Testlist RTL run - (.*?) - (.*?)</strong>", block
        )
        if not name_match:
            continue

        config = clean_text(name_match.group(1))
        testcase = clean_text(name_match.group(2))

        status_match = re.search(
            r'<button class="btn btn-(?:success|danger|warning)[^"]*"[^>]*>'
            r"\s*(?:<small>)?([^<]+)(?:</small>)?\s*</button>",
            block,
        )
        if not status_match:
            continue

        status_label = clean_text(status_match.group(1)).upper()
        status = {"PASS": "success", "FAIL": "failure"}.get(
            status_label, "unknown"
        )
        duration_match = re.search(r"timeDifference_absolute\(([0-9]+)\)", block)
        jobs.append(
            {
                "config": config,
                "testcase": testcase,
                "conclusion": status,
                "status_label": status_label,
                "duration_seconds": (
                    int(duration_match.group(1)) if duration_match else 0
                ),
            }
        )
    return jobs


def add_testlist_job_summary(summary: dict, card: str) -> dict:
    jobs = parse_testlist_jobs(card)
    passed = sum(job["conclusion"] == "success" for job in jobs)
    failed = sum(job["conclusion"] == "failure" for job in jobs)
    summary["jobs"] = jobs
    summary["passed_jobs"] = passed
    summary["failed_jobs"] = failed
    summary["total_jobs"] = len(jobs)
    summary["pass_rate"] = round(passed / len(jobs) * 100, 1) if jobs else 0
    return summary


def parse_latest_pipeline(page: str, dashboard_url: str = DEFAULT_URL) -> dict:
    return parse_pipeline_summary(split_pipeline_cards(page)[0], dashboard_url)


def parse_matrix_definition(
    source: str,
    branch: str,
    head_sha: str,
) -> dict:
    data = yaml.safe_load(source)
    if not isinstance(data, dict):
        raise ValueError("GitLab CI configuration is not a mapping")

    variables = data.get("variables", {})
    simulator = variables.get("MY_SIMULATOR", "") if isinstance(variables, dict) else ""
    if not isinstance(simulator, str) or not simulator:
        raise ValueError("MY_SIMULATOR is missing from GitLab CI configuration")

    target = data.get(".testlist_matrix_target", {})
    if not isinstance(target, dict):
        raise ValueError("testlist matrix definition is missing")
    parallel = target.get("parallel", {})
    matrix = parallel.get("matrix", {}) if isinstance(parallel, dict) else {}
    if not isinstance(matrix, list):
        raise ValueError("testlist matrix is not a list")

    configs = []
    testlists = []
    jobs = []
    seen = set()
    for entry in matrix:
        if not isinstance(entry, dict):
            raise ValueError("testlist matrix entry is not a mapping")
        config = entry.get("MY_TARGET")
        suites = entry.get("MY_TESTLIST")
        if not isinstance(config, str) or not isinstance(suites, list):
            raise ValueError("testlist matrix entry is incomplete")
        if config not in configs:
            configs.append(config)
        for testcase in suites:
            if not isinstance(testcase, str):
                raise ValueError("testlist matrix contains a non-string testlist")
            pair = (config, testcase)
            if pair in seen:
                raise ValueError(
                    f"duplicate testlist matrix entry: {config} / {testcase}"
                )
            seen.add(pair)
            if testcase not in testlists:
                testlists.append(testcase)
            jobs.append(
                {
                    "config": config,
                    "testcase": testcase,
                    "conclusion": "configured",
                    "status_label": "CONFIGURED",
                }
            )

    if not jobs:
        raise ValueError("testlist matrix contains no jobs")

    return {
        "branch": branch,
        "head_sha": head_sha[:8],
        "head_sha_full": head_sha,
        "source_url": (
            "https://github.com/openhwgroup/cva6/blob/"
            f"{head_sha}/.gitlab-ci.yml"
        ),
        "backend": f"{simulator.upper()}/UVM",
        "configs": configs,
        "testlists": testlists,
        "jobs": jobs,
        "total_configs": len(configs),
        "total_testlists": len(testlists),
        "total_jobs": len(jobs),
    }


def parse_public_dashboard(
    page: str,
    dashboard_url: str = DEFAULT_URL,
    matrix_definition: dict | None = None,
) -> dict:
    cards = split_pipeline_cards(page)
    latest = parse_pipeline_summary(cards[0], dashboard_url)
    relevant = []
    for card in cards:
        try:
            summary = add_testlist_job_summary(
                parse_pipeline_summary(card, dashboard_url), card
            )
        except ValueError:
            continue
        if summary["jobs"]:
            relevant.append(summary)
        if len(relevant) >= HISTORY_LIMIT:
            break

    definition = matrix_definition or {}
    expected_sha = definition.get("head_sha_full", "")
    latest["matrix_definition"] = definition
    latest["latest_matrix_snapshot"] = relevant[0] if relevant else {}
    latest["matrix_snapshot"] = next(
        (
            item
            for item in relevant
            if expected_sha and item.get("head_sha_full") == expected_sha
        ),
        {},
    )
    latest["history"] = relevant
    return latest


def fetch_page(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenHW-CVA6-tier-dashboard/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("dashboard response exceeded 32 MiB")
    return payload.decode("utf-8", errors="replace")


def unavailable_reference(url: str, error: Exception) -> dict:
    return {
        "available": False,
        "source": "thales-gitlab",
        "backend": "VCS/UVM",
        "scope": "latest public pipeline",
        "status": "unknown",
        "status_label": "UNAVAILABLE",
        "stale": False,
        "dashboard_url": url,
        "matrix_definition": {},
        "matrix_snapshot": {},
        "latest_matrix_snapshot": {},
        "history": [],
        "error": str(error),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-html", type=Path)
    parser.add_argument("--matrix-file", type=Path)
    parser.add_argument("--matrix-branch", default="master_candidate")
    parser.add_argument("--matrix-sha", default="")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    try:
        page = (
            args.input_html.read_text(encoding="utf-8")
            if args.input_html
            else fetch_page(args.url, args.timeout)
        )
        matrix_definition = {}
        if args.matrix_file:
            if not args.matrix_sha:
                raise ValueError("--matrix-sha is required with --matrix-file")
            matrix_definition = parse_matrix_definition(
                args.matrix_file.read_text(encoding="utf-8"),
                args.matrix_branch,
                args.matrix_sha,
            )
        reference = parse_public_dashboard(
            page,
            args.url,
            matrix_definition=matrix_definition,
        )
        reference["stale"] = False
        reference["collected_at"] = datetime.now(timezone.utc).isoformat()
    except (
        OSError,
        OverflowError,
        UnicodeError,
        ValueError,
        urllib.error.URLError,
    ) as error:
        attempted_at = datetime.now(timezone.utc).isoformat()
        try:
            previous = json.loads(args.output.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None

        if isinstance(previous, dict):
            reference = previous
            reference["stale"] = True
            reference["last_error"] = str(error)
            reference["attempted_at"] = attempted_at
            print(f"NOTICE: keeping previous Thales reference: {error}")
        else:
            reference = unavailable_reference(args.url, error)
            reference["collected_at"] = attempted_at

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reference, indent=2), encoding="utf-8")
    print(f"Thales reference: {reference.get('status_label', 'UNKNOWN')}")


if __name__ == "__main__":
    main()
