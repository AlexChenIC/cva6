# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil

import typer

from flows.recipes.testharness_common import (
    require_target_files,
    verilator_binary,
    verilator_elab_directory,
)
from flows.utils.utils import (
    TraceMode,
    autocompletion_target,
    print_error,
    print_info,
    print_param_table,
    print_recipe_end,
    print_recipe_title,
    print_step,
    print_success,
    run_cmd,
)

app = typer.Typer()


TESTHARNESS_PACKAGE_SOURCES = (
    "corev_apu/tb/ariane_axi_pkg.sv",
    "corev_apu/tb/axi_intf.sv",
    "corev_apu/register_interface/src/reg_intf.sv",
    "corev_apu/tb/ariane_soc_pkg.sv",
    "corev_apu/riscv-dbg/src/dm_pkg.sv",
    "corev_apu/tb/ariane_axi_soc_pkg.sv",
)


TANDEM_SOURCES = (
    "verif/tb/core/uvma_core_cntrl_pkg.sv",
    "verif/tb/core/uvma_cva6pkg_utils_pkg.sv",
    "verif/tb/core/uvma_rvfi_pkg.sv",
    "verif/tb/core/uvmc_rvfi_reference_model_pkg.sv",
    "verif/tb/core/uvmc_rvfi_scoreboard_pkg.sv",
    "corev_apu/tb/common/spike.sv",
)


def _tool_paths(repo_dir: Path) -> tuple[Path, Path, Path]:
    try:
        riscv = Path(os.environ["RISCV"]).resolve()
    except KeyError as error:
        raise ValueError("RISCV is not set") from error

    verilator_install = Path(
        os.environ.get("VERILATOR_INSTALL_DIR", repo_dir / "tools" / "verilator")
    ).resolve()
    spike_install = Path(
        os.environ.get("SPIKE_INSTALL_DIR", repo_dir / "tools" / "spike")
    ).resolve()
    return riscv, verilator_install, spike_install


def _compile_environment(
    repo_dir: Path, target: str, spike_install: Path
) -> dict[str, str]:
    return {
        "CVA6_REPO_DIR": str(repo_dir),
        "TARGET_CFG": target,
        "HPDCACHE_DIR": str(repo_dir / "core" / "cache_subsystem" / "hpdcache"),
        "SPIKE_INSTALL_DIR": str(spike_install),
    }


def build_command(
    *,
    repo_dir: Path,
    target: str,
    tandem_enabled: bool,
    trace_mode: TraceMode,
    jobs: int,
    verilator: str,
    riscv: Path,
    verilator_install: Path,
    spike_install: Path,
) -> list[str]:
    elab_dir = verilator_elab_directory(repo_dir, target, tandem_enabled)
    cflags = [
        f"-I{repo_dir}",
        f"-I{spike_install / 'include' / 'riscv'}",
        f"-I{spike_install / 'include' / 'disasm'}",
        f"-I{verilator_install / 'share' / 'verilator' / 'include' / 'vltstd'}",
        f"-I{riscv / 'include'}",
        f"-I{spike_install / 'include'}",
        "-std=c++17",
        f"-I{repo_dir / 'corev_apu' / 'tb' / 'dpi'}",
        "-O3",
        "-DVL_DEBUG",
        f"-I{spike_install}",
    ]
    ldflags = [
        f"-L{riscv / 'lib'}",
        f"-L{spike_install / 'lib'}",
        f"-Wl,-rpath,{riscv / 'lib'}",
        f"-Wl,-rpath,{spike_install / 'lib'}",
        "-lfesvr",
        "-lriscv",
        "-ldisasm",
        "-lyaml-cpp",
        "-lpthread",
    ]
    if trace_mode == TraceMode.compact:
        ldflags.append("-lz")
    include_dirs = (
        "vendor/pulp-platform/common_cells/include",
        "vendor/pulp-platform/axi/include",
        "corev_apu/register_interface/include",
        "corev_apu/tb/common",
        "vendor/pulp-platform/obi/include",
        "verif/core-v-verif/lib/uvm_agents/uvma_rvfi",
        "verif/core-v-verif/lib/uvm_components/uvmc_rvfi_reference_model",
        "verif/core-v-verif/lib/uvm_components/uvmc_rvfi_scoreboard",
        "verif/core-v-verif/lib/uvm_agents/uvma_core_cntrl",
        "verif/tb/core",
        "core/include",
        "corev_apu/instr_tracing/ITI/include",
        "corev_apu/axi_node",
    )

    command = [
        verilator,
        "--build",
        "-j",
        str(jobs),
        "--no-timing",
        str(repo_dir / "verilator_config.vlt"),
        "-f",
        str(repo_dir / "config" / "target" / target / "Flist.cva6"),
        str(repo_dir / "core" / "cva6_rvfi.sv"),
    ]
    command.extend(str(repo_dir / source) for source in TESTHARNESS_PACKAGE_SOURCES)
    if tandem_enabled:
        command.extend(str(repo_dir / source) for source in TANDEM_SOURCES)
        command.append("+define+SPIKE_TANDEM")
    command.extend(
        [
            "-f",
            str(repo_dir / "verif" / "tb" / "core" / "Flist.verilator_testharness"),
            "-DPRELOAD=1",
            "--unroll-count",
            "256",
            "-Wall",
            "-Werror-PINMISSING",
            "-Werror-IMPLICIT",
            "-Wno-fatal",
            "-Wno-PINCONNECTEMPTY",
            "-Wno-ASSIGNDLY",
            "-Wno-DECLFILENAME",
            "-Wno-UNUSED",
            "-Wno-UNOPTFLAT",
            "-Wno-BLKANDNBLK",
            "-Wno-style",
            "-LDFLAGS",
            shlex.join(ldflags),
            "-CFLAGS",
            shlex.join(cflags),
            "--cc",
            "--vpi",
        ]
    )
    command.extend(f"+incdir+{repo_dir / directory}" for directory in include_dirs)
    command.append(f"+incdir+{spike_install / 'include' / 'disasm'}")

    if trace_mode == TraceMode.fast:
        command.extend(("--trace", "+define+VM_TRACE"))
    elif trace_mode == TraceMode.compact:
        command.extend(("--trace-fst", "+define+VM_TRACE", "+define+VM_TRACE_FST"))
    elif trace_mode != TraceMode.notrace:
        raise ValueError(f"Unsupported Verilator trace mode: {trace_mode.value}")

    command.extend(
        [
            "--top-module",
            "ariane_testharness",
            "--threads-dpi",
            "none",
            "--Mdir",
            str(elab_dir),
            "-O3",
            "--exe",
            str(repo_dir / "corev_apu" / "tb" / "ariane_tb.cpp"),
            str(repo_dir / "corev_apu" / "tb" / "dpi" / "SimDTM.cc"),
            str(repo_dir / "corev_apu" / "tb" / "dpi" / "SimJTAG.cc"),
            str(repo_dir / "corev_apu" / "tb" / "dpi" / "remote_bitbang.cc"),
            str(repo_dir / "corev_apu" / "tb" / "dpi" / "msim_helper.cc"),
        ]
    )
    return command


@app.command()
def verilator_testharness_comp(
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="CVA6 user configuration",
        autocompletion=autocompletion_target,
    ),
    tandem_enabled: bool = typer.Option(
        False,
        "--tandem-enabled/--no-tandem",
        help="Compile the live Spike tandem components",
    ),
    trace_mode: TraceMode = typer.Option(
        TraceMode.notrace, help="Waveform trace format"
    ),
    jobs: int | None = typer.Option(
        None, min=1, help="Parallel jobs used by the Verilator build"
    ),
    clean: bool = typer.Option(
        True, "--clean/--no-clean", help="Remove the existing elaboration directory"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (errors only)"
    ),
) -> None:
    """Compile the CVA6 Verilator TestHarness executable directly."""
    print_recipe_title("VERILATOR TESTHARNESS COMPILATION", quiet=quiet)
    repo_dir = Path.cwd().resolve()

    try:
        require_target_files(repo_dir, target, ("Flist.cva6", "rtl_cfg_pkg.sv"))
        riscv, verilator_install, spike_install = _tool_paths(repo_dir)
        verilator = shutil.which("verilator")
        if verilator is None:
            raise ValueError("verilator is not available in PATH")
        job_count = jobs or int(os.environ.get("NUM_JOBS", "1"))
        if job_count < 1:
            raise ValueError("NUM_JOBS must be at least 1")
        command = build_command(
            repo_dir=repo_dir,
            target=target,
            tandem_enabled=tandem_enabled,
            trace_mode=trace_mode,
            jobs=job_count,
            verilator=verilator,
            riscv=riscv,
            verilator_install=verilator_install,
            spike_install=spike_install,
        )
    except (OSError, TypeError, ValueError) as error:
        print_error(str(error), quiet=quiet)
        raise typer.Exit(code=1) from error

    elab_dir = verilator_elab_directory(repo_dir, target, tandem_enabled)
    binary = verilator_binary(repo_dir, target, tandem_enabled)
    print_param_table(
        {
            "Target": target,
            "Tandem enabled": tandem_enabled,
            "Trace mode": trace_mode.value,
            "Build directory": elab_dir,
            "Jobs": job_count,
        },
        "Options",
        quiet=quiet,
    )

    print_step("Compile TestHarness", quiet=quiet)
    try:
        if clean and elab_dir.exists():
            shutil.rmtree(elab_dir)
        elab_dir.mkdir(parents=True, exist_ok=True)
        run_cmd(
            command,
            cwd=repo_dir,
            env=_compile_environment(repo_dir, target, spike_install),
            log_file=elab_dir / "compile.log",
            check=True,
            capture_output=False,
            quiet=quiet,
        )
    except (OSError, RuntimeError) as error:
        print_error(f"Verilator compilation failed: {error}", quiet=quiet)
        raise typer.Exit(code=1) from error

    if not binary.is_file():
        print_error(f"Missing Verilator executable: {binary}", quiet=quiet)
        raise typer.Exit(code=1)

    print_success(f"Verilator TestHarness: {binary}", quiet=quiet)
    print_info(f"Compile log: {elab_dir / 'compile.log'}", quiet=quiet)
    print_recipe_end("Completed", quiet=quiet)
