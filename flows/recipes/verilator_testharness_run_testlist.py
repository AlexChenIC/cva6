# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Run cook-compiled testlists with the public Verilator TestHarness flow."""

import os
from pathlib import Path
import subprocess
import sys

import typer
import yaml

from flows.utils.report_builder import Report, TableStatusMetric
from flows.utils.utils import (
    autocompletion_target,
    autocompletion_testlist,
    autocompletion_testname_in_testlist,
    print_error,
    print_recipe_end,
    print_recipe_title,
    print_success,
)


app = typer.Typer()


def run_streaming(command: list[str], cwd: Path, env: dict[str, str], log: Path) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log_file.write(line)
        return process.wait()


@app.command()
def verilator_testharness_run_testlist(
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
    test_name: list[str] = typer.Option(
        None,
        "--testname",
        "-n",
        help="Run only selected tests from the testlist",
        autocompletion=autocompletion_testname_in_testlist,
    ),
    tandem_enabled: bool = typer.Option(
        True, "--tandem-enabled/--no-tandem", help="Enable Spike tandem mode"
    ),
    iss_timeout: int = typer.Option(
        30000, help="Timeout passed to the TestHarness execution backend"
    ),
    uvm_seed: str = typer.Option("1", help="Deterministic TestHarness seed"),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress recipe summary output"
    ),
):
    """Run precompiled ELF tests through Verilator TestHarness and Spike."""
    print_recipe_title("VERILATOR TESTHARNESS TESTLIST", quiet=quiet)

    repo_dir = Path.cwd().resolve()
    target_dir = repo_dir / "config" / "target" / target
    testlist_file = (repo_dir / testlist).resolve()
    isa_file = target_dir / "isa.yml"
    spike_file = target_dir / "spike.yaml"
    linker_file = target_dir / "link.ld"

    required_files = [testlist_file, isa_file, spike_file, linker_file]
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        for path in missing:
            print_error(f"Missing required file: {path}", quiet=quiet)
        raise typer.Exit(code=1)

    testlist_data = yaml.safe_load(testlist_file.read_text(encoding="utf-8"))
    isa_data = yaml.safe_load(isa_file.read_text(encoding="utf-8"))
    spike_data = yaml.safe_load(spike_file.read_text(encoding="utf-8"))
    tests = testlist_data.get("testlist", [])
    if test_name:
        selected_names = set(test_name)
        tests = [test for test in tests if test["test"] in selected_names]
    tests = [test for test in tests if test.get("iterations", 1) > 0]

    if not tests:
        print_error("No enabled tests selected", quiet=quiet)
        raise typer.Exit(code=1)

    build_root = repo_dir / "build" / target
    simulation_root = (
        build_root / "simulation" / "sim_verilator_testharness"
    )
    result_metric = TableStatusMetric("Verilator TestHarness test results")
    result_metric.add_column("Target", "text")
    result_metric.add_column("Test", "text")
    result_metric.add_column("ISA", "text")
    result_metric.add_column("Backend", "text")
    code = 0

    privilege = (
        spike_data.get("spike_param_tree", {}).get("priv", "MSU").lower()
    )
    env = os.environ.copy()
    if tandem_enabled:
        env["SPIKE_TANDEM"] = "1"
    else:
        env.pop("SPIKE_TANDEM", None)

    for test in tests:
        for iteration in range(test.get("iterations", 1)):
            compiled_name = f"{test['test']}_{iteration}"
            compile_dir = build_root / "compile" / compiled_name
            elf_file = compile_dir / f"{compiled_name}.elf"
            isa_string_file = compile_dir / "isa_string"
            simulation_dir = simulation_root / compiled_name
            run_log = simulation_dir / "cook_testharness.log"

            if not elf_file.is_file() or not isa_string_file.is_file():
                print_error(
                    f"Missing cook compilation output for {compiled_name}",
                    quiet=quiet,
                )
                result_metric.add_fail(
                    target, compiled_name, "unknown", "veri-testharness,spike"
                )
                code = 1
                continue

            effective_isa = isa_string_file.read_text(encoding="utf-8").strip()
            command = [
                sys.executable,
                "cva6.py",
                "--target",
                target,
                "--custom_target",
                str(target_dir),
                "--isa",
                effective_isa,
                "--mabi",
                isa_data["mabi"],
                "--elf_tests",
                str(elf_file),
                "--iss_yaml",
                str(repo_dir / "verif" / "sim" / "cva6.yaml"),
                "--iss",
                "veri-testharness,spike",
                "--iss_timeout",
                str(iss_timeout),
                "--issrun_opts=+tb_performance_mode+debug_disable=1+UVM_VERBOSITY=UVM_NONE",
                "--sv_seed",
                uvm_seed,
                "--priv",
                privilege,
                "--linker",
                str(linker_file),
                "--spike_yaml",
                str(spike_file),
                "--output",
                str(simulation_dir),
            ]
            return_code = run_streaming(
                command, repo_dir / "verif" / "sim", env, run_log
            )
            if return_code == 0:
                print_success(f"{compiled_name}: PASS", quiet=quiet)
                result_metric.add_pass(
                    target,
                    compiled_name,
                    effective_isa,
                    "veri-testharness,spike",
                )
            else:
                print_error(
                    f"{compiled_name}: FAIL ({return_code})", quiet=quiet
                )
                result_metric.add_fail(
                    target,
                    compiled_name,
                    effective_isa,
                    "veri-testharness,spike",
                )
                code = 1

    report = Report()
    report.add_metric(result_metric)
    report_path = (
        repo_dir
        / "artifacts"
        / "reports"
        / f"report_github_actions_{target}_{testlist_file.stem}.yml"
    )
    report.dump(str(report_path.relative_to(repo_dir)))
    print_recipe_end("Completed", quiet=quiet)

    if code != 0:
        raise typer.Exit(code=1)
