#!/usr/bin/env python3
# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Run bounded Cook suites and independently reconcile their native evidence."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from flows.utils.testharness_tandem import read_tandem_report, testharness_mode
from prepare_testlists import materialize, names
from run_smoke import (
    checked_report,
    metric,
    read_yaml,
    require_fields,
    run_logged,
    sha256,
)

UPSTREAM = "fb095566d6ce3a2a89d0a24d3c147863f058cfdb"
USER_CHECKPOINT = "9255652fe53d44b6172f6c2bee5be35c624357c5"


def checked_case(root, target, name, run_name=None):
    directory = (
        root
        / "build"
        / target
        / "simulation"
        / testharness_mode(True)
        / (run_name or name)
    )
    report = checked_report(directory, "verilator-testharness-run", name)
    manifest = read_yaml(directory / "cook_manifest.yml")
    require_fields(manifest, {"recipe": "verilator-testharness-run"}, "Run manifest")
    require_fields(
        manifest["options"],
        {
            "target": target,
            "test_name": name,
            "tandem_enabled": True,
            "comp_mode": "rtl",
            "trace_mode": "notrace",
            "run_name": run_name,
        },
        "Run options",
    )
    log = (directory / "testharness.log").read_text()
    if "*** SUCCESS *** (tohost = 0)" not in log or any(
        marker in log for marker in ("*** FAILED ***", "UVM_ERROR", "UVM_FATAL")
    ):
        raise ValueError(f"{name}: no successful normal RTL termination")
    native = read_tandem_report(directory / "testharness.log.yaml")
    counts = {
        key: native[key]
        for key in ("instr_count", "csrs_match_count", "mismatches_count")
    }
    if metric(report, "Tandem comparison", name) != [{"status": "pass", **counts}]:
        raise ValueError(f"{name}: Cook and native tandem results disagree")
    source = root / "config" / "target" / target / "spike.yaml"
    provenance = read_yaml(directory / "spike-config-source.yml")
    command = json.loads((directory / "simulation.command.json").read_text())
    configs = [arg for arg in command if arg.startswith("+config_file=")]
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
            or configs != [f"+config_file={snapshot}"]
        ):
            raise ValueError("Spike model configuration was not preserved")
    elif provenance != {"mode": "rtl-derived"} or configs:
        raise ValueError("Unexpected Spike model override")
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--scope", choices=("probe", "tier1", "pilot"), default="tier1")
    parser.add_argument("--check-reference-baseline", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    output = root / "ci-results"
    output.mkdir(exist_ok=True)
    evidence = {
        "status": "FAIL",
        "scope": args.scope,
        "profile": args.profile,
        "commands": [],
        "suites": {},
        "single_runs": {},
        "negative_controls": {},
    }
    destination = output / "stage1-evidence.json"
    cook = [sys.executable, "cook.py"]

    def save():
        destination.write_text(json.dumps(evidence, indent=2) + "\n")

    def run(label, command, expected_failure=False, timeout=2100, cwd=None):
        evidence["active_stage"] = label
        save()
        code, timed_out = run_logged(
            command,
            cwd=cwd or root,
            env=os.environ.copy(),
            log=output / f"{label}.log",
            timeout=timeout,
        )
        evidence["commands"].append(
            {
                "stage": label,
                "argv": command,
                "exit_code": code,
                "timed_out": timed_out,
                "expected_failure": expected_failure,
            }
        )
        evidence["active_stage"] = None
        save()
        if timed_out or (
            expected_failure is not None
            and (code == 0 if expected_failure else code != 0)
        ):
            raise ValueError(f"{label}: exit={code}, outer timeout={timed_out}")
        return code

    try:
        selection = "pilots" if args.scope == "pilot" else "profiles"
        config, lists = materialize(args.profile, output / "testlists", selection)
        target = config["target"]
        evidence.update(
            target=target,
            environment=config["environment"],
            upstream=UPSTREAM,
            user_checkpoint=USER_CHECKPOINT,
            source_revision=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], text=True
            ).strip(),
        )
        # Official submodule patches are recorded separately, not mistaken for
        # extra processor RTL changes in this reference.
        baseline_check = subprocess.run(
            [
                "git",
                "diff",
                "--exit-code",
                "--ignore-submodules=dirty",
                UPSTREAM,
                "--",
                "core",
                "config/target",
            ],
            check=False,
            timeout=30,
            capture_output=True,
            text=True,
        )
        if baseline_check.returncode not in (0, 1):
            raise ValueError("Could not inspect the reference RTL baseline")
        (output / "core-and-target.diff").write_text(baseline_check.stdout)
        evidence["no_extra_core_or_target_changes"] = baseline_check.returncode == 0
        if args.check_reference_baseline and baseline_check.returncode:
            raise ValueError("Reference adds processor RTL or target changes")
        if args.scope == "probe":
            data = read_yaml(Path(lists["basic"]))
            data["testlist"] = data["testlist"][:1]
            probe = output / "testlists" / "probe.yaml"
            probe.write_text(yaml.safe_dump(data, sort_keys=False))
            lists = {"probe": str(probe)}
        common = ["-t", target, "--tandem-enabled", "--quiet"]
        for suite, testlist in lists.items():
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
        run(
            "compile-testharness",
            cook
            + [
                "verilator-testharness-comp",
                *common,
                "--jobs",
                os.environ.get("NUM_JOBS", "2"),
            ],
        )
        model = root / "build" / target / "elab" / testharness_mode(True)
        checked_report(model, "verilator-testharness-comp", "hardware")
        all_names = []
        for suite, testlist in lists.items():
            planned = names(read_yaml(Path(testlist)))
            all_names.extend(planned)
            for name in planned:
                checked_report(
                    root / "build" / target / "compile" / name, "sw-compile", name
                )
            # Check independent single-test use, then testlist composition.
            run(
                f"single-{suite}",
                cook
                + [
                    "verilator-testharness-run",
                    "-n",
                    planned[0],
                    "--run-name",
                    f"single-{suite}",
                    *common,
                ],
            )
            evidence["single_runs"][suite] = {
                "test_name": planned[0],
                "run_name": f"single-{suite}",
                "comparisons": checked_case(
                    root, target, planned[0], f"single-{suite}"
                ),
            }
            run(
                f"batch-{suite}",
                cook
                + [
                    "testharness-run-testlist",
                    "--simulator",
                    "verilator",
                    "-l",
                    testlist,
                    *common,
                ],
            )
            batch = (
                root
                / "build"
                / target
                / "simulation"
                / f"testharness_verilator_{Path(testlist).stem}_tandem"
            )
            report = checked_report(batch, "testharness-run-testlist", suite)
            expected = [
                {
                    "status": "pass",
                    "test": name,
                    "report": str(
                        root
                        / "build"
                        / target
                        / "simulation"
                        / testharness_mode(True)
                        / name
                    ),
                }
                for name in planned
            ]
            if (
                metric(report, "Test results", suite) != expected
                or report["label"] != f"{len(planned)}/{len(planned)} PASS"
            ):
                raise ValueError("Batch plan and Cook report disagree")
            evidence["suites"][suite] = {
                name: checked_case(root, target, name) for name in planned
            }
            save()
        if args.profile == "rv32-60x" and args.scope == "tier1":
            # Infrastructure controls, not additional functional/ISA coverage.
            for fixture, seconds in (("fail", "30"), ("loop", "5")):
                name = f"ci-control-{fixture}"
                run(
                    f"compile-control-{fixture}",
                    cook
                    + [
                        "sw-compile",
                        "-t",
                        target,
                        "-c",
                        "github_actions_gcc",
                        "--out",
                        name,
                        "--march",
                        config["march"],
                        "--mabi",
                        config["mabi"],
                        "--linker",
                        f"config/target/{target}/link.ld",
                        "--options",
                        "nostdlib",
                        "--options",
                        "nostartfiles",
                        f".github/cook/fixtures/{fixture}.S",
                        "--quiet",
                    ],
                )
                code = run(
                    f"control-{fixture}",
                    cook
                    + [
                        "verilator-testharness-run",
                        "-n",
                        name,
                        "--sim-timeout",
                        seconds,
                        *common,
                    ],
                    expected_failure=True,
                    timeout=60,
                )
                directory = (
                    root
                    / "build"
                    / target
                    / "simulation"
                    / testharness_mode(True)
                    / name
                )
                report = read_yaml(directory / "cook_report.yml")
                if report.get("status") != "fail":
                    raise ValueError("Intentional failure has no failing Cook report")
                log = (directory / "testharness.log").read_text()
                if fixture == "loop" and not any(
                    "timed out" in str(m) for m in report.get("metrics", [])
                ):
                    raise ValueError("Timeout was not recorded")
                if fixture == "fail" and "*** FAILED ***" not in log:
                    raise ValueError("Software failure was not observed")
                control = output / "negative-controls" / fixture
                control.parent.mkdir(exist_ok=True)
                shutil.move(str(directory), control)
                evidence["negative_controls"][fixture] = {
                    "status": "PASS",
                    "expected_recipe": "fail",
                    "exit_code": code,
                }
            first = (
                root
                / "build"
                / target
                / "simulation"
                / testharness_mode(True)
                / all_names[0]
            )
            second = (
                root
                / "build"
                / target
                / "compile"
                / all_names[1]
                / f"{all_names[1]}.elf"
            )
            mismatch = output / "negative-controls" / "mismatch"
            mismatch.mkdir()
            command = json.loads((first / "simulation.command.json").read_text())
            command = [
                f"+elf_file={second}" if arg.startswith("+elf_file=") else arg
                for arg in command
            ]
            # Raw native exit status alone is not a comparison verdict.
            run(
                "control-mismatch",
                command,
                expected_failure=None,
                timeout=60,
                cwd=mismatch,
            )
            native_path = mismatch / "testharness.log.yaml"
            native = read_yaml(native_path)
            if (
                type(native.get("mismatches_count")) is not int
                or native["mismatches_count"] < 1
            ):
                raise ValueError("Controlled model/RTL divergence was not detected")
            divergent = any(
                isinstance(row, dict)
                and isinstance(row.get("core"), dict)
                and isinstance(row.get("reference_model"), dict)
                and any(
                    row["core"].get(key) is not None
                    and row["core"].get(key) != row["reference_model"].get(key)
                    for key in ("insn", "pc_rdata")
                )
                for row in native.get("mismatches", [])
            )
            if not divergent:
                raise ValueError("Control has no native instruction/PC divergence")
            try:
                read_tandem_report(native_path)
            except ValueError:
                pass
            else:
                raise ValueError(
                    "Divergent native report passed the acceptance validator"
                )
            evidence["negative_controls"]["mismatch"] = {
                "status": "PASS",
                "expected_native": "FAIL",
                "mismatches_count": native["mismatches_count"],
                "divergent_instruction": True,
            }
        evidence["status"] = "PASS"
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ) as error:
        evidence["error"] = str(error)
        print(f"Stage 1 validation failed: {error}", file=sys.stderr)
        if evidence.get("commands"):
            stage = evidence["commands"][-1]["stage"]
            print(
                (output / f"{stage}.log").read_text(errors="replace")[-12000:],
                file=sys.stderr,
            )
        return 1
    finally:
        save()


if __name__ == "__main__":
    raise SystemExit(main())
