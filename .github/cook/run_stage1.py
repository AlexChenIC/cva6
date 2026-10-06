#!/usr/bin/env python3
# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Execute only Cook recipes and reconcile unified reports with native evidence."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flows.utils.autocompletion import CompMode
from flows.utils.testharness import (
    testharness_binary,
    simulation_directory,
    read_tandem_report,
    testharness_log_passed,
)
from flows.utils.logged_process import run_logged_process
from prepare_stage1 import materialize, names
from run_smoke import checked_report, metric, read_yaml, require_fields, sha256
from check_native_failures import check_native_failures


def checked_case(root, target, name):
    directory = simulation_directory(root, target, name, CompMode.rtl, True)
    checked_report(directory, "verilator-testharness-run", name)
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
    source = root / "config" / "target" / target / "spike.yaml"
    provenance = read_yaml(directory / "spike-config-source.yml")
    command = json.loads((directory / "simulation.command.json").read_text())
    config_args = [arg for arg in command if arg.startswith("+config_file=")]
    if source.is_file():
        snapshot = directory / "spike-config.yaml"
        if (
            provenance
            != {
                "mode": "target-yaml",
                "source": str(source.relative_to(root)),
                "sha256": sha256(source),
            }
            or sha256(snapshot) != sha256(source)
            or config_args != [f"+config_file={snapshot}"]
        ):
            raise ValueError(f"{name}: target Spike configuration evidence mismatch")
    elif provenance != {"mode": "rtl-derived"} or config_args:
        raise ValueError(f"{name}: unexpected Spike configuration override")
    return result, tandem


def checked_suite(root, target, testlist):
    planned = names(read_yaml(Path(testlist)))
    directory = (
        root
        / "build"
        / target
        / "simulation"
        / f"testharness_verilator_{Path(testlist).stem}_tandem"
    )
    report = checked_report(directory, "testharness-run-testlist", "batch")
    expected = [
        {
            "status": "pass",
            "test": name,
            "report": str(simulation_directory(root, target, name, CompMode.rtl, True)),
        }
        for name in planned
    ]
    if (
        metric(report, "Test results", "batch") != expected
        or report["label"] != f"{len(planned)}/{len(planned)} PASS"
    ):
        raise ValueError("Batch rows/counts disagree with plan")
    counts = {}
    for name in planned:
        _, native = checked_case(root, target, name)
        counts[name] = {
            key: native[key]
            for key in ("instr_count", "csrs_match_count", "mismatches_count")
        }
    return dict(total=len(planned), passed=len(planned), failed=0, comparisons=counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--selection", choices=("profiles", "diagnostics", "pilots"), default="profiles"
    )
    args = parser.parse_args()
    root, output = Path.cwd(), Path("ci-results")
    output.mkdir(exist_ok=True)
    evidence = dict(
        status="FAIL",
        profile=args.profile,
        selection=args.selection,
        validation_mode="live-tandem",
        commands=[],
        suites={},
    )
    destination = output / "stage1-evidence.json"

    def save():
        destination.write_text(json.dumps(evidence, indent=2) + "\n")

    def run(label, command, timeout=2400):
        evidence["active_stage"] = label
        save()
        code, timed_out = run_logged_process(
            command,
            cwd=root,
            env=os.environ.copy(),
            log=output / f"{label}.log",
            timeout=timeout,
        )
        evidence["commands"].append(
            dict(stage=label, argv=command, exit_code=code, timed_out=timed_out)
        )
        evidence["active_stage"] = None
        save()
        if code != 0 or timed_out:
            print(
                (output / f"{label}.log").read_text(errors="replace")[-14000:],
                flush=True,
            )
            raise ValueError(f"{label}: exit={code}, timed_out={timed_out}")

    code = 1
    try:
        config, lists = materialize(args.profile, output / "testlists", args.selection)
        target = config["target"]
        evidence.update(
            target=target,
            source_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
        )
        if (root / "build" / target).exists():
            raise ValueError("Use a fresh target build directory")
        evidence["environment"] = read_yaml(
            Path(os.environ["CONFIG_DIR"]) / "environment.yml"
        )
        cook = [sys.executable, "cook.py"]
        common = [
            "-t",
            target,
            "--trace-mode",
            "notrace",
            "--tandem-enabled",
            "--quiet",
        ]
        run(
            "compile-testharness",
            cook + ["verilator-testharness-comp", "--jobs", "2"] + common,
        )
        errors = []
        for suite, testlist in lists.items():
            try:
                run(
                    "compile-" + suite,
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
                planned = names(read_yaml(Path(testlist)))
                if suite == "basic":
                    evidence["native_negative_checks"] = check_native_failures(
                        root, target, config, planned, cook, run
                    )
                    run(
                        "single-test",
                        cook + ["verilator-testharness-run", "-n", planned[0]] + common,
                    )
                    checked_case(root, target, planned[0])
                    shutil.copytree(
                        simulation_directory(
                            root, target, planned[0], CompMode.rtl, True
                        ),
                        output / "single" / planned[0],
                    )
                run(
                    "run-" + suite,
                    cook
                    + ["testharness-run-testlist", "-s", "verilator", "-l", testlist]
                    + common,
                    timeout=3600,
                )
                evidence["suites"][suite] = dict(
                    status="PASS", **checked_suite(root, target, testlist)
                )
            except (OSError, TypeError, KeyError, ValueError, yaml.YAMLError) as error:
                errors.append(str(error))
                evidence["suites"][suite] = dict(status="FAIL", error=str(error))
            save()
        evidence["binary_sha256"] = sha256(
            testharness_binary(root, target, CompMode.rtl, True)
        )
        evidence["elf_sha256"] = {
            str(p.relative_to(root)): sha256(p)
            for p in (root / "build" / target / "compile").glob("*/*.elf")
        }
        if errors:
            raise ValueError("; ".join(errors))
        evidence["status"], code = "PASS", 0
    except (
        OSError,
        TypeError,
        KeyError,
        ValueError,
        yaml.YAMLError,
        subprocess.SubprocessError,
    ) as error:
        evidence["error"] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        save()
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as stream:
                stream.write(
                    f"## {args.selection} / {args.profile}: {evidence['status']}\n"
                )
                stream.write(
                    "\nActual results: " + json.dumps(evidence["suites"]) + "\n"
                )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
