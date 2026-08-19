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

DEFAULT_URL = "https://riscv-ci.pages.thales-invia.fr/dashboard/dashboard_cva6.html"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
PIPELINE_MARKER = '<div class="list-group-item list-group-item-action py-3">'
JOB_MARKER = '<div class="col-12 border-top p-1">'


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


def parse_latest_pipeline(page: str, dashboard_url: str = DEFAULT_URL) -> dict:
    return parse_pipeline_summary(split_pipeline_cards(page)[0], dashboard_url)


def parse_public_dashboard(
    page: str,
    dashboard_url: str = DEFAULT_URL,
) -> dict:
    return parse_latest_pipeline(page, dashboard_url)


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
        "error": str(error),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-html", type=Path)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    try:
        page = (
            args.input_html.read_text(encoding="utf-8")
            if args.input_html
            else fetch_page(args.url, args.timeout)
        )
        reference = parse_public_dashboard(page, args.url)
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
