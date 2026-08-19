#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
"""Generate the CVA6 master_candidate Tier CI dashboard."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from jinja2 import Environment, FileSystemLoader


WORKFLOW_INFO = [
    {
        "key": "tier1",
        "display_name": "Tier 1",
        "matrix_label": "Tier 1",
        "file": "runs_tier1.json",
        "backend": "Verilator/TestHarness",
        "scope": "Pull request sanity",
    },
    {
        "key": "tier2",
        "display_name": "Tier 2",
        "matrix_label": "Tier 2",
        "file": "runs_tier2.json",
        "backend": "Verilator/TestHarness",
        "scope": "master_candidate regression",
    },
]

MATRIX_CONFIGS_ORDER = ["cv32a60x_axi", "cv32a65x_axi"]
MATRIX_SUITES_ORDER = ["base-rv32-p", "base-pmp"]
TREND_COUNT = 20
THALES_FILE = "thales_reference.json"
FRESH_AFTER_HOURS = 8


def is_valid_matrix_job(job: dict) -> bool:
    config = job.get("config", "")
    testcase = job.get("testcase", "")
    return bool(
        config
        and testcase
        and "${{" not in config
        and "${{" not in testcase
    )


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "N/A"
    minutes, secs = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"
    return f"{minutes}m {secs}s"


def format_datetime(value: str) -> str:
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_label(value: str, now: datetime) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return "age unavailable"
    seconds = max(0, int((now - parsed).total_seconds()))
    if seconds < 60:
        return "less than a minute ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def freshness(
    value: str,
    now: datetime,
    *,
    forced_stale: bool = False,
) -> dict[str, str | bool]:
    parsed = parse_datetime(value)
    stale = forced_stale
    if parsed is not None:
        age_hours = max(0, (now - parsed).total_seconds()) / 3600
        stale = stale or age_hours > FRESH_AFTER_HOURS
    return {
        "display": format_datetime(value),
        "age": age_label(value, now),
        "stale": stale,
        "label": "STALE" if stale else ("FRESH" if parsed else "UNKNOWN"),
    }


def load_json(path: Path, default):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def load_workflow_data(data_dir: Path) -> dict[str, list[dict]]:
    return {
        workflow["key"]: load_json(data_dir / workflow["file"], [])
        for workflow in WORKFLOW_INFO
    }


def ordered(items: set[str], preferred: list[str]) -> list[str]:
    return [item for item in preferred if item in items] + sorted(
        items - set(preferred)
    )


def build_matrix(all_data: dict[str, list[dict]]) -> tuple[dict, dict]:
    matrix: dict[str, dict] = {}
    orders: dict[str, dict[str, list[str]]] = {}

    for workflow in WORKFLOW_INFO:
        key = workflow["key"]
        latest = next(
            (
                run
                for run in all_data.get(key, [])
                if any(is_valid_matrix_job(job) for job in run.get("jobs", []))
            ),
            None,
        )
        if latest is None:
            orders[key] = {"configs": [], "suites": []}
            continue

        configs: set[str] = set()
        suites: set[str] = set()
        for job in latest.get("jobs", []):
            if not is_valid_matrix_job(job):
                continue
            config = job["config"]
            testcase = job["testcase"]
            configs.add(config)
            suites.add(testcase)
            matrix.setdefault(config, {}).setdefault(testcase, {})[key] = {
                "conclusion": job.get("conclusion", "unknown"),
                "html_url": job.get("html_url", ""),
            }
        orders[key] = {
            "configs": ordered(configs, MATRIX_CONFIGS_ORDER),
            "suites": ordered(suites, MATRIX_SUITES_ORDER),
        }

    return matrix, orders


def build_chart_data(all_data: dict[str, list[dict]]) -> dict:
    chart_data = {}
    for workflow in WORKFLOW_INFO:
        runs = list(reversed(all_data.get(workflow["key"], [])[:TREND_COUNT]))
        pass_rates = [
            round(run.get("passed_jobs", 0) / run.get("total_jobs", 1) * 100, 1)
            if run.get("total_jobs", 0)
            else 0
            for run in runs
        ]
        durations = [
            round(run.get("duration_seconds", 0) / 60, 1) for run in runs
        ]
        chart_data[workflow["key"]] = {
            "labels": [str(run.get("run_number", "")) for run in runs],
            "pass_rates": pass_rates,
            "durations": durations,
            "count": len(runs),
            "summary": (
                f"{len(runs)} completed runs. Latest pass rate "
                f"{pass_rates[-1]:g} percent and duration "
                f"{durations[-1]:g} minutes."
                if runs
                else "No completed run data."
            ),
        }
    return chart_data


def enrich_run(run: dict, now: datetime) -> dict:
    run["duration_display"] = format_duration(run.get("duration_seconds", 0))
    run["created_at_display"] = format_datetime(run.get("created_at", ""))
    run["updated_at_display"] = format_datetime(
        run.get("updated_at", run.get("created_at", ""))
    )
    run["observed_age"] = age_label(
        run.get("updated_at", run.get("created_at", "")), now
    )
    environment = run.get("environment", {})
    if isinstance(environment, dict):
        environment["freshness"] = freshness(
            environment.get("collected_at", ""),
            now,
            forced_stale=bool(environment.get("stale")),
        )
    for job in run.get("jobs", []):
        job["duration_display"] = format_duration(job.get("duration_seconds", 0))
    return run


def build_workflows_context(
    all_data: dict[str, list[dict]], now: datetime
) -> list[dict]:
    workflows = []
    for definition in WORKFLOW_INFO:
        runs = [
            enrich_run(run, now) for run in all_data.get(definition["key"], [])
        ]
        latest = runs[0] if runs else {
            "conclusion": "unknown",
            "head_branch": "N/A",
            "head_sha": "N/A",
            "head_sha_full": "",
            "passed_jobs": 0,
            "failed_jobs": 0,
            "skipped_jobs": 0,
            "total_jobs": 0,
            "duration_display": "N/A",
            "run_number": 0,
            "html_url": "",
            "observed_age": "age unavailable",
            "updated_at_display": "N/A",
            "environment": {},
        }
        workflows.append({**definition, "latest": latest, "runs": runs})
    return workflows


def load_thales_reference(data_dir: Path, now: datetime) -> dict:
    reference = load_json(data_dir / THALES_FILE, {})
    if not isinstance(reference, dict) or not reference.get("available"):
        return {
            "available": False,
            "status": "unknown",
            "status_label": "UNAVAILABLE",
            "backend": "VCS/UVM",
            "scope": "latest public pipeline",
            "branch": "N/A",
            "head_sha": "N/A",
            "head_sha_full": "",
            "pipeline_id": "N/A",
            "dashboard_url": reference.get(
                "dashboard_url",
                "https://riscv-ci.pages.thales-invia.fr/dashboard/dashboard_cva6.html",
            ),
            "created_at_display": "N/A",
            "duration_display": "N/A",
        }

    reference["created_at_display"] = format_datetime(reference.get("created_at", ""))
    reference["observed_age"] = age_label(reference.get("created_at", ""), now)
    reference["duration_display"] = format_duration(
        reference.get("duration_seconds", 0)
    )
    return reference


def source_relation(workflows: list[dict], thales: dict) -> dict[str, str]:
    thales_sha = thales.get("head_sha_full", "")
    github_shas = {
        workflow["latest"].get("head_sha_full", "") for workflow in workflows
    }
    github_shas.discard("")
    if not thales_sha or not github_shas:
        return {"kind": "unknown", "label": "Source comparison unavailable"}
    if github_shas == {thales_sha}:
        return {"kind": "match", "label": "Matching source revision"}
    return {"kind": "different", "label": "Different source revisions"}


def build_matrix_metadata(workflows: list[dict]) -> dict:
    return {
        workflow["key"]: {
            "label": f"GitHub Actions · {workflow['backend']}",
            "branch": workflow["latest"].get("head_branch", "N/A"),
            "head_sha": workflow["latest"].get("head_sha", "N/A"),
            "relation": "",
        }
        for workflow in workflows
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="site")
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "openhwgroup/cva6"),
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    all_data = load_workflow_data(data_dir)
    workflows = build_workflows_context(all_data, now)
    thales = load_thales_reference(data_dir, now)
    matrix, matrix_orders = build_matrix(all_data)
    relation = source_relation(workflows, thales)

    context = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "year": now.year,
        "repo": args.repo,
        "workflows": workflows,
        "thales": thales,
        "source_relation": relation,
        "matrix_data": matrix,
        "matrix_metadata": build_matrix_metadata(workflows),
        "matrix_orders": matrix_orders,
        "default_matrix_wf": "tier2" if all_data.get("tier2") else "tier1",
        "chart_data": build_chart_data(all_data),
        "trend_count": TREND_COUNT,
    }

    template_dir = Path(__file__).parent / "templates"
    environment = Environment(
        loader=FileSystemLoader(str(template_dir)), autoescape=True
    )
    html_page = environment.get_template("index.html").render(**context)
    (output_dir / "index.html").write_text(html_page, encoding="utf-8")

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        assets_dir = output_dir / "assets"
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        shutil.copytree(static_dir, assets_dir)

    print(f"Dashboard generated: {output_dir / 'index.html'}")
    print(f"GitHub runs: {sum(len(item['runs']) for item in workflows)}")
    print(f"Thales reference: {thales['status_label']}")


if __name__ == "__main__":
    main()
