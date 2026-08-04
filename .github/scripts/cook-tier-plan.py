#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Validate and emit the public master_candidate cook.py CI matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

DEFAULT_PLAN = Path(".github/ci/master_candidate_cook_tiers.yml")
ACCEPTANCE_POLICIES = ("required", "diagnostic")


def load_yaml(path: Path) -> Any:
    if not path.is_file():
        raise ValueError(f"Required input is missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def enabled_tests(path: Path) -> list[str]:
    data = load_yaml(path)
    tests = data.get("testlist", [])
    return [test["test"] for test in tests if int(test.get("iterations", 1)) > 0]


def thales_matrix(ci_path: Path, matrix_key: str) -> dict[str, set[str]]:
    data = load_yaml(ci_path)
    try:
        entries = data[matrix_key]["parallel"]["matrix"]
    except (KeyError, TypeError) as error:
        raise ValueError(
            f"Cannot find {matrix_key}.parallel.matrix in {ci_path}"
        ) from error

    result: dict[str, set[str]] = {}
    for entry in entries:
        target = entry.get("MY_TARGET")
        testlists = entry.get("MY_TESTLIST", [])
        if target:
            result.setdefault(target, set()).update(testlists)
    return result


def file_fingerprint(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"Required comparison input is missing: {path}")
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def git_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def validate_plan(plan_path: Path) -> dict[str, Any]:
    plan = load_yaml(plan_path)
    if plan.get("schema_version") != 1:
        raise ValueError("Unsupported plan schema_version")

    comparison = plan["comparison"]
    ci_path = Path(comparison["source"])
    matrix = thales_matrix(ci_path, comparison["matrix_key"])
    scope_targets = plan["scope"]["targets"]
    if len(scope_targets) != len(set(scope_targets)):
        raise ValueError("scope.targets contains duplicates")

    report_tiers: dict[str, Any] = {}
    tier_pairs: dict[str, set[tuple[str, str]]] = {}
    for tier_name, tier in plan["tiers"].items():
        entries = tier["entries"]
        seen: set[tuple[str, str]] = set()
        enabled_total = 0
        enabled_by_acceptance = {policy: 0 for policy in ACCEPTANCE_POLICIES}
        report_entries = []

        for entry in entries:
            target = entry["target"]
            testlist_path = Path(entry["testlist"])
            testlist_name = testlist_path.stem
            acceptance = entry.get("acceptance")
            if acceptance not in ACCEPTANCE_POLICIES:
                raise ValueError(
                    f"{target}/{testlist_name} has invalid acceptance policy: "
                    f"{acceptance}"
                )
            if acceptance == "diagnostic" and not entry.get("acceptance_reason"):
                raise ValueError(
                    f"{target}/{testlist_name} diagnostic entry needs "
                    "acceptance_reason"
                )
            if tier_name == "tier1" and acceptance != "required":
                raise ValueError("Tier 1 entries must use required acceptance")
            pair = (target, testlist_name)
            if pair in seen:
                raise ValueError(
                    f"Duplicate {tier_name} pair: {target}/{testlist_name}"
                )
            seen.add(pair)

            if target not in scope_targets:
                raise ValueError(f"{target} is outside scope.targets")
            if target not in matrix or testlist_name not in matrix[target]:
                raise ValueError(
                    f"{target}/{testlist_name} is not in the Thales GitLab matrix"
                )

            target_dir = Path("config/target") / target
            testbench = load_yaml(target_dir / "testbench_cfg.yml")
            if testbench.get("hier") != entry["expected_hier"]:
                raise ValueError(
                    f"{target} hierarchy is {testbench.get('hier')}, "
                    f"expected {entry['expected_hier']}"
                )

            tests = enabled_tests(testlist_path)
            if len(tests) != int(entry["expected_enabled_tests"]):
                raise ValueError(
                    f"{testlist_path} has {len(tests)} enabled tests, "
                    f"expected {entry['expected_enabled_tests']}"
                )
            enabled_total += len(tests)
            enabled_by_acceptance[acceptance] += len(tests)
            report_entries.append(
                {
                    **entry,
                    "testlist_name": testlist_name,
                    "enabled_tests": tests,
                    "matrix_membership": True,
                }
            )

        if enabled_total != int(tier["expected_enabled_tests"]):
            raise ValueError(
                f"{tier_name} has {enabled_total} enabled target/test pairs, "
                f"expected {tier['expected_enabled_tests']}"
            )
        for acceptance, enabled_count in enabled_by_acceptance.items():
            expected_key = f"expected_{acceptance}_enabled_tests"
            if enabled_count != int(tier[expected_key]):
                raise ValueError(
                    f"{tier_name} has {enabled_count} {acceptance} enabled "
                    f"target/test pairs, expected {tier[expected_key]}"
                )
        tier_pairs[tier_name] = seen
        report_tiers[tier_name] = {
            "enabled_target_test_pairs": enabled_total,
            "required_enabled_target_test_pairs": enabled_by_acceptance["required"],
            "diagnostic_enabled_target_test_pairs": enabled_by_acceptance["diagnostic"],
            "entries": report_entries,
        }

    if not tier_pairs["tier1"].issubset(tier_pairs["tier2"]):
        raise ValueError("Tier 1 must be a subset of Tier 2")

    tier1_pairs = tier_pairs["tier1"]
    tier2_required_pairs = {
        (entry["target"], entry["testlist_name"])
        for entry in report_tiers["tier2"]["entries"]
        if entry["acceptance"] == "required"
    }
    if tier2_required_pairs != tier1_pairs:
        raise ValueError(
            "Tier 2 required entries must exactly match the Tier 1 acceptance set"
        )

    tier2_pairs = tier_pairs["tier2"]
    for target in scope_targets:
        expected = {(target, name) for name in matrix.get(target, set())}
        actual = {pair for pair in tier2_pairs if pair[0] == target}
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(
                f"Tier 2 is not testlist-complete for {target}; "
                f"missing={missing}, extra={extra}"
            )

    return {
        "schema_version": 1,
        "source_revision": git_revision(),
        "plan": file_fingerprint(plan_path),
        "comparison_source": file_fingerprint(ci_path),
        "scope_targets": scope_targets,
        "tiers": report_tiers,
        "comparison_boundary": {
            "shared": [
                "cook.py sw-compile-testlist entry point",
                "target configuration names and config/target inputs",
                "testlist names, sources, and enabled tests",
                "Spike tandem reference model",
            ],
            "public_tier_backend": comparison["public_backend"],
            "thales_backend": comparison["thales_backend"],
            "binary_toolchain_identity_shared": False,
            "full_pipeline_parity_claimed": False,
        },
    }


def matrix_for_tier(plan_path: Path, tier_name: str) -> dict[str, Any]:
    report = validate_plan(plan_path)
    entries = report["tiers"][tier_name]["entries"]
    matrix = []
    for entry in entries:
        matrix.append(
            {
                "target": entry["target"],
                "testlist": entry["testlist"],
                "testcase": entry["testlist_name"].replace("_", "-"),
                "toolchain": entry["toolchain"],
                "install_script": entry["install_script"],
                "compiler_march": entry["compiler_march"],
                "compiler_march_reason": entry["compiler_march_reason"],
                "expected_enabled_tests": entry["expected_enabled_tests"],
                "acceptance": entry["acceptance"],
                "acceptance_reason": entry.get("acceptance_reason", "none"),
            }
        )
    return {"include": matrix}


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def write_github_output(path: Path, key: str, value: str) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--output", type=Path)

    matrix_parser = subparsers.add_parser("matrix")
    matrix_parser.add_argument("--tier", choices=("tier1", "tier2"), required=True)
    matrix_parser.add_argument("--github-output", type=Path)
    matrix_parser.add_argument("--report", type=Path)

    entry_parser = subparsers.add_parser("entry-report")
    entry_parser.add_argument("--tier", choices=("tier1", "tier2"), required=True)
    entry_parser.add_argument("--target", required=True)
    entry_parser.add_argument("--testlist", required=True)
    entry_parser.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    try:
        report = validate_plan(args.plan)
        if args.command == "validate":
            if args.output:
                write_yaml(args.output, report)
            print("PASS: master_candidate cook tier plan is valid")
        elif args.command == "matrix":
            matrix = matrix_for_tier(args.plan, args.tier)
            encoded = json.dumps(matrix, separators=(",", ":"))
            if args.github_output:
                write_github_output(args.github_output, "matrix", encoded)
                write_github_output(
                    args.github_output,
                    "enabled_tests",
                    str(report["tiers"][args.tier]["enabled_target_test_pairs"]),
                )
            if args.report:
                write_yaml(args.report, report)
            print(encoded)
        else:
            testlist_name = Path(args.testlist).stem
            matches = [
                entry
                for entry in report["tiers"][args.tier]["entries"]
                if entry["target"] == args.target
                and entry["testlist_name"] == testlist_name
            ]
            if len(matches) != 1:
                raise ValueError(
                    f"Expected one {args.tier} entry for "
                    f"{args.target}/{testlist_name}, found {len(matches)}"
                )
            write_yaml(
                args.output,
                {
                    "schema_version": 1,
                    "source_revision": report["source_revision"],
                    "entry": matches[0],
                    "comparison_boundary": report["comparison_boundary"],
                },
            )
            print(f"PASS: {args.target}/{testlist_name} is in {args.tier}")
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as error:
        raise SystemExit(f"ERROR: {error}") from error


if __name__ == "__main__":
    main()
