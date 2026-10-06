# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
"""Strict execution evidence shared by the Cook TestHarness and CI diagnostics."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

import yaml

from flows.utils.autocompletion import CompMode, TraceMode
from flows.utils.logged_process import run_logged_process

MANIFEST_NAME = "cook_manifest.yml"
SIMULATION_TIMEOUT = 500


def validate_options(comp_mode: CompMode, trace_mode: TraceMode, stats: bool) -> None:
    if comp_mode != CompMode.rtl:
        raise ValueError(
            "Verilator TestHarness currently supports only rtl compilation mode; "
            f"requested {comp_mode.value}"
        )
    if trace_mode == TraceMode.gui:
        raise ValueError("Verilator TestHarness does not support interactive GUI mode")
    if stats:
        raise ValueError(
            "RTL perf tracer statistics are not supported by the Verilator "
            "TestHarness recipe"
        )


def target_directory(repo_dir: Path, target: str) -> Path:
    if target in {"", ".", ".."} or Path(target).name != target:
        raise ValueError(f"Invalid target name: {target}")

    directory = repo_dir / "config" / "target" / target
    required = (
        directory / "Flist.cva6",
        directory / "rtl_cfg_pkg.sv",
        directory / "testbench_cfg.yml",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError("Missing target file(s): " + ", ".join(missing))
    config = yaml.safe_load(
        (directory / "testbench_cfg.yml").read_text(encoding="utf-8")
    )
    if not isinstance(config, dict) or config.get("hier") != "axi":
        raise ValueError(
            f"The current Verilator TestHarness requires an AXI target (hier: axi); "
            f"requested {target}. Use a matching AXI configuration such as cv32a60x_axi."
        )
    return directory


def build_directory(repo_dir: Path, *parts: str) -> Path:
    repo_dir = repo_dir.resolve()
    directory = repo_dir / "build"
    for part in parts:
        if part in {"", ".", ".."} or Path(part).name != part:
            raise ValueError(f"Invalid build path component: {part}")
        directory /= part
    for parent in (directory, *directory.parents):
        if parent == repo_dir:
            break
        if parent.is_symlink():
            raise ValueError(
                f"Build output must not traverse a symbolic link: {parent}"
            )
    return directory


def elaboration_directory(
    repo_dir: Path, target: str, comp_mode: CompMode, tandem_enabled: bool = False
) -> Path:
    suffix = "_tandem" if tandem_enabled else ""
    return build_directory(
        repo_dir, target, "elab", f"sim_{comp_mode.value}_verilator_testharness{suffix}"
    )


def testharness_binary(
    repo_dir: Path, target: str, comp_mode: CompMode, tandem_enabled: bool = False
) -> Path:
    return (
        elaboration_directory(repo_dir, target, comp_mode, tandem_enabled)
        / "Variane_testharness"
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
    repo_dir: Path,
    target: str,
    test_name: str,
    comp_mode: CompMode,
    tandem_enabled: bool = False,
) -> Path:
    target = validate_path_component(target, "target name")
    test_name = validate_path_component(test_name, "test name")
    return build_directory(
        repo_dir,
        target,
        "simulation",
        f"sim_{comp_mode.value}_verilator_testharness{'_tandem' if tandem_enabled else ''}",
        test_name,
    )


def testharness_log_passed(log: Path) -> tuple[bool, str]:
    if not log.is_file():
        return False, f"missing TestHarness log: {log}"
    try:
        text = log.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
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


def read_tandem_report(path: Path) -> dict:
    """Validate the native rvfi_compare report, not disassembled trace text."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Tandem report must be a regular file")
    report = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Missing or malformed live tandem report")
    for key in ("exit_code", "instr_count", "csrs_match_count", "mismatches_count"):
        if type(report.get(key)) is not int or report[key] < 0:
            raise ValueError(f"Invalid tandem report field: {key}")
    if (
        report.get("exit_cause") != "SUCCESS"
        or report["exit_code"] != 0
        or report["instr_count"] == 0
        or report["mismatches_count"] != 0
        or "mismatches" not in report
        or report.get("mismatches") not in (None, [])
        or report.get("mismatch_description") != ""
    ):
        raise ValueError(
            f"Live tandem failed: cause={report.get('exit_cause')}, "
            f"exit={report['exit_code']}, compared={report['instr_count']}, "
            f"mismatches={report['mismatches_count']}"
        )
    return report


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
    tohost: str,
    trace_mode: TraceMode,
    spike_config: Path | None = None,
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
    if spike_config is not None:
        command.append(f"+config_file={spike_config}")
    return command


def prepare_spike_config(repo: Path, target: str, output: Path) -> Path | None:
    """Snapshot the target model parameters, matching the Cook UVM flow."""
    source = repo / "config" / "target" / target / "spike.yaml"
    metadata = {"mode": "rtl-derived"}
    snapshot = None
    try:
        source_stat = source.lstat()
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError(f"Spike configuration must be a regular file: {source}")
        content = source.read_bytes()
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or not isinstance(
            data.get("spike_param_tree"), dict
        ):
            raise ValueError(f"Invalid Spike parameter tree: {source}")
        snapshot = output / "spike-config.yaml"
        snapshot.write_bytes(content)
        metadata = {
            "mode": "target-yaml",
            "source": str(source.relative_to(repo)),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    (output / "spike-config-source.yml").write_text(
        yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
    )
    return snapshot


def run_spike_dasm(
    spike_dasm: Path,
    raw_trace: Path,
    output_log: Path,
    error_log: Path,
    compiler_isa: str,
    timeout: int,
    *,
    env: dict[str, str],
) -> tuple[bool, str]:
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
                env=env,
            )
    except subprocess.TimeoutExpired:
        return False, f"spike-dasm timed out after {timeout} seconds"
    except OSError as error:
        return False, f"trace disassembly I/O or launch error: {error}"
    if result.returncode != 0:
        return (
            False,
            f"spike-dasm exited with code {result.returncode}; see {error_log}",
        )
    return True, "trace disassembly completed"


def check_manifests(
    *,
    target,
    test_name,
    comp_mode,
    trace_mode,
    compile_dir,
    elab_dir,
    tandem_enabled=False,
):
    software = yaml.safe_load((compile_dir / MANIFEST_NAME).read_text())
    hardware = yaml.safe_load((elab_dir / MANIFEST_NAME).read_text())
    for manifest, recipe, expected in (
        (software, "sw-compile", {"target": target, "test_name": test_name}),
        (
            hardware,
            "verilator-testharness-comp",
            {"target": target, "comp_mode": comp_mode.value},
        ),
    ):
        if (
            not isinstance(manifest, dict)
            or manifest.get("recipe") != recipe
            or not isinstance(manifest.get("options"), dict)
        ):
            raise ValueError("Missing or malformed Cook prerequisite manifest")
        if any(
            manifest["options"].get(key) != value for key, value in expected.items()
        ):
            raise ValueError("Inconsistent Cook prerequisite manifest")
    if hardware["options"].get("tandem_enabled", False) is not tandem_enabled:
        raise ValueError(
            "TestHarness live tandem build does not match the requested mode"
        )
    if (
        trace_mode != TraceMode.notrace
        and hardware["options"].get("trace_mode") != trace_mode.value
    ):
        raise ValueError("Trace mode requires a matching TestHarness build")
    for directory, recipe in (
        (compile_dir, "sw-compile"),
        (elab_dir, "verilator-testharness-comp"),
    ):
        report = yaml.safe_load((directory / "cook_report.yml").read_text())
        if (
            not isinstance(report, dict)
            or report.get("recipe") != recipe
            or report.get("status") != "pass"
        ):
            raise ValueError("Prerequisite compilation has no passing Cook report")


def run_testharness_and_trace(
    *,
    command: list[str],
    output_dir: Path,
    env: dict[str, str],
    spike_install: Path,
    compiler_isa: str,
    timeout: int,
    tandem_enabled: bool = False,
) -> tuple[bool, str]:
    testharness_log = output_dir / "testharness.log"
    (output_dir / "simulation.command.json").write_text(
        json.dumps(command, indent=2) + "\n", encoding="utf-8"
    )
    return_code, timed_out = run_logged_process(
        command,
        cwd=output_dir,
        env=env,
        log=testharness_log,
        timeout=timeout,
    )
    (output_dir / "execution.yml").write_text(
        yaml.safe_dump({"exit_code": return_code, "timed_out": timed_out}),
        encoding="utf-8",
    )
    if timed_out:
        return False, f"TestHarness timed out after {timeout} seconds"
    if return_code != 0:
        return False, f"TestHarness returned {return_code}"

    passed, detail = testharness_log_passed(testharness_log)
    if not passed:
        return False, detail

    if tandem_enabled:
        try:
            report = read_tandem_report(output_dir / "testharness.log.yaml")
            detail += f"; live tandem compared {report['instr_count']} instructions, 0 mismatches"
        except (OSError, ValueError, yaml.YAMLError) as error:
            return False, f"Live tandem evidence failed: {error}"

    raw_trace = output_dir / "trace_rvfi_hart_00.dasm"
    failure = "RTL simulation passed; trace post-processing failed"
    # Only an absent path is optional; invalid trace paths must not be skipped.
    try:
        trace_stat = raw_trace.lstat()
    except FileNotFoundError:
        return (
            True,
            f"{detail}; trace disassembly skipped: raw trace not produced ({raw_trace.name})",
        )
    except OSError as error:
        return False, f"{failure}: cannot inspect raw trace: {error}"
    if not stat.S_ISREG(trace_stat.st_mode):
        return False, f"{failure}: raw trace is not a regular file: {raw_trace}"

    trace_passed, trace_detail = run_spike_dasm(
        spike_install / "bin" / "spike-dasm",
        raw_trace,
        output_dir / "verilator.log",
        output_dir / "spike_dasm.log",
        compiler_isa,
        min(timeout, 120),
        env=env,
    )
    if not trace_passed:
        return False, f"{failure}: {trace_detail}"
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
    tandem_enabled: bool = False,
    run_name: str | None = None,
) -> tuple[bool, str, Path]:
    output_dir = simulation_directory(
        Path.cwd(), target, run_name or test_name, comp_mode, tandem_enabled
    )
    # Invalidate previous success even if this invocation fails its prerequisites.
    for stale in ("result.yml", "cook_manifest.yml", "cook_report.yml"):
        (output_dir / stale).unlink(missing_ok=True)
    if type(timeout) is not int or timeout < 1:
        raise ValueError("Simulation timeout must be a positive integer")
    if iss_enabled:
        raise ValueError(
            "Offline ISS comparison is unsupported; use --tandem-enabled for live checking"
        )

    repo_dir = Path.cwd().resolve()
    validate_run_options(comp_mode, trace_mode, interactive_gui)
    target = validate_path_component(target, "target name")
    test_name = validate_path_component(test_name, "test name")

    target_directory(repo_dir, target)
    compile_dir = repo_dir / "build" / target / "compile" / test_name
    elab_dir = elaboration_directory(repo_dir, target, comp_mode, tandem_enabled)
    elf = compile_dir / f"{test_name}.elf"
    binary = testharness_binary(repo_dir, target, comp_mode, tandem_enabled)
    if not elf.is_file() or not binary.is_file():
        raise ValueError(
            "Missing compiled software or TestHarness; compile prerequisites first"
        )
    check_manifests(
        target=target,
        test_name=test_name,
        comp_mode=comp_mode,
        trace_mode=trace_mode,
        compile_dir=compile_dir,
        elab_dir=elab_dir,
        tandem_enabled=tandem_enabled,
    )

    software = yaml.safe_load((compile_dir / MANIFEST_NAME).read_text())["options"]
    compiler_isa = software.get("march")
    symbols = software.get("symbols")
    tohost = symbols.get("tohost") if isinstance(symbols, dict) else None
    if not isinstance(compiler_isa, str) or not isinstance(tohost, str):
        raise ValueError("Missing march or tohost in software manifest")
    if not compiler_isa:
        raise ValueError("Empty compiler ISA in software manifest")
    if not re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]+", tohost) or int(tohost, 16) == 0:
        raise ValueError("Invalid or zero tohost address in software manifest")
    if not os.access(binary, os.X_OK):
        raise ValueError(f"TestHarness is not executable: {binary}")
    env, spike_install = runtime_environment(repo_dir, target)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    spike_config = (
        prepare_spike_config(repo_dir, target, output_dir) if tandem_enabled else None
    )
    command = testharness_command(
        binary,
        elf,
        target=target,
        tohost=tohost,
        trace_mode=trace_mode,
        spike_config=spike_config,
    )
    passed, detail = run_testharness_and_trace(
        command=command,
        output_dir=output_dir,
        env=env,
        spike_install=spike_install,
        compiler_isa=compiler_isa,
        timeout=timeout,
        tandem_enabled=tandem_enabled,
    )
    return passed, detail, output_dir
