# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re

import typer
import yaml

from flows.recipes.verilator_testharness_comp import testharness_binary
from flows.recipes.verilator_testharness_run import verilator_testharness_run
from flows.utils.manifest import require_prerequisite
from flows.utils.report_builder import Report, TableStatusMetric
from flows.utils.utils import (
    CompMode,
    TraceMode,
    autocompletion_target,
    autocompletion_testlist,
    print_error,
    print_info,
    print_param_table,
    print_recipe_end,
    print_recipe_title,
    print_step,
)

app = typer.Typer()


class Simulator(str, Enum):
    verilator = "verilator"


def enabled_tests(testlist_file: Path) -> list[tuple[str, int]]:
    try:
        data = yaml.safe_load(testlist_file.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"Cannot read testlist {testlist_file}: {error}") from error
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML in {testlist_file}: {error}") from error

    if not isinstance(data, dict) or not isinstance(data.get("testlist"), list):
        raise ValueError(f"Missing testlist sequence in {testlist_file}")

    selected: list[tuple[str, int]] = []
    for index, entry in enumerate(data["testlist"]):
        if not isinstance(entry, dict):
            raise ValueError(f"Testlist entry {index} must be a mapping")
        name = entry.get("test")
        iterations = entry.get("iterations", 1)
        if not isinstance(name, str) or not name:
            raise ValueError(f"Testlist entry {index} has no valid test name")
        if isinstance(iterations, bool) or not isinstance(iterations, int):
            raise ValueError(f"Test '{name}' iterations must be an integer")
        if iterations < 0:
            raise ValueError(f"Test '{name}' iterations cannot be negative")
        if iterations:
            selected.append((name, iterations))
    return selected


def report_path(
    repo_dir: Path, target: str, simulator: Simulator, testlist: str
) -> Path:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(testlist).stem)
    return (
        repo_dir
        / "build"
        / target
        / "simulation"
        / f"testharness_{simulator.value}_{label}_report.yml"
    )


def run_entries(
    *,
    tests: list[tuple[str, int]],
    target: str,
    comp_mode: CompMode,
    trace_mode: TraceMode,
    iss_enabled: bool,
    quiet: bool,
) -> tuple[TableStatusMetric, bool]:
    metric = TableStatusMetric("TestHarness testlist results")
    metric.add_column("Target", "text")
    metric.add_column("Test", "text")
    metric.add_column("Iteration", "text")
    failed = False

    for base_name, iterations in tests:
        for iteration in range(iterations):
            compiled_name = f"{base_name}_{iteration}"
            try:
                verilator_testharness_run(
                    target=target,
                    test_name=compiled_name,
                    comp_mode=comp_mode,
                    trace_mode=trace_mode,
                    iss_enabled=iss_enabled,
                    interactive_gui=False,
                    quiet=quiet,
                )
            except typer.Exit:
                metric.add_fail(target, base_name, str(iteration))
                print_error(f"{compiled_name}: returned error", quiet=quiet)
                failed = True
            else:
                metric.add_pass(target, base_name, str(iteration))
    return metric, failed


@app.command()
def testharness_run_testlist(
    simulator: Simulator = typer.Option(
        ...,
        "--simulator",
        help="TestHarness simulator",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="CVA6 user configuration",
        autocompletion=autocompletion_target,
    ),
    testlist: str = typer.Option(
        ...,
        "--testlist",
        "-l",
        help="Testlist YAML file",
        autocompletion=autocompletion_testlist,
    ),
    comp_mode: CompMode = typer.Option(CompMode.rtl, help="Hardware compilation mode"),
    trace_mode: TraceMode = typer.Option(TraceMode.notrace, help="Trace mode"),
    iss_enabled: bool = typer.Option(False, help="Enable ISS comparison"),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (errors only)"
    ),
) -> None:
    """Run a TestHarness testlist with the selected simulator."""
    print_recipe_title(f"{simulator.value.upper()} TESTHARNESS TESTLIST", quiet=quiet)
    print_param_table(
        {
            "Simulator": simulator.value,
            "Target": target,
            "Testlist": testlist,
            "Compilation mode": comp_mode.value,
            "Trace mode": trace_mode.value,
            "ISS comparison": iss_enabled,
        },
        "Options",
        quiet=quiet,
    )

    repo_dir = Path.cwd().resolve()
    require_prerequisite(
        testharness_binary(repo_dir, target, comp_mode),
        f"Verilator TestHarness (comp mode '{comp_mode.value}')",
        f"./cook.py verilator-testharness-comp -t {target} --comp-mode {comp_mode.value}",
    )

    try:
        tests = enabled_tests((repo_dir / testlist).resolve())
    except ValueError as error:
        print_error(str(error), quiet=quiet)
        raise typer.Exit(code=1) from error
    if not tests:
        print_error("No enabled tests in testlist", quiet=quiet)
        raise typer.Exit(code=1)

    print_step("Run testlist", quiet=quiet)
    metric, failed = run_entries(
        tests=tests,
        target=target,
        comp_mode=comp_mode,
        trace_mode=trace_mode,
        iss_enabled=iss_enabled,
        quiet=quiet,
    )
    report = Report()
    report.add_metric(metric)
    output = report_path(repo_dir, target, simulator, testlist)
    report.dump(output)
    print_info(f"Report: {output}", quiet=quiet)
    print_recipe_end("Completed", quiet=quiet)
    if failed:
        raise typer.Exit(code=1)
