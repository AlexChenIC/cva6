# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import typer
import yaml

from flows.recipes.verilator_testharness_run import run_test
from flows.utils.report_builder import Report, TableStatusMetric
from flows.utils.utils import (
    TraceMode,
    autocompletion_target,
    autocompletion_testlist,
    autocompletion_testname_in_testlist,
    print_error,
    print_param_table,
    print_recipe_end,
    print_recipe_title,
)

app = typer.Typer()


class Simulator(str, Enum):
    verilator = "verilator"


def enabled_tests(
    data: dict[str, Any], selected: list[str] | None
) -> list[dict[str, Any]]:
    entries = data.get("testlist")
    if not isinstance(entries, list):
        raise ValueError("testlist must contain a list named 'testlist'")

    tests = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("test"), str):
            raise ValueError(f"Invalid test entry at index {index}")
        try:
            iterations = int(entry.get("iterations", 1))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid iterations for test {entry['test']}") from error
        if iterations < 0:
            raise ValueError(f"Negative iterations for test {entry['test']}")
        if iterations:
            tests.append({**entry, "iterations": iterations})

    if selected:
        requested = set(selected)
        available = {entry["test"] for entry in tests}
        unknown = sorted(requested - available)
        if unknown:
            raise ValueError("Unknown or disabled tests: " + ", ".join(unknown))
        tests = [entry for entry in tests if entry["test"] in requested]
    return tests


@app.command()
def testharness_run_testlist(
    simulator: Simulator = typer.Option(
        ...,
        "--simulator",
        "-s",
        help="TestHarness simulator backend",
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
        help="Testlist YAML compiled by sw-compile-testlist",
        autocompletion=autocompletion_testlist,
    ),
    test_name: list[str] | None = typer.Option(
        None,
        "--testname",
        "-n",
        help="Run selected enabled tests from the testlist",
        autocompletion=autocompletion_testname_in_testlist,
    ),
    tandem_enabled: bool = typer.Option(
        False,
        "--tandem-enabled/--no-tandem",
        help="Use live Spike tandem mode",
    ),
    iss_enabled: bool = typer.Option(
        True,
        "--iss-enabled/--no-iss",
        help="Compare with a standalone ISS when tandem mode is disabled",
    ),
    iss_timeout: int = typer.Option(
        500, min=1, help="Timeout in seconds for each simulator process"
    ),
    seed: str = typer.Option("1", "--seed", help="TestHarness random seed"),
    trace_mode: TraceMode = typer.Option(
        TraceMode.notrace, help="Waveform trace format"
    ),
    run_options: list[str] = typer.Option(
        [], "--run-opt", help="Additional TestHarness argument"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress command output and summaries"
    ),
) -> None:
    print_recipe_title(
        f"{simulator.value.upper()} TESTHARNESS TESTLIST", quiet=quiet
    )
    repo_dir = Path.cwd().resolve()
    testlist_file = (repo_dir / testlist).resolve()
    try:
        data = yaml.safe_load(testlist_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Expected a mapping in {testlist_file}")
        tests = enabled_tests(data, test_name)
        if not tests:
            raise ValueError("No enabled tests selected")
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        print_error(str(error), quiet=quiet)
        raise typer.Exit(code=1) from error

    print_param_table(
        {
            "Simulator": simulator.value,
            "Target": target,
            "Testlist": testlist,
            "Selected tests": test_name or "all enabled tests",
            "Tandem enabled": tandem_enabled,
            "Standalone ISS enabled": iss_enabled and not tandem_enabled,
            "Timeout (seconds)": iss_timeout,
            "Seed": seed,
            "Trace mode": trace_mode.value,
        },
        "Options",
        quiet=quiet,
    )

    metric = TableStatusMetric("TestHarness test results")
    metric.add_column("Target", "text")
    metric.add_column("Test", "text")
    metric.add_column("Compiler ISA", "text")
    metric.add_column("ABI", "text")
    metric.add_column("Simulator", "text")
    metric.add_column("Backend", "text")

    failed = False
    for test in tests:
        for iteration in range(test["iterations"]):
            compiled_name = f"{test['test']}_{iteration}"
            result = run_test(
                target=target,
                test_name=compiled_name,
                tandem_enabled=tandem_enabled,
                iss_enabled=iss_enabled,
                iss_timeout=iss_timeout,
                seed=seed,
                trace_mode=trace_mode,
                run_options=run_options,
            )
            row = (
                target,
                result.name,
                result.compiler_isa,
                result.mabi,
                simulator.value,
                result.backend,
            )
            if result.passed:
                metric.add_pass(*row)
            else:
                metric.add_fail(*row)
                print_error(f"{result.name}: {result.detail}", quiet=quiet)
                failed = True

    report = Report()
    report.add_metric(metric)
    report_path = (
        repo_dir
        / "artifacts"
        / "reports"
        / f"report_testharness_{simulator.value}_{target}_{testlist_file.stem}.yml"
    )
    report.dump(str(report_path.relative_to(repo_dir)))
    print_recipe_end("Completed", quiet=quiet)
    if failed:
        raise typer.Exit(code=1)
