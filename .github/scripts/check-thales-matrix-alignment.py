#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Verify that a public Tier target/testlist pair exists in Thales GitLab CI."""

import argparse
import hashlib
from pathlib import Path
import subprocess

import yaml


def file_fingerprint(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"Required comparison input is missing: {path}")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def source_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def source_worktree_dirty() -> bool:
    return bool(
        subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--ignore-submodules=untracked",
                "--",
                ".",
                ":(exclude)ci-results",
                ":(exclude)ci-results/**",
                ":(exclude)build",
                ":(exclude)build/**",
                ":(exclude)artifacts",
                ":(exclude)artifacts/**",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gitlab-ci", default=".gitlab-ci.yml", type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--testlist", required=True)
    parser.add_argument("--test-name", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    ci_data = yaml.safe_load(args.gitlab_ci.read_text(encoding="utf-8"))
    matrix = ci_data[".testlist_matrix_target"]["parallel"]["matrix"]
    requested_testlist = Path(args.testlist).stem
    target_dir = Path("config") / "target" / args.target
    isa_file = target_dir / "isa.yml"
    testbench_file = target_dir / "testbench_cfg.yml"
    linker_file = target_dir / "link.ld"
    spike_file = target_dir / "spike.yaml"
    testlist_file = Path(args.testlist)
    testlist_data = yaml.safe_load(testlist_file.read_text(encoding="utf-8"))
    available_tests = [
        test["test"]
        for test in testlist_data.get("testlist", [])
        if test.get("iterations", 1) > 0
    ]
    selected_tests = args.test_name or available_tests

    unknown_tests = sorted(set(selected_tests) - set(available_tests))
    if unknown_tests:
        raise SystemExit(
            f"Selected tests are not enabled in {args.testlist}: "
            + ", ".join(unknown_tests)
        )

    target_entry = next(
        (entry for entry in matrix if entry.get("MY_TARGET") == args.target), None
    )
    if target_entry is None:
        raise SystemExit(
            f"{args.target} is not present in .testlist_matrix_target"
        )

    thales_testlists = target_entry.get("MY_TESTLIST", [])
    if requested_testlist not in thales_testlists:
        raise SystemExit(
            f"{args.target}/{requested_testlist} is not present in the Thales matrix"
        )

    isa_data = yaml.safe_load(isa_file.read_text(encoding="utf-8"))
    testbench_data = yaml.safe_load(testbench_file.read_text(encoding="utf-8"))

    report = {
        "schema_version": 2,
        "source": str(args.gitlab_ci),
        "source_revision": source_revision(),
        "source_worktree_dirty": source_worktree_dirty(),
        "gitlab_ci_sha256": hashlib.sha256(
            args.gitlab_ci.read_bytes()
        ).hexdigest(),
        "target": args.target,
        "canonical_target_name": args.target,
        "requested_testlist": requested_testlist,
        "selected_tests": selected_tests,
        "selected_test_count": len(selected_tests),
        "thales_testlists": thales_testlists,
        "matrix_match": True,
        "canonical_target": {
            "march": isa_data["march"],
            "mabi": isa_data["mabi"],
            "hier": testbench_data["hier"],
        },
        "shared_inputs": [
            file_fingerprint(isa_file),
            file_fingerprint(testbench_file),
            file_fingerprint(linker_file),
            file_fingerprint(spike_file),
            file_fingerprint(testlist_file),
            file_fingerprint(Path("flows/recipes/sw_compile_testlist.py")),
            file_fingerprint(Path("flows/recipes/sw_compile.py")),
        ],
        "thales_compile_script": ci_data["testlist_compile"]["script"],
        "thales_run_script": ci_data["testlist_run_sim_rtl"]["script"],
        "thales_toolchain_key": f"my_{args.target}_toolchain",
        "thales_toolchain_runtime_source": "$CONFIG_DIR/compiler.yml",
        "toolchain_binary_identity_shared": False,
        "comparison_boundary": {
            "thales": "VCS/UVM with Spike tandem",
            "public_tier": "Verilator/TestHarness with Spike comparison",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(report, sort_keys=False), encoding="utf-8"
    )
    print(
        f"PASS: {args.target}/{requested_testlist} exists in the Thales matrix"
    )


if __name__ == "__main__":
    main()
