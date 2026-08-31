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

from flows.recipes.testharness_common import (
    TestHarnessRunner,
    validate_iss_options,
    validate_path_component,
    validate_verilator_options,
)
from flows.recipes.verilator_testharness_run import run_test as run_verilator_test
from flows.utils.report_builder import Report, TableStatusMetric
from flows.utils.utils import (
    CompMode,
    TraceMode,
    autocompletion_target,
    autocompletion_testlist,
    autocompletion_testname_in_testlist,
    print_error,
    print_param_table,
    print_recipe_end,
    print_recipe_title,
    print_step,
    print_success,
)

app = typer.Typer()


class Simulator(str, Enum):
    verilator = "verilator"


RUNNERS: dict[Simulator, TestHarnessRunner] = {
    Simulator.verilator: run_verilator_test
}


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
        test_name = validate_path_component(entry["test"], "test name")
        try:
            iterations = int(entry.get("iterations", 1))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid iterations for test {test_name}") from error
        if iterations < 0:
            raise ValueError(f"Negative iterations for test {test_name}")
        if iterations:
            tests.append({**entry, "test": test_name, "iterations": iterations})

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
    comp_mode: CompMode = typer.Option(
        CompMode.rtl, help="Hardware compilation mode (currently rtl only)"
    ),
    trace_mode: TraceMode = typer.Option(
        TraceMode.notrace, help="Trace mode (Verilator gui is not supported)"
    ),
    tandem_enabled: bool = typer.Option(
        False,
        "--tandem-enabled/--no-tandem",
        help="Use live Spike tandem mode",
    ),
    iss_enabled: bool = typer.Option(
        False,
        "--iss-enabled/--no-iss",
        help="Enable ISS (required for tandem; standalone comparison otherwise)",
    ),
    iss_timeout: int = typer.Option(
        500, min=1, help="Timeout in seconds for each simulator process"
    ),
    seed: str = typer.Option("1", "--seed", help="TestHarness random seed"),
    emulator_options: list[str] = typer.Option(
        [],
        "--emulator-opt",
        help="Backend emulator option placed before the ELF",
    ),
    run_options: list[str] = typer.Option(
        [],
        "--run-opt",
        help="Verilog plusarg or HTIF/host argument placed after the ELF",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress command output and summaries"
    ),
) -> None:
    """Run enabled Cook-compiled tests with a TestHarness simulator backend."""
    print_recipe_title(
        f"{simulator.value.upper()} TESTHARNESS TESTLIST", quiet=quiet
    )
    repo_dir = Path.cwd().resolve()
    testlist_file = (repo_dir / testlist).resolve()
    try:
        target = validate_path_component(target, "target name")
        if simulator == Simulator.verilator:
            validate_verilator_options(
                comp_mode=comp_mode, trace_mode=trace_mode
            )
        validate_iss_options(
            iss_enabled=iss_enabled, tandem_enabled=tandem_enabled
        )
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
            "Compilation mode": comp_mode.value,
            "Trace mode": trace_mode.value,
            "Tandem enabled": tandem_enabled,
            "Standalone ISS enabled": iss_enabled and not tandem_enabled,
            "Timeout (seconds)": iss_timeout,
            "Seed": seed,
        },
        "Options",
        quiet=quiet,
    )

    try:
        run_test = RUNNERS[simulator]
    except KeyError as error:
        print_error(
            f"Unsupported TestHarness simulator: {simulator.value}", quiet=quiet
        )
        raise typer.Exit(code=1) from error

    metric = TableStatusMetric("TestHarness test results")
    metric.add_column("Target", "text")
    metric.add_column("Test", "text")
    metric.add_column("Compilation mode", "text")
    metric.add_column("Compiler ISA", "text")
    metric.add_column("ABI", "text")
    metric.add_column("Simulator", "text")
    metric.add_column("Backend", "text")
    metric.add_column("Detail", "text")

    failed = False
    for test in tests:
        for iteration in range(test["iterations"]):
            compiled_name = f"{test['test']}_{iteration}"
            print_step(f"Run {compiled_name}", quiet=quiet)
            result = run_test(
                target=target,
                test_name=compiled_name,
                comp_mode=comp_mode,
                trace_mode=trace_mode,
                tandem_enabled=tandem_enabled,
                iss_enabled=iss_enabled,
                iss_timeout=iss_timeout,
                seed=seed,
                emulator_options=emulator_options,
                run_options=run_options,
            )
            row = (
                target,
                result.name,
                comp_mode.value,
                result.compiler_isa,
                result.mabi,
                simulator.value,
                result.backend,
                result.detail,
            )
            if result.passed:
                metric.add_pass(*row)
                print_success(
                    f"{result.name}: PASS ({result.detail})", quiet=quiet
                )
            else:
                metric.add_fail(*row)
                print_error(f"{result.name}: FAIL ({result.detail})", quiet=quiet)
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
