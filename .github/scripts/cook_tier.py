#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CI composition of atomic Cook recipes and versioned evidence artifact."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flows.utils.logged_process import run_logged_process
from flows.recipes.testharness_run_testlist import enabled_tests, report_path, Simulator


def checked_summary(
    data: dict, *, target: str, testlist: str, expected: list[str]
) -> dict:
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Missing supported testlist summary")
    for key, value in {
        "target": target,
        "testlist": testlist,
        "simulator": "verilator",
        "iss_enabled": True,
        "comp_mode": "rtl",
        "trace_mode": "notrace",
    }.items():
        if data.get(key) != value:
            raise ValueError(f"Testlist summary mismatch: {key}")
    cases = data.get("cases")
    if not isinstance(cases, list) or [c.get("test_name") for c in cases] != expected:
        raise ValueError("Testlist result does not match expected compiled cases")
    passed = sum(c.get("status") == "PASS" for c in cases)
    if not cases or any(c.get("status") not in {"PASS", "FAIL"} for c in cases):
        raise ValueError("Empty or malformed testlist cases")
    for key, value in {
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
    }.items():
        if type(data.get(key)) is not int or data[key] != value:
            raise ValueError(f"Inconsistent result count: {key}")
    if data.get("status") != "PASS" or passed != len(cases):
        raise ValueError("Testlist reported failing cases")
    return data


def main() -> int:
    root = Path.cwd()
    output = Path(os.environ.get("RESULTS_DIR", "ci-results"))
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    target, testlist = env["TIER_CONFIG"], env["TIER_TESTLIST"]
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    evidence = {
        "schema_version": 1,
        "tier": env["TIER_NAME"],
        "target": target,
        "testcase": env["TIER_TESTCASE"],
        "testlist": testlist,
        "simulator": "verilator",
        "reference_model": "spike-offline",
        "source_revision": source_sha,
        "event_head_sha": env.get("TIER_EVENT_HEAD_SHA", ""),
        "event_base_sha": env.get("TIER_EVENT_BASE_SHA", ""),
        "run_id": env.get("GITHUB_RUN_ID", "local"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT", "1"),
        "repository": env.get("GITHUB_REPOSITORY", "local"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "commands": [],
    }
    rc = 1
    try:
        expected = enabled_tests(Path(testlist))
        cook = [sys.executable, "cook.py"]
        commands = [
            cook
            + [
                "sw-compile-testlist",
                "-t",
                target,
                "-c",
                "github_actions_gcc",
                "-l",
                testlist,
                "--march",
                env["TIER_COMPILER_MARCH"],
            ],
            cook + ["verilator-testharness-comp", "-t", target, "--quiet"],
            cook
            + [
                "testharness-run-testlist",
                "--simulator",
                "verilator",
                "-t",
                target,
                "-l",
                testlist,
                "--iss-enabled",
                "--quiet",
            ],
        ]
        for index, command in enumerate(commands):
            log = output / f"step-{index+1}.log"
            print("Running:", " ".join(command), flush=True)
            code, timed_out = run_logged_process(
                command, cwd=root, env=env, log=log, timeout=3600
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
                    f"Cook step {index+1} failed: code {code}, timeout={timed_out}"
                )
        report = report_path(root, target, Simulator.verilator, testlist)
        summary_path = report.with_name(
            report.name.replace("_report.yml", "_summary.yml")
        )
        summary = checked_summary(
            yaml.safe_load(summary_path.read_text()),
            target=target,
            testlist=testlist,
            expected=expected,
        )
        evidence["results"] = summary
        shutil.copy2(report, output / "testlist-report.yml")
        shutil.copy2(summary_path, output / "testlist-summary.yml")
        evidence["status"], rc = "PASS", 0
    except (OSError, KeyError, ValueError, TypeError, yaml.YAMLError) as error:
        evidence["error"] = str(error)
        print(f"ERROR: {error}", file=sys.stderr)
    finally:
        metadata = Path(env["CONFIG_DIR"]) / "environment.yml"
        if metadata.is_file():
            evidence["environment"] = yaml.safe_load(metadata.read_text())
            shutil.copy2(metadata, output / "toolchain-environment.yml")
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
        (output / "exit_code").write_text(f"{rc}\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
