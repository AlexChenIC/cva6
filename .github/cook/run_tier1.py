#!/usr/bin/env python3
# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Invoke atomic Cook recipes and reconcile actual live results with the selected lists."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flows.recipes.testharness_run_testlist import enabled_tests, report_path, Simulator
from flows.recipes.verilator_testharness_comp import testharness_binary
from flows.recipes.verilator_testharness_run import (
    read_tandem_report,
    simulation_directory,
    testharness_log_passed,
)
from flows.utils.logged_process import run_logged_process
from flows.utils.utils import CompMode
from prepare_testlists import materialize
from run_smoke import read_yaml, require_fields, sha256
from check_native_failures import check_native_failures


def checked_case(root, target, name):
    directory = simulation_directory(root, target, name, CompMode.rtl, True)
    result = read_yaml(directory / "result.yml")
    require_fields(
        result,
        {
            "target": target,
            "test_name": name,
            "status": "PASS",
            "iss_enabled": False,
            "tandem_enabled": True,
        },
        f"{name} result",
    )
    if result["iss_enabled"] is not False or result["tandem_enabled"] is not True:
        raise ValueError("Invalid result mode")
    manifest = read_yaml(directory / "cook_manifest.yml")
    require_fields(manifest, {"recipe": "verilator-testharness-run"}, "Run recipe")
    require_fields(
        manifest["options"],
        {
            "target": target,
            "test_name": name,
            "comp_mode": "rtl",
            "trace_mode": "notrace",
            "tandem_enabled": True,
            "iss_enabled": False,
            "interactive_gui": False,
        },
        "Run options",
    )
    execution = read_yaml(directory / "execution.yml")
    if (
        type(execution.get("exit_code")) is not int
        or execution["exit_code"] != 0
        or execution.get("timed_out") is not False
    ):
        raise ValueError(f"{name}: abnormal simulation termination")
    passed, detail = testharness_log_passed(directory / "testharness.log")
    if not passed:
        raise ValueError(detail)
    tandem = read_tandem_report(directory / "testharness.log.yaml")
    return result, tandem


def checked_suite(root, target, testlist):
    names = enabled_tests(Path(testlist))
    report = report_path(root, target, Simulator.verilator, testlist, True)
    summary = read_yaml(
        report.with_name(report.name.replace("_report.yml", "_summary.yml"))
    )
    require_fields(
        summary,
        {
            "schema_version": 1,
            "target": target,
            "testlist": testlist,
            "simulator": "verilator",
            "comp_mode": "rtl",
            "trace_mode": "notrace",
            "tandem_enabled": True,
            "iss_enabled": False,
            "status": "PASS",
        },
        "batch metadata",
    )
    for key, count in {"total": len(names), "passed": len(names), "failed": 0}.items():
        if type(summary.get(key)) is not int or summary[key] != count:
            raise ValueError(f"Batch count mismatch: {key}")
    cases, counts = [], {}
    for name in names:
        result, tandem = checked_case(root, target, name)
        cases.append({key: result[key] for key in ("test_name", "status", "detail")})
        counts[name] = {
            key: tandem[key]
            for key in ("instr_count", "csrs_match_count", "mismatches_count")
        }
    if summary["cases"] != cases:
        raise ValueError("Batch receipts do not match the planned test order")
    cooked = read_yaml(report)
    require_fields(cooked, {"status": "pass"}, "Cook report")
    rows = [
        {
            "status": "pass",
            "label": "PASS",
            "col": [target, case["test_name"], case["detail"]],
        }
        for case in cases
    ]
    metrics = cooked.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != 1:
        raise ValueError("Expected exactly one Cook report metric")
    require_fields(
        metrics[0],
        {"status": "pass", "type": "table_status", "value": rows},
        "Cook report rows",
    )
    return {
        "total": len(names),
        "passed": len(names),
        "failed": 0,
        "comparisons": counts,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("rv32", "rv64"), required=True)
    parser.add_argument("--suite", choices=("basic", "full"), default="full")
    args = parser.parse_args()
    root, output = Path.cwd(), Path("ci-results")
    output.mkdir(exist_ok=True)
    evidence = {
        "status": "FAIL",
        "profile": args.profile,
        "validation_mode": "live-tandem",
        "commands": [],
        "suites": {},
    }
    evidence_path = output / "tier1-evidence.json"

    def save():
        evidence_path.write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
        )

    def run(label, command, timeout=2400):
        evidence["active_stage"] = label
        save()
        print(f"Starting Cook stage: {label}", flush=True)
        code, timed_out = run_logged_process(
            command,
            cwd=root,
            env=os.environ.copy(),
            log=output / f"{label}.log",
            timeout=timeout,
        )
        evidence["commands"].append(
            {"stage": label, "argv": command, "exit_code": code, "timed_out": timed_out}
        )
        evidence["active_stage"] = None
        save()
        print(f"Completed {label}: exit={code}, timed_out={timed_out}", flush=True)
        if code != 0 or timed_out:
            print(
                (output / f"{label}.log").read_text(errors="replace")[-12000:],
                file=sys.stderr,
            )
            raise ValueError(f"{label}: exit={code}, timed_out={timed_out}")

    rc = 1
    try:
        config, lists = materialize(args.profile, output / "testlists")
        target = config["target"]
        evidence["target"] = target
        evidence["source_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=10
        ).strip()
        evidence["environment"] = read_yaml(
            Path(os.environ["CONFIG_DIR"]) / "environment.yml"
        )
        if (root / "build" / target).exists():
            raise ValueError("Use a fresh target build directory")
        cook = [sys.executable, "cook.py"]
        common = [
            "-t",
            target,
            "--trace-mode",
            "notrace",
            "--tandem-enabled",
            "--quiet",
        ]
        run("compile-testharness", cook + ["verilator-testharness-comp"] + common)
        suites = ("basic", "arch") if args.suite == "full" else ("basic",)
        for suite in suites:
            testlist = lists[suite]
            run(
                f"compile-{suite}",
                cook
                + [
                    "sw-compile-testlist",
                    "-t",
                    target,
                    "-c",
                    "github_actions_gcc",
                    "-l",
                    testlist,
                    "--quiet",
                ],
            )
            if suite == "basic":
                evidence["native_negative_checks"] = check_native_failures(
                    root, target, config, enabled_tests(Path(testlist)), cook, run
                )
                save()
                name = enabled_tests(Path(testlist))[0]
                run(
                    "single-test",
                    cook + ["verilator-testharness-run", "-n", name] + common,
                )
                checked_case(root, target, name)
                shutil.copytree(
                    simulation_directory(root, target, name, CompMode.rtl, True),
                    output / "single" / name,
                )
            run(
                f"run-{suite}",
                cook
                + ["testharness-run-testlist", "-s", "verilator", "-l", testlist]
                + common,
                timeout=3600,
            )
            evidence["suites"][suite] = checked_suite(root, target, testlist)
            save()
        evidence["binary_sha256"] = sha256(
            testharness_binary(root, target, CompMode.rtl, True)
        )
        evidence["elf_sha256"] = {
            str(path.relative_to(root)): sha256(path)
            for path in (root / "build" / target / "compile").glob("*/*.elf")
        }
        evidence["status"], rc = "PASS", 0
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ) as error:
        evidence["error"] = str(error)
        print(f"ERROR: {error}", file=sys.stderr)
    finally:
        save()
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
                stream.write(
                    f"## Cook live tandem / {args.profile}: {evidence['status']}\n\n"
                )
                for suite, result in evidence["suites"].items():
                    stream.write(
                        f"- {suite}: {result['passed']} PASS / {result['failed']} FAIL; native comparison reports checked.\n"
                    )
                stream.write(
                    "\nNot full historical cache coverage. Exclusions are in tier1.yml.\n"
                )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
