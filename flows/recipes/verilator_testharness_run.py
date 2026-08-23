# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
from typing import NamedTuple

import typer
import yaml

from flows.recipes.testharness_common import (
    require_target_files,
    test_simulation_directory,
    validate_path_component,
    verilator_binary,
)
from flows.utils.utils import (
    TraceMode,
    autocompletion_target,
    autocompletion_testname_compiled,
    print_error,
    print_info,
    print_param_table,
    print_recipe_end,
    print_recipe_title,
    print_step,
    print_success,
    tail_file,
)

app = typer.Typer()

BOOT_PC_RE = re.compile(
    r"^\s*\d+\s*\|\s*core\s+\d+:\s*0x0000000080000000\s", re.MULTILINE
)
TANDEM_COMMIT_RE = re.compile(r"^\s*core\s+\d+:", re.MULTILINE)


class TestHarnessResult(NamedTuple):
    name: str
    compiler_isa: str
    mabi: str
    backend: str
    passed: bool
    detail: str


def comparison_report_passed(report: Path) -> tuple[bool, str]:
    if not report.is_file():
        return False, f"missing comparison report: {report}"
    try:
        text = report.read_text(encoding="utf-8")
    except OSError as error:
        return False, f"cannot read comparison report: {error}"

    failures = text.count("[FAILED]")
    if failures:
        return False, f"{failures} failed comparison(s)"

    matched = [
        int(value)
        for value in re.findall(r"\[PASSED\]:\s*([0-9]+)\s+matched\b", text)
    ]
    if matched and all(count > 0 for count in matched):
        return True, f"{sum(matched)} matched instruction(s)"
    if matched:
        return False, "comparison contains a zero-match result"
    return False, "comparison report contains no result"


def testharness_log_passed(log: Path, tandem_enabled: bool) -> tuple[bool, str]:
    if not log.is_file():
        return False, f"missing TestHarness log: {log}"
    try:
        text = log.read_text(encoding="utf-8")
    except OSError as error:
        return False, f"cannot read TestHarness log: {error}"

    failure_markers = (
        "*** FAILED ***",
        "SIMULATION FAILED",
        "[FAILED]",
        "UVM_ERROR",
        "UVM_FATAL",
        "MISMATCH",
    )
    failures = [marker for marker in failure_markers if marker in text]
    if failures:
        return False, "failure marker(s): " + ", ".join(failures)
    for line in text.splitlines():
        normalized = line.lower()
        if "spike_tandem" in normalized and (
            "uvm_warning" in normalized or "mismatch" in normalized
        ):
            return False, "live Spike tandem mismatch"
    if "*** SUCCESS *** (tohost = 0)" not in text:
        return False, "missing successful TestHarness tohost result"

    if tandem_enabled:
        markers = (
            "Running binary in tandem mode",
            "[SPIKE] Starting 'spike_create'...",
        )
        if any(marker not in text for marker in markers):
            return False, "missing live Spike tandem markers"
        return True, "live Spike tandem completed"
    return True, "TestHarness completed"


def tandem_trace_passed(log: Path) -> tuple[bool, str]:
    if not log.is_file():
        return False, f"missing live Spike tandem trace: {log}"
    try:
        text = log.read_text(encoding="utf-8")
    except OSError as error:
        return False, f"cannot read live Spike tandem trace: {error}"
    if not TANDEM_COMMIT_RE.search(text):
        return False, "live Spike tandem trace contains no committed instruction"
    return True, "live Spike tandem trace contains committed instructions"


def boot_pc_reached(log: Path) -> tuple[bool, str]:
    if not log.is_file():
        return False, f"missing disassembled TestHarness trace: {log}"
    try:
        text = log.read_text(encoding="utf-8")
    except OSError as error:
        return False, f"cannot read disassembled TestHarness trace: {error}"
    if not BOOT_PC_RE.search(text):
        return False, "TestHarness trace did not reach boot PC 0x80000000"
    return True, "TestHarness trace reached boot PC 0x80000000"


def _terminate(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def run_logged_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    timeout: int,
) -> tuple[int, bool]:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as output:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            output.write(f"ERROR: {error}\n")
            return 127, False
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            _terminate(process)
            return process.returncode or 124, True


def _runtime_environment(
    repo_dir: Path, target: str, tandem_enabled: bool
) -> tuple[dict[str, str], Path, Path]:
    try:
        riscv = Path(os.environ["RISCV"]).resolve()
    except KeyError as error:
        raise ValueError("RISCV is not set") from error
    spike = Path(
        os.environ.get("SPIKE_INSTALL_DIR", repo_dir / "tools" / "spike")
    ).resolve()

    env = os.environ.copy()
    libraries = [str(spike / "lib"), str(riscv / "lib")]
    if env.get("LD_LIBRARY_PATH"):
        libraries.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = os.pathsep.join(libraries)
    env["CVA6_REPO_DIR"] = str(repo_dir)
    env["TARGET_CFG"] = target
    env["SPIKE_INSTALL_DIR"] = str(spike)
    if tandem_enabled:
        env["SPIKE_TANDEM"] = "1"
    else:
        env.pop("SPIKE_TANDEM", None)
    return env, riscv, spike


def _is_emulator_option(argument: str) -> bool:
    flags = {
        "+cycle-count",
        "+verbose",
        "--cycle-count",
        "--verbose",
    }
    prefixes = (
        "+dump-start=",
        "+max-cycles=",
        "--dump-start=",
        "--max-cycles=",
        "--rbb-port=",
    )
    return argument in flags or argument.startswith(prefixes)


def testharness_command(
    binary: Path,
    elf: Path,
    *,
    target: str,
    spike_yaml: Path,
    tohost: str,
    seed: str,
    trace_mode: TraceMode,
    run_options: list[str],
) -> list[str]:
    command = [str(binary)]
    if trace_mode == TraceMode.fast:
        command.extend(("--vcd", "verilator.vcd"))
    elif trace_mode == TraceMode.compact:
        command.extend(("--fst", "verilator.fst"))
    elif trace_mode != TraceMode.notrace:
        raise ValueError(f"Unsupported Verilator trace mode: {trace_mode.value}")
    emulator_options = [option for option in run_options if _is_emulator_option(option)]
    host_options = [option for option in run_options if not _is_emulator_option(option)]
    command.extend(("--seed", seed))
    command.extend(emulator_options)
    command.append(str(elf))
    command.extend(
        (
            "+tb_performance_mode",
            "+debug_disable=1",
            "+UVM_VERBOSITY=UVM_NONE",
            f"++{elf}",
            f"+elf_file={elf}",
            f"+core_name={target}",
            f"+config_file={spike_yaml}",
            f"+signature={elf}.signature_output",
            "+UVM_TESTNAME=uvmt_cva6_firmware_test_c",
            "+report_file=testharness.log.yaml",
        )
    )
    command.append(f"+tohost_addr={tohost}")
    command.extend(host_options)
    return command


def _run_spike_dasm(
    spike_dasm: Path,
    raw_trace: Path,
    output_log: Path,
    error_log: Path,
    compiler_isa: str,
    timeout: int,
) -> bool:
    if not raw_trace.is_file() or not spike_dasm.is_file():
        return False
    try:
        with (
            raw_trace.open("rb") as source,
            output_log.open("wb") as output,
            error_log.open("wb") as errors,
        ):
            result = subprocess.run(
                [str(spike_dasm), f"--isa={compiler_isa}"],
                stdin=source,
                stdout=output,
                stderr=errors,
                timeout=timeout,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _filter_spike_log(source: Path, output: Path) -> None:
    with source.open("r", encoding="utf-8", errors="replace") as input_file:
        with output.open("w", encoding="utf-8") as output_file:
            for line in input_file:
                if not line.startswith("[") and not line.startswith("/top/"):
                    output_file.write(line)


def _run_standalone_spike(
    *,
    spike: Path,
    elf: Path,
    compiler_isa: str,
    privilege: str,
    spike_yaml: Path,
    simulation_dir: Path,
    env: dict[str, str],
    timeout: int,
) -> tuple[bool, str]:
    raw_log = simulation_dir / "spike.raw.log"
    command = [
        str(spike),
        "--steps=2000000",
        "--log-commits",
        f"--isa={compiler_isa}",
        f"--priv={privilege}",
        "--param-file",
        str(spike_yaml),
        "-l",
        str(elf),
    ]
    return_code, timed_out = run_logged_process(
        command, cwd=simulation_dir, env=env, log=raw_log, timeout=timeout
    )
    if timed_out:
        return False, f"Spike timed out after {timeout} seconds"
    if return_code != 0:
        return False, f"Spike returned {return_code}"
    try:
        _filter_spike_log(raw_log, simulation_dir / "spike.log")
    except OSError as error:
        return False, f"cannot filter Spike log: {error}"
    return True, "Spike completed"


def _postprocess_and_compare(repo_dir: Path, simulation_dir: Path) -> tuple[bool, str]:
    sim_dir = repo_dir / "verif" / "sim"
    scripts_dir = sim_dir / "dv" / "scripts"
    verilator_log = simulation_dir / "verilator.log"
    spike_log = simulation_dir / "spike.log"
    verilator_csv = simulation_dir / "verilator.csv"
    spike_csv = simulation_dir / "spike.csv"
    report = simulation_dir / "iss_regr.log"
    env = os.environ.copy()
    pythonpath = [str(scripts_dir)]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    commands = (
        [
            sys.executable,
            str(sim_dir / "verilator_log_to_trace_csv.py"),
            "--log",
            str(verilator_log),
            "--csv",
            str(verilator_csv),
        ],
        [
            sys.executable,
            str(sim_dir / "cva6_spike_log_to_trace_csv.py"),
            "--log",
            str(spike_log),
            "--csv",
            str(spike_csv),
        ],
        [
            sys.executable,
            str(scripts_dir / "instr_trace_compare.py"),
            "--csv_file_1",
            str(spike_csv),
            "--csv_file_2",
            str(verilator_csv),
            "--csv_name_1",
            "spike",
            "--csv_name_2",
            "verilator",
            "--gpr_update_coalescing_limit",
            "0",
            "--log",
            str(report),
        ],
    )
    for index, command in enumerate(commands):
        return_code, timed_out = run_logged_process(
            command,
            cwd=sim_dir,
            env=env,
            log=simulation_dir / f"postprocess_{index}.log",
            timeout=120,
        )
        if timed_out or return_code != 0:
            return False, f"trace post-processing step {index + 1} failed"
    return comparison_report_passed(report)


def run_test(
    *,
    target: str,
    test_name: str,
    tandem_enabled: bool,
    iss_enabled: bool,
    iss_timeout: int,
    seed: str,
    trace_mode: TraceMode,
    run_options: list[str],
) -> TestHarnessResult:
    repo_dir = Path.cwd().resolve()
    backend = "verilator+spike-tandem" if tandem_enabled else "verilator"
    if iss_enabled and not tandem_enabled:
        backend += "+spike"

    compiler_isa = "unknown"
    mabi = "unknown"
    try:
        target = validate_path_component(target, "target name")
        test_name = validate_path_component(test_name, "test name")
        compile_dir = repo_dir / "build" / target / "compile" / test_name
        elf = compile_dir / f"{test_name}.elf"
        isa_file = compile_dir / "isa_string"
        tohost_file = compile_dir / f"{test_name}.add_tohost"
        simulation_dir = test_simulation_directory(
            repo_dir, target, test_name, tandem_enabled
        )
        binary = verilator_binary(repo_dir, target, tandem_enabled)
        target_dir = require_target_files(repo_dir, target, ("isa.yml", "spike.yaml"))
        spike_yaml = target_dir / "spike.yaml"
        isa_data = yaml.safe_load((target_dir / "isa.yml").read_text(encoding="utf-8"))
        spike_data = yaml.safe_load(spike_yaml.read_text(encoding="utf-8"))
        if not isinstance(isa_data, dict) or not isinstance(spike_data, dict):
            raise ValueError("target ISA and Spike configuration must be mappings")
        mabi = isa_data.get("mabi")
        if not isinstance(mabi, str) or not mabi:
            raise ValueError(f"Missing mabi in {target_dir / 'isa.yml'}")
        spike_parameters = spike_data.get("spike_param_tree")
        if not isinstance(spike_parameters, dict):
            raise ValueError(f"Missing spike_param_tree in {target_dir / 'spike.yaml'}")
        privilege = spike_parameters.get("priv", "MSU")
        if not isinstance(privilege, str) or not privilege:
            raise ValueError("invalid Spike privilege mode")
        if not elf.is_file() or not isa_file.is_file() or not tohost_file.is_file():
            raise ValueError(f"Missing Cook software output for {test_name}")
        if not binary.is_file():
            raise ValueError(f"Missing Verilator executable: {binary}")
        compiler_isa = isa_file.read_text(encoding="utf-8").strip()
        if not compiler_isa:
            raise ValueError(f"Empty compiler ISA in {isa_file}")
        tohost = tohost_file.read_text(encoding="utf-8").strip()
        if not tohost:
            raise ValueError(f"Empty tohost address in {tohost_file}")
        env, _, spike_install = _runtime_environment(
            repo_dir, target, tandem_enabled
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        return TestHarnessResult(
            test_name, compiler_isa, mabi, backend, False, str(error)
        )

    try:
        if simulation_dir.exists():
            shutil.rmtree(simulation_dir)
        simulation_dir.mkdir(parents=True)
    except OSError as error:
        return TestHarnessResult(
            test_name,
            compiler_isa,
            mabi,
            backend,
            False,
            f"cannot prepare output: {error}",
        )
    testharness_log = simulation_dir / "testharness.log"

    command = testharness_command(
        binary,
        elf,
        target=target,
        spike_yaml=spike_yaml,
        tohost=tohost,
        seed=seed,
        trace_mode=trace_mode,
        run_options=run_options,
    )
    return_code, timed_out = run_logged_process(
        command,
        cwd=simulation_dir,
        env=env,
        log=testharness_log,
        timeout=iss_timeout,
    )
    if timed_out:
        detail = f"TestHarness timed out after {iss_timeout} seconds"
        return TestHarnessResult(test_name, compiler_isa, mabi, backend, False, detail)
    if return_code != 0:
        detail = f"TestHarness returned {return_code}"
        return TestHarnessResult(test_name, compiler_isa, mabi, backend, False, detail)

    passed, detail = testharness_log_passed(testharness_log, tandem_enabled)
    if not passed:
        return TestHarnessResult(test_name, compiler_isa, mabi, backend, False, detail)
    if tandem_enabled:
        passed, detail = tandem_trace_passed(simulation_dir / "tandem.log")
        if not passed:
            return TestHarnessResult(
                test_name, compiler_isa, mabi, backend, False, detail
            )

    verilator_log = simulation_dir / "verilator.log"
    if not _run_spike_dasm(
        spike_install / "bin" / "spike-dasm",
        simulation_dir / "trace_rvfi_hart_00.dasm",
        verilator_log,
        simulation_dir / "spike_dasm.log",
        compiler_isa,
        min(iss_timeout, 120),
    ):
        return TestHarnessResult(
            test_name,
            compiler_isa,
            mabi,
            backend,
            False,
            "TestHarness trace disassembly failed",
        )
    passed, detail = boot_pc_reached(verilator_log)
    if not passed:
        return TestHarnessResult(test_name, compiler_isa, mabi, backend, False, detail)

    if iss_enabled and not tandem_enabled:
        passed, detail = _run_standalone_spike(
            spike=spike_install / "bin" / "spike",
            elf=elf,
            compiler_isa=compiler_isa,
            privilege=privilege.lower(),
            spike_yaml=spike_yaml,
            simulation_dir=simulation_dir,
            env=env,
            timeout=iss_timeout,
        )
        if passed:
            passed, detail = _postprocess_and_compare(repo_dir, simulation_dir)
        if not passed:
            return TestHarnessResult(
                test_name, compiler_isa, mabi, backend, False, detail
            )

    return TestHarnessResult(test_name, compiler_isa, mabi, backend, True, detail)


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
    tandem_enabled: bool = typer.Option(
        False,
        "--tandem-enabled/--no-tandem",
        help="Use the TestHarness live Spike tandem build",
    ),
    iss_enabled: bool = typer.Option(
        True,
        "--iss-enabled/--no-iss",
        help="Compare with standalone Spike when tandem mode is disabled",
    ),
    iss_timeout: int = typer.Option(
        500, min=1, help="Timeout in seconds for simulator processes"
    ),
    seed: str = typer.Option("1", "--seed", help="TestHarness random seed"),
    trace_mode: TraceMode = typer.Option(
        TraceMode.notrace, help="Waveform trace format"
    ),
    run_options: list[str] = typer.Option(
        [], "--run-opt", help="Additional TestHarness or SystemVerilog argument"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (errors only)"
    ),
) -> None:
    """Run one Cook-compiled ELF with the Verilator TestHarness."""
    print_recipe_title("VERILATOR TESTHARNESS RUN", quiet=quiet)
    try:
        simulation_dir = test_simulation_directory(
            Path.cwd().resolve(), target, test_name, tandem_enabled
        )
    except ValueError as error:
        print_error(str(error), quiet=quiet)
        raise typer.Exit(code=1) from error
    print_param_table(
        {
            "Target": target,
            "Test": test_name,
            "Tandem enabled": tandem_enabled,
            "Standalone ISS enabled": iss_enabled and not tandem_enabled,
            "Timeout (seconds)": iss_timeout,
            "Seed": seed,
            "Trace mode": trace_mode.value,
        },
        "Options",
        quiet=quiet,
    )
    print_step(f"Run {test_name}", quiet=quiet)
    result = run_test(
        target=target,
        test_name=test_name,
        tandem_enabled=tandem_enabled,
        iss_enabled=iss_enabled,
        iss_timeout=iss_timeout,
        seed=seed,
        trace_mode=trace_mode,
        run_options=run_options,
    )
    if not quiet and (simulation_dir / "testharness.log").is_file():
        tail_file(simulation_dir / "testharness.log", n=20)
    if result.passed:
        print_success(f"{test_name}: PASS ({result.detail})", quiet=quiet)
    else:
        print_error(f"{test_name}: FAIL ({result.detail})", quiet=quiet)
    print_info(f"Results: {simulation_dir}", quiet=quiet)
    print_recipe_end("Completed", quiet=quiet)
    if not result.passed:
        raise typer.Exit(code=1)
