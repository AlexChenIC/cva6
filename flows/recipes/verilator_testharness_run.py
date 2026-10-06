# Copyright 2026 OpenHW Foundation
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/
#
# Original Author: Junchao Chen (junchao.chen@eclipse-foundation.org)

# Please refer to flows/README.md to add target

"""
Run one test on the Verilator TestHarness.

Require a normal process exit and successful tohost. In live mode the native
RVFI report must additionally show nonzero comparisons and zero mismatches.
"""

from pathlib import Path
import re
import shutil
import stat

import yaml

import typer

from flows.utils.autocompletion import (
    CompMode,
    TraceMode,
    autocompletion_target,
    autocompletion_testname_compiled,
)
from flows.utils.manifest import (
    get_manifest_option,
    read_manifest,
    require_manifest_option,
    require_prerequisite,
    write_manifest,
)
from flows.utils.recipe_report import RecipeReport
from flows.utils.testharness import run_test, simulation_directory, read_tandem_report

app = typer.Typer()

# Wall clock limit of one run. The harness stops on tohost; a test that
# derails never writes it and would otherwise hold the pipeline.
SIMULATION_TIMEOUT = 500


# ==========================================================
# RECIPE
# ==========================================================


@app.command()
def verilator_testharness_run(
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="CVA6 user configuration",
        autocompletion=autocompletion_target,
    ),
    test_name: str = typer.Option(
        ...,
        "--testname",
        "-n",
        help="Cook-compiled test name",
        autocompletion=autocompletion_testname_compiled,
    ),
    comp_mode: CompMode = typer.Option(
        CompMode.rtl, help="Compilation mode; only rtl is supported"
    ),
    trace_mode: TraceMode = typer.Option(
        TraceMode.notrace,
        help="notrace, fast (VCD), or compact (FST); must match the build",
    ),
    interactive_gui: bool = typer.Option(
        False, help="Interactive GUI is currently unsupported"
    ),
    sim_timeout: int = typer.Option(
        SIMULATION_TIMEOUT, "--sim-timeout", help="Simulation timeout in seconds"
    ),
    run_name: str = typer.Option(
        None,
        "--run-name",
        help="Name of the output directory, when the same test is run more "
        "than once on the same design (default: the test name)",
    ),
    tandem_enabled: bool = typer.Option(
        False, help="Require native live Spike/RVFI comparison"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (errors only)"
    ),
):
    """Run one ELF; require native zero-mismatch evidence in live mode."""
    report = RecipeReport(
        "verilator-testharness-run",
        title="VERILATOR TESTHARNESS RUN",
        context=dict(
            target=target,
            test_name=test_name,
            comp_mode=comp_mode,
            trace_mode=trace_mode,
            interactive_gui=interactive_gui,
            sim_timeout=sim_timeout,
            run_name=run_name,
            tandem_enabled=tandem_enabled,
        ),
        quiet=quiet,
    )
    try:
        directory = simulation_directory(
            Path.cwd(), target, run_name or test_name, comp_mode, tandem_enabled
        )
        report.set_out_dir(directory)
        if type(sim_timeout) is not int or sim_timeout < 1:
            report.error_exit("sim_timeout must be a positive integer", env=True)
        report.step(f"Run {test_name}")
        passed, detail, directory = run_test(
            target=target,
            test_name=test_name,
            comp_mode=comp_mode,
            trace_mode=trace_mode,
            interactive_gui=interactive_gui,
            iss_enabled=False,
            timeout=sim_timeout,
            tandem_enabled=tandem_enabled,
            run_name=run_name,
        )
        if passed:
            report.success(f"{test_name}: {detail}")
            if tandem_enabled:
                native = read_tandem_report(directory / "testharness.log.yaml")
                report.metric(
                    "Live tandem",
                    {
                        k: native[k]
                        for k in ("instr_count", "csrs_match_count", "mismatches_count")
                    },
                )
            text = (directory / "testharness.log").read_text(errors="replace")
            cycles = re.search(r"after (\d+) cycles", text)
            if cycles:
                report.set_label(f"{int(cycles.group(1)) / 1000:.2f} kCycles")
        else:
            report.error(f"{test_name}: {detail}")
        options = dict(
            target=target,
            test_name=test_name,
            comp_mode=comp_mode.value,
            trace_mode=trace_mode.value,
            interactive_gui=interactive_gui,
            run_name=run_name,
            sim_timeout=sim_timeout,
            tandem_enabled=tandem_enabled,
        )
        write_manifest(directory, "verilator-testharness-run", options, report=report)
        manifest = read_manifest(directory, report)
        if not isinstance(manifest, dict) or manifest.get("options") != options:
            report.error_exit("Run manifest was not written correctly", env=True)
        (directory / "result.yml").write_text(
            yaml.safe_dump(
                dict(
                    target=target,
                    test_name=test_name,
                    status="PASS" if passed else "FAIL",
                    iss_enabled=False,
                    tandem_enabled=tandem_enabled,
                    detail=detail,
                )
            )
        )
        report.log(
            "Generated files", [str(p) for p in directory.iterdir() if p.is_file()]
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        report.error_exit(str(error), env=True)
    report.end("Completed")
