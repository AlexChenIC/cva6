# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import typer
import yaml

from flows.recipes.verilator_testharness_comp import (
    build_directory,
    elaboration_directory,
    testharness_binary,
    target_directory,
    validate_options,
)
from flows.utils.manifest import (
    MANIFEST_NAME,
    read_manifest,
    require_manifest_option,
    require_prerequisite,
    write_manifest,
)
from flows.utils.logged_process import run_logged_process
from flows.utils.utils import (
    CompMode,
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

SIMULATION_TIMEOUT = 500
BOOT_PC_RE = re.compile(
    r"^\s*\d+\s*\|\s*core\s+\d+:\s*0x0000000080000000\s", re.MULTILINE
)


def validate_path_component(value: str, label: str) -> str:
    if value in {"", ".", ".."} or Path(value).name != value:
        raise ValueError(f"Invalid {label}: {value}")
    return value


def validate_run_options(
    comp_mode: CompMode, trace_mode: TraceMode, interactive_gui: bool
) -> None:
    validate_options(comp_mode, trace_mode, stats=False)
    if interactive_gui:
        raise ValueError(
            "Interactive GUI is not supported by the Verilator TestHarness recipe"
        )


def simulation_directory(
    repo_dir: Path, target: str, test_name: str, comp_mode: CompMode
) -> Path:
    target = validate_path_component(target, "target name")
    test_name = validate_path_component(test_name, "test name")
    return build_directory(
        repo_dir,
        target,
        "simulation",
        f"sim_{comp_mode.value}_verilator_testharness",
        test_name,
    )


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
        int(value) for value in re.findall(r"\[PASSED\]:\s*([0-9]+)\s+matched\b", text)
    ]
    if matched and all(count > 0 for count in matched):
        return True, f"{sum(matched)} matched instruction(s)"
    if matched:
        return False, "comparison contains a zero-match result"
    return False, "comparison report contains no result"


def testharness_log_passed(log: Path) -> tuple[bool, str]:
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
    )
    failures = [marker for marker in failure_markers if marker in text]
    if failures:
        return False, "failure marker(s): " + ", ".join(failures)
    if "*** SUCCESS *** (tohost = 0)" not in text:
        return False, "missing successful TestHarness tohost result"
    return True, "TestHarness completed"


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


def runtime_environment(repo_dir: Path, target: str) -> tuple[dict[str, str], Path]:
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
    env.pop("SPIKE_TANDEM", None)
    return env, spike


def testharness_command(
    binary: Path,
    elf: Path,
    *,
    target: str,
    spike_yaml: Path | None,
    tohost: str,
    trace_mode: TraceMode,
) -> list[str]:
    command = [str(binary)]
    if trace_mode == TraceMode.fast:
        command.extend(("--vcd", "verilator.vcd"))
    elif trace_mode == TraceMode.compact:
        command.extend(("--fst", "verilator.fst"))
    elif trace_mode != TraceMode.notrace:
        raise ValueError(f"Unsupported Verilator trace mode: {trace_mode.value}")
    command.extend(("--seed", "1", str(elf)))
    command.extend(
        (
            "+tb_performance_mode",
            "+debug_disable=1",
            "+UVM_VERBOSITY=UVM_NONE",
            f"++{elf}",
            f"+elf_file={elf}",
            f"+core_name={target}",
            "+signature=signature_output",
            "+UVM_TESTNAME=uvmt_cva6_firmware_test_c",
            "+report_file=testharness.log.yaml",
            f"+tohost_addr={tohost}",
        )
    )
    if spike_yaml is not None:
        command.append(f"+config_file={spike_yaml}")
    return command


def run_spike_dasm(
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


def filter_spike_log(source: Path, output: Path) -> None:
    with source.open("r", encoding="utf-8", errors="replace") as input_file:
        with output.open("w", encoding="utf-8") as output_file:
            for line in input_file:
                if not line.startswith("[") and not line.startswith("/top/"):
                    output_file.write(line)


def run_standalone_spike(
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
        # Spike's generated DTB hardcodes generic PMP settings. Keep the
        # target-specific spike.yaml parameters authoritative instead.
        "--disable-dtb",
        "--param-file",
        str(spike_yaml),
        "-l",
        str(elf),
    ]
    return_code, timed_out = run_logged_process(
        command,
        cwd=simulation_dir,
        env=env,
        log=raw_log,
        timeout=timeout,
    )
    if timed_out:
        return False, f"Spike timed out after {timeout} seconds"
    if return_code != 0:
        return False, f"Spike returned {return_code}"
    try:
        filter_spike_log(raw_log, simulation_dir / "spike.log")
    except OSError as error:
        return False, f"cannot filter Spike log: {error}"
    return True, "Spike completed"


def postprocess_and_compare(repo_dir: Path, simulation_dir: Path) -> tuple[bool, str]:
    sim_dir = repo_dir / "verif" / "sim"
    scripts_dir = sim_dir / "dv" / "scripts"
    verilator_csv = simulation_dir / "verilator.csv"
    spike_csv = simulation_dir / "spike.csv"
    report = simulation_dir / "iss_regr.log"
    # Reuse the repository's trace parsers as libraries, as the UVM recipes
    # do with report utilities. Their historical imports need this search path.
    original_path = sys.path.copy()
    try:
        sys.path[:0] = [str(scripts_dir), str(sim_dir)]
        modules = []
        for path in (
            sim_dir / "verilator_log_to_trace_csv.py",
            sim_dir / "cva6_spike_log_to_trace_csv.py",
            scripts_dir / "instr_trace_compare.py",
        ):
            spec = importlib.util.spec_from_file_location(
                f"_testharness_{path.stem}", path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        report.unlink(missing_ok=True)
        with (
            (simulation_dir / "postprocess.log").open("w", encoding="utf-8") as log,
            redirect_stdout(log),
            redirect_stderr(log),
        ):
            verilator_count = modules[0].process_verilator_sim_log(
                str(simulation_dir / "verilator.log"), str(verilator_csv)
            )
            spike_count = modules[1].process_spike_sim_log(
                str(simulation_dir / "spike.log"), str(spike_csv)
            )
            if not verilator_count or not spike_count:
                return False, "trace comparison requires nonempty RTL and Spike traces"
            modules[2].compare_trace_csv(
                str(spike_csv),
                str(verilator_csv),
                "spike",
                "verilator",
                str(report),
                coalescing_limit=0,
            )
    except (OSError, ImportError, ValueError, IndexError) as error:
        return False, f"trace post-processing failed: {error}"
    finally:
        sys.path[:] = original_path
    return comparison_report_passed(report)


def target_configuration(
    target_dir: Path, iss_enabled: bool
) -> tuple[Path | None, str]:
    spike_yaml = target_dir / "spike.yaml"
    if not iss_enabled:
        return None, "msu"
    if not spike_yaml.is_file():
        raise ValueError(
            f"ISS comparison requires a target Spike configuration: {spike_yaml}; use --no-iss-enabled for RTL-only execution"
        )
    spike_data = yaml.safe_load(spike_yaml.read_text(encoding="utf-8"))
    if not isinstance(spike_data, dict):
        raise ValueError("target Spike configuration must be a mapping")
    spike_parameters = spike_data.get("spike_param_tree")
    if not isinstance(spike_parameters, dict):
        raise ValueError(f"Missing spike_param_tree in {spike_yaml}")
    privilege = spike_parameters.get("priv", "MSU")
    if not isinstance(privilege, str) or privilege.lower() not in {"m", "mu", "msu"}:
        raise ValueError("invalid Spike privilege mode")
    return spike_yaml, privilege.lower()


def check_manifests(
    *,
    target: str,
    test_name: str,
    comp_mode: CompMode,
    trace_mode: TraceMode,
    compile_dir: Path,
    elab_dir: Path,
) -> None:
    software_manifest = read_manifest(compile_dir)
    for directory in (compile_dir, elab_dir):
        manifest = read_manifest(directory)
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("options"), dict
        ):
            raise ValueError(
                f"Missing or malformed Cook manifest: {directory / MANIFEST_NAME}; compile the prerequisite again"
            )
    require_manifest_option(
        software_manifest,
        "target",
        [target],
        "compiled software target does not match the requested target",
        f"./cook.py sw-compile -t {target} -c <toolchain> --out {test_name} <sources>",
        manifest_dir=compile_dir,
    )
    require_manifest_option(
        software_manifest,
        "test_name",
        [test_name],
        "compiled software name does not match the requested test",
        f"./cook.py sw-compile -t {target} -c <toolchain> --out {test_name} <sources>",
        manifest_dir=compile_dir,
    )

    hardware_manifest = read_manifest(elab_dir)
    if hardware_manifest.get("recipe") != "verilator-testharness-comp":
        raise ValueError("Hardware must be produced by verilator-testharness-comp")
    require_manifest_option(
        hardware_manifest,
        "target",
        [target],
        "TestHarness target does not match the requested target",
        f"./cook.py verilator-testharness-comp -t {target}",
        manifest_dir=elab_dir,
    )
    require_manifest_option(
        hardware_manifest,
        "comp_mode",
        [comp_mode.value],
        "TestHarness compilation mode does not match the requested mode",
        f"./cook.py verilator-testharness-comp -t {target} --comp-mode {comp_mode.value}",
        manifest_dir=elab_dir,
    )
    if trace_mode != TraceMode.notrace:
        require_manifest_option(
            hardware_manifest,
            "trace_mode",
            [trace_mode.value],
            f"trace mode '{trace_mode.value}' requires a matching TestHarness build",
            f"./cook.py verilator-testharness-comp -t {target} --trace-mode {trace_mode.value}",
            manifest_dir=elab_dir,
        )


def run_testharness_and_trace(
    *,
    command: list[str],
    output_dir: Path,
    env: dict[str, str],
    spike_install: Path,
    compiler_isa: str,
    timeout: int,
) -> tuple[bool, str]:
    testharness_log = output_dir / "testharness.log"
    return_code, timed_out = run_logged_process(
        command,
        cwd=output_dir,
        env=env,
        log=testharness_log,
        timeout=timeout,
    )
    if timed_out:
        return False, f"TestHarness timed out after {timeout} seconds"
    if return_code != 0:
        return False, f"TestHarness returned {return_code}"

    passed, detail = testharness_log_passed(testharness_log)
    if not passed:
        return False, detail

    verilator_log = output_dir / "verilator.log"
    if not run_spike_dasm(
        spike_install / "bin" / "spike-dasm",
        output_dir / "trace_rvfi_hart_00.dasm",
        verilator_log,
        output_dir / "spike_dasm.log",
        compiler_isa,
        min(timeout, 120),
    ):
        return False, "TestHarness trace disassembly failed"
    trace_passed, trace_detail = boot_pc_reached(verilator_log)
    if not trace_passed:
        return False, trace_detail
    return True, f"{detail}; {trace_detail}"


def run_test(
    *,
    target: str,
    test_name: str,
    comp_mode: CompMode,
    trace_mode: TraceMode,
    iss_enabled: bool,
    interactive_gui: bool,
    timeout: int = SIMULATION_TIMEOUT,
) -> tuple[bool, str, Path]:
    repo_dir = Path.cwd().resolve()
    validate_run_options(comp_mode, trace_mode, interactive_gui)
    target = validate_path_component(target, "target name")
    test_name = validate_path_component(test_name, "test name")

    target_dir = target_directory(repo_dir, target)
    spike_yaml, privilege = target_configuration(target_dir, iss_enabled)
    compile_dir = repo_dir / "build" / target / "compile" / test_name
    elab_dir = elaboration_directory(repo_dir, target, comp_mode)
    output_dir = simulation_directory(repo_dir, target, test_name, comp_mode)
    elf = compile_dir / f"{test_name}.elf"
    isa_file = compile_dir / "isa_string"
    tohost_file = compile_dir / f"{test_name}.add_tohost"
    binary = testharness_binary(repo_dir, target, comp_mode)

    require_prerequisite(
        elf,
        f"compiled software for test '{test_name}'",
        f"./cook.py sw-compile -t {target} -c <toolchain> --out {test_name} <sources>",
    )
    require_prerequisite(
        isa_file,
        f"compiler ISA for test '{test_name}'",
        f"./cook.py sw-compile -t {target} -c <toolchain> --out {test_name} <sources>",
    )
    require_prerequisite(
        tohost_file,
        f"tohost address for test '{test_name}'",
        f"./cook.py sw-compile -t {target} -c <toolchain> --out {test_name} <sources>",
    )
    require_prerequisite(
        binary,
        f"Verilator TestHarness (comp mode '{comp_mode.value}')",
        f"./cook.py verilator-testharness-comp -t {target} --comp-mode {comp_mode.value}",
    )
    check_manifests(
        target=target,
        test_name=test_name,
        comp_mode=comp_mode,
        trace_mode=trace_mode,
        compile_dir=compile_dir,
        elab_dir=elab_dir,
    )

    compiler_isa = isa_file.read_text(encoding="utf-8").strip()
    tohost = tohost_file.read_text(encoding="utf-8").strip()
    if not compiler_isa:
        raise ValueError(f"Empty compiler ISA in {isa_file}")
    if not re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]+", tohost) or int(tohost, 16) == 0:
        raise ValueError(f"Invalid or zero tohost address in {tohost_file}")
    if not os.access(binary, os.X_OK):
        raise ValueError(f"TestHarness is not executable: {binary}")
    env, spike_install = runtime_environment(repo_dir, target)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    command = testharness_command(
        binary,
        elf,
        target=target,
        spike_yaml=spike_yaml,
        tohost=tohost,
        trace_mode=trace_mode,
    )
    passed, detail = run_testharness_and_trace(
        command=command,
        output_dir=output_dir,
        env=env,
        spike_install=spike_install,
        compiler_isa=compiler_isa,
        timeout=timeout,
    )
    if not passed:
        return False, detail, output_dir
    evidence = [detail]

    if iss_enabled:
        passed, detail = run_standalone_spike(
            spike=spike_install / "bin" / "spike",
            elf=elf,
            compiler_isa=compiler_isa,
            privilege=privilege,
            spike_yaml=spike_yaml,
            simulation_dir=output_dir,
            env=env,
            timeout=timeout,
        )
        if passed:
            evidence.append(detail)
            passed, detail = postprocess_and_compare(repo_dir, output_dir)
        if not passed:
            return False, detail, output_dir
        evidence.append(detail)

    return True, "; ".join(evidence), output_dir


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
    iss_enabled: bool = typer.Option(
        False, help="Compare against standalone Spike; requires target spike.yaml"
    ),
    interactive_gui: bool = typer.Option(
        False, help="Interactive GUI is currently unsupported"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (errors only)"
    ),
) -> None:
    """Verilator TestHarness run simulation flow."""
    print_recipe_title("VERILATOR TESTHARNESS RUN", quiet=quiet)
    print_param_table(
        {
            "Target": target,
            "Test": test_name,
            "Compilation mode": comp_mode.value,
            "Trace mode": trace_mode.value,
            "ISS comparison": iss_enabled,
            "Interactive GUI": interactive_gui,
        },
        "Options",
        quiet=quiet,
    )
    print_step(f"Run {test_name}", quiet=quiet)

    try:
        passed, detail, output_dir = run_test(
            target=target,
            test_name=test_name,
            comp_mode=comp_mode,
            trace_mode=trace_mode,
            iss_enabled=iss_enabled,
            interactive_gui=interactive_gui,
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
        print_error(str(error))
        raise typer.Exit(code=1) from error

    if (not quiet or not passed) and (output_dir / "testharness.log").is_file():
        tail_file(output_dir / "testharness.log", n=20)
    options = {
        "target": target,
        "test_name": test_name,
        "comp_mode": comp_mode.value,
        "trace_mode": trace_mode.value,
        "iss_enabled": iss_enabled,
        "interactive_gui": interactive_gui,
    }
    write_manifest(
        output_dir,
        "verilator-testharness-run",
        options,
        quiet=quiet,
    )
    manifest = read_manifest(output_dir)
    if (
        not isinstance(manifest, dict)
        or manifest.get("recipe") != "verilator-testharness-run"
        or manifest.get("options") != options
    ):
        print_error(
            f"Run manifest was not written correctly: {output_dir / MANIFEST_NAME}"
        )
        raise typer.Exit(code=1)
    try:
        (output_dir / "result.yml").write_text(
            yaml.safe_dump(
                {
                    "target": target,
                    "test_name": test_name,
                    "status": "PASS" if passed else "FAIL",
                    "iss_enabled": iss_enabled,
                    "detail": detail,
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        print_error(f"Cannot write run result: {error}")
        raise typer.Exit(code=1) from error
    if passed:
        print_success(f"{test_name}: PASS ({detail})", quiet=quiet)
    else:
        print_error(f"{test_name}: FAIL ({detail}); results: {output_dir}")
    print_info(f"Results: {output_dir}", quiet=quiet)
    print_recipe_end("Completed", quiet=quiet)
    if not passed:
        raise typer.Exit(code=1)
