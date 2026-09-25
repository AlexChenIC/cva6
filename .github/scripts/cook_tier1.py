#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute the declared RTL-only Tier 1 matrix row using atomic Cook recipes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cook_testharness_smoke import (
    GREETING,
    TESTLIST as HELLO_TESTLIST,
    TEST_NAME as HELLO_NAME,
    CompMode,
    Simulator,
    checked_report,
    checked_run,
    checked_summary,
    enabled_tests,
    report_path,
    run_logged_process,
    simulation_directory,
)

MATRIX = ".github/config/cook-tier1.json"
RISCV_TESTS_SHA = "f92842f91644092960ac7946a61ec2895e543cec"


def matrix_row(root: Path, target: str) -> tuple[dict, dict]:
    matrix = json.loads((root / MATRIX).read_text())
    rows = [row for row in matrix["include"] if row["target"] == target]
    if len(rows) != 1 or type(rows[0]["hello_world"]) is not bool:
        raise ValueError(f"Expected one declared Tier 1 row for {target}")
    if enabled_tests(root / matrix["testlist"]) != matrix["expected_tests"]:
        raise ValueError("Tier 1 testlist differs from the declared acceptance set")
    if rows[0]["hello_world"] and enabled_tests(root / HELLO_TESTLIST) != [HELLO_NAME]:
        raise ValueError("Hello World testlist must contain exactly one iteration")
    return matrix, rows[0]


def cook_commands(matrix: dict, row: dict) -> list[list[str]]:
    cook = [sys.executable, "cook.py"]
    target = ["-t", row["target"]]
    modes = ["--trace-mode", "notrace", "--no-iss-enabled", "--quiet"]

    def software(testlist: str) -> list[str]:
        return cook + [
            "sw-compile-testlist",
            *target,
            "-c",
            "github_actions_gcc",
            "-l",
            testlist,
            "--march",
            row["march"],
            "--mabi",
            "ilp32",
        ]

    def batch(testlist: str) -> list[str]:
        return cook + [
            "testharness-run-testlist",
            "--simulator",
            "verilator",
            *target,
            "-l",
            testlist,
            *modes,
        ]

    commands = [
        software(matrix["testlist"]),
        cook
        + ["verilator-testharness-comp", *target, "--trace-mode", "notrace", "--quiet"],
        batch(matrix["testlist"]),
    ]
    if row["hello_world"]:
        commands += [
            software(HELLO_TESTLIST),
            cook + ["verilator-testharness-run", *target, "-n", HELLO_NAME, *modes],
            batch(HELLO_TESTLIST),
        ]
    return commands


def check_batch(root: Path, target: str, testlist: str, names: list[str]) -> dict:
    report = report_path(root, target, Simulator.verilator, testlist)
    summary_path = report.with_name(report.name.replace("_report.yml", "_summary.yml"))
    summary = checked_summary(
        yaml.safe_load(summary_path.read_text()), target, testlist, names
    )
    checked_report(yaml.safe_load(report.read_text()), summary)
    for case in summary["cases"]:
        name = case["test_name"]
        result = checked_run(
            simulation_directory(root, target, name, CompMode.rtl),
            target,
            name,
            GREETING if name == HELLO_NAME else None,
        )
        if result.get("detail") != case["detail"]:
            raise ValueError(f"Run receipt disagrees with summary: {name}")
    return summary


def test_sources(root: Path) -> dict:
    """Record the pinned upstream input and verify both existing CVA6 patches."""
    directory = root / "verif/tests/riscv-tests"
    revision = subprocess.check_output(
        ["git", "-C", str(directory), "rev-parse", "HEAD"], text=True, timeout=10
    ).strip()
    if revision != RISCV_TESTS_SHA:
        raise ValueError(f"Unexpected riscv-tests revision: {revision}")
    for patch, prefix in (
        ("riscv-tests.patch", []),
        ("riscv-tests-env.patch", ["--directory=env"]),
    ):
        subprocess.run(
            [
                "git",
                "apply",
                "--reverse",
                "--check",
                *prefix,
                str(root / "verif/regress" / patch),
            ],
            cwd=directory,
            check=True,
            timeout=30,
        )
    submodules = subprocess.check_output(
        ["git", "-C", str(directory), "submodule", "status", "--recursive"],
        text=True,
        timeout=30,
    )
    if any(line.startswith(("-", "+", "U")) for line in submodules.splitlines()):
        raise ValueError("riscv-tests submodules are not at the pinned revisions")
    diff = subprocess.check_output(
        ["git", "-C", str(directory), "diff", "--binary"], timeout=30
    )
    env_diff = subprocess.check_output(
        ["git", "-C", str(directory / "env"), "diff", "--binary"], timeout=30
    )
    return {
        "revision": revision,
        "submodules": submodules,
        "patched_tree_diff_sha256": hashlib.sha256(diff + env_diff).hexdigest(),
    }


def main(target: str) -> int:
    root = Path.cwd()
    output = root / "ci-results"
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    evidence = {
        "schema_version": 1,
        "status": "FAIL",
        "target": target,
        "validation_mode": "rtl-only",
        "reference_model": None,
        "iss_enabled": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_head_sha": env.get("TIER_EVENT_HEAD_SHA", ""),
        "event_base_sha": env.get("TIER_EVENT_BASE_SHA", ""),
        "run_id": env.get("GITHUB_RUN_ID", "local"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT", "1"),
        "repository": env.get("GITHUB_REPOSITORY", "local"),
        "commands": [],
    }
    code = 1

    def execute(command: list[str], child_env: dict | None = None) -> None:
        log = output / f"step-{len(evidence['commands']) + 1}.log"
        print("Running:", " ".join(command), flush=True)
        rc, timeout = run_logged_process(
            command,
            cwd=root,
            env=env if child_env is None else child_env,
            log=log,
            timeout=2100,
        )
        evidence["commands"].append(
            {"argv": command, "exit_code": rc, "timed_out": timeout, "log": log.name}
        )
        if rc or timeout:
            print(log.read_text(errors="replace")[-16000:], file=sys.stderr)
            raise ValueError(
                f"Command failed: code={rc}, timeout={timeout}; {log.name}"
            )

    try:
        evidence["source_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, timeout=10
        ).strip()
        matrix, row = matrix_row(root, target)
        evidence["matrix_row"] = row
        evidence["expected_tests"] = matrix["expected_tests"]
        evidence["testlist_sha256"] = hashlib.sha256(
            (root / matrix["testlist"]).read_bytes()
        ).hexdigest()
        # Reuse the repository's pinned installer. Never reset an existing checkout.
        execute(
            ["bash", "-e", "verif/regress/install-riscv-tests.sh"],
            {
                **env,
                "TESTS_REPO": "https://github.com/riscv-software-src/riscv-tests.git",
                "TESTS_BRANCH": "master",
                "TESTS_HASH": RISCV_TESTS_SHA,
            },
        )
        evidence["test_sources"] = test_sources(root)
        execute(
            [
                sys.executable,
                ".github/scripts/prepare-cook-toolchains.py",
                "--output-dir",
                env["CONFIG_DIR"],
            ]
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

        for command in cook_commands(matrix, row):
            execute(command)
            if command[2] == "verilator-testharness-run":
                directory = simulation_directory(root, target, HELLO_NAME, CompMode.rtl)
                evidence["hello_single"] = checked_run(directory, target)
                saved = output / "hello-single"
                saved.mkdir(exist_ok=True)
                for name in ("result.yml", "cook_manifest.yml", "testharness.log"):
                    shutil.copy2(directory / name, saved / name)
            elif command[2] == "testharness-run-testlist":
                testlist = command[command.index("-l") + 1]
                hello = testlist == HELLO_TESTLIST
                names = [HELLO_NAME] if hello else matrix["expected_tests"]
                evidence["hello_batch" if hello else "base_batch"] = check_batch(
                    root, target, testlist, names
                )
        evidence["status"], code = "PASS", 0
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
        (output / "tier1-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        (output / "exit_code").write_text(f"{code}\n")
        if env.get("GITHUB_STEP_SUMMARY"):
            with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
                stream.write(
                    f"## RTL-only Tier 1: {target}: {evidence['status']}\n\n"
                    f"- Source: `{evidence.get('source_revision', 'unknown')}`\n"
                    "- Five declared RV32 instruction tests per configuration.\n"
                    "- cv32a65x_axi additionally runs Hello World directly and through a testlist.\n"
                    "- No ISS comparison, live tandem, Tier 2 or nightly validation.\n"
                    "- See artifacts for commands, tool identities, manifests and RTL logs.\n"
                )
                if code:
                    stream.write(f"\nFailure: {evidence.get('error', 'unknown')}\n")
    return code


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    raise SystemExit(main(parser.parse_args().target))
