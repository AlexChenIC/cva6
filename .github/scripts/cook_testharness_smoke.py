#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one real Hello World ELF through the atomic Cook recipes."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flows.recipes.testharness_run_testlist import enabled_tests, report_path, Simulator
from flows.recipes.verilator_testharness_run import (
    simulation_directory,
    testharness_log_passed,
)
from flows.utils.logged_process import run_logged_process
from flows.utils.utils import CompMode

TARGET = "cv32a65x_axi"
TESTLIST = "verif/tests/testlist_verilator_testharness_smoke.yaml"
TEST_NAME = "hello-world_0"
GREETING = "0: Hello World !"


def checked_summary(data: dict) -> dict:
    expected = {
        "schema_version": 1,
        "target": TARGET,
        "testlist": TESTLIST,
        "simulator": "verilator",
        "comp_mode": "rtl",
        "trace_mode": "notrace",
        "status": "PASS",
    }
    if not isinstance(data, dict) or any(data.get(k) != v for k, v in expected.items()):
        raise ValueError("Missing or inconsistent smoke summary")
    if data.get("iss_enabled") is not False:
        raise ValueError("Smoke must not enable ISS comparison")
    cases = data.get("cases")
    if (
        not isinstance(cases, list)
        or len(cases) != 1
        or not isinstance(cases[0], dict)
        or cases[0].get("test_name") != TEST_NAME
        or cases[0].get("status") != "PASS"
    ):
        raise ValueError("Expected exactly one passing Hello World result")
    for key, value in {"total": 1, "passed": 1, "failed": 0}.items():
        if type(data.get(key)) is not int or data[key] != value:
            raise ValueError(f"Inconsistent smoke count: {key}")
    return data


def checked_run(directory: Path) -> dict:
    result = yaml.safe_load((directory / "result.yml").read_text())
    expected = {
        "target": TARGET,
        "test_name": TEST_NAME,
        "comp_mode": "rtl",
        "trace_mode": "notrace",
        "status": "PASS",
    }
    if not isinstance(result, dict) or any(
        result.get(k) != v for k, v in expected.items()
    ):
        raise ValueError("Missing or inconsistent single-test result")
    if result.get("iss_enabled") is not False:
        raise ValueError("Single-test result unexpectedly enables ISS")
    log = directory / "testharness.log"
    passed, detail = testharness_log_passed(log)
    if not passed:
        raise ValueError(detail)
    if GREETING not in log.read_text():
        raise ValueError("TestHarness did not print the expected Hello World greeting")
    return result


def checked_report(data: dict, summary: dict) -> None:
    if not isinstance(data, dict) or data.get("status") != "pass":
        raise ValueError("Cook report does not report PASS")
    metrics = data.get("metrics")
    if (
        not isinstance(metrics, list)
        or len(metrics) != 1
        or not isinstance(metrics[0], dict)
    ):
        raise ValueError("Missing Cook testlist metric")
    metric = metrics[0]
    expected_row = {
        "status": "pass",
        "label": "PASS",
        "col": [TARGET, TEST_NAME, summary["cases"][0]["detail"]],
    }
    if (
        metric.get("status") != "pass"
        or metric.get("type") != "table_status"
        or metric.get("value") != [expected_row]
    ):
        raise ValueError("Cook report disagrees with the testlist summary")


def cook_commands() -> list[list[str]]:
    cook = [sys.executable, "cook.py"]
    return [
        cook
        + [
            "sw-compile-testlist",
            "-t",
            TARGET,
            "-c",
            "github_actions_gcc",
            "-l",
            TESTLIST,
        ],
        cook
        + [
            "verilator-testharness-comp",
            "-t",
            TARGET,
            "--trace-mode",
            "notrace",
            "--quiet",
        ],
        cook
        + [
            "verilator-testharness-run",
            "-t",
            TARGET,
            "-n",
            TEST_NAME,
            "--trace-mode",
            "notrace",
            "--no-iss-enabled",
            "--quiet",
        ],
        cook
        + [
            "testharness-run-testlist",
            "--simulator",
            "verilator",
            "-t",
            TARGET,
            "-l",
            TESTLIST,
            "--trace-mode",
            "notrace",
            "--no-iss-enabled",
            "--quiet",
        ],
    ]


def main() -> int:
    root = Path.cwd()
    output = root / "ci-results"
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    evidence = {
        "schema_version": 1,
        "target": TARGET,
        "testlist": TESTLIST,
        "validation_mode": "rtl-only",
        "reference_model": None,
        "iss_enabled": False,
        "event_head_sha": env.get("SMOKE_EVENT_HEAD_SHA", ""),
        "event_base_sha": env.get("SMOKE_EVENT_BASE_SHA", ""),
        "run_id": env.get("GITHUB_RUN_ID", "local"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT", "1"),
        "repository": env.get("GITHUB_REPOSITORY", "local"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "commands": [],
    }
    rc = 1
    try:
        evidence["source_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=10
        ).strip()
        if enabled_tests(Path(TESTLIST)) != [TEST_NAME]:
            raise ValueError(
                "Smoke testlist must contain only one Hello World iteration"
            )
        metadata = Path(env["CONFIG_DIR"]) / "environment.yml"
        environment = yaml.safe_load(metadata.read_text())
        if (
            not isinstance(environment, dict)
            or environment.get("validation_mode") != "rtl-only"
            or environment.get("required_toolchain") != "github_actions_gcc"
        ):
            raise ValueError("Missing or inconsistent toolchain environment")
        evidence["environment"] = environment
        shutil.copy2(metadata, output / "toolchain-environment.yml")

        run_dir = simulation_directory(root, TARGET, TEST_NAME, CompMode.rtl)
        for index, command in enumerate(cook_commands(), start=1):
            log = output / f"step-{index}.log"
            print("Running:", " ".join(command), flush=True)
            code, timed_out = run_logged_process(
                command, cwd=root, env=env, log=log, timeout=2100
            )
            evidence["commands"].append(
                {
                    "argv": command,
                    "exit_code": code,
                    "timed_out": timed_out,
                    "log": log.name,
                }
            )
            if code or timed_out:
                print(log.read_text(errors="replace")[-16000:], file=sys.stderr)
                raise ValueError(
                    f"Cook step {index} failed: code {code}, timeout={timed_out}"
                )
            if index == 3:
                evidence["single_test"] = checked_run(run_dir)
                # The testlist reruns the same ELF and replaces the run directory.
                saved = output / "single-test"
                saved.mkdir(exist_ok=True)
                for name in ("result.yml", "testharness.log", "cook_manifest.yml"):
                    shutil.copy2(run_dir / name, saved / name)

        report = report_path(root, TARGET, Simulator.verilator, TESTLIST)
        summary_path = report.with_name(
            report.name.replace("_report.yml", "_summary.yml")
        )
        summary = checked_summary(yaml.safe_load(summary_path.read_text()))
        checked_report(yaml.safe_load(report.read_text()), summary)
        evidence["batch_test"] = checked_run(run_dir)
        evidence["results"] = summary
        shutil.copy2(report, output / "testlist-report.yml")
        shutil.copy2(summary_path, output / "testlist-summary.yml")
        evidence["status"], rc = "PASS", 0
    except (
        OSError,
        KeyError,
        ValueError,
        TypeError,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ) as error:
        evidence["error"] = str(error)
        print(f"ERROR: {error}", file=sys.stderr)
    finally:
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        (output / "exit_code").write_text(f"{rc}\n")
        if env.get("GITHUB_STEP_SUMMARY"):
            with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
                stream.write(
                    f"## TestHarness smoke: {evidence['status']}\n\n"
                    f"- Source: `{evidence.get('source_revision', 'unknown')}`\n"
                    f"- Target: `{TARGET}`\n"
                    "- One Hello World ELF, run once directly and once through a testlist.\n"
                    "- RTL-only, notrace; no ISS comparison or live tandem.\n"
                    "- See the smoke artifact for commands, tool versions and per-step logs.\n"
                )
                if rc:
                    stream.write(f"\nFailure: {evidence.get('error', 'unknown')}\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
