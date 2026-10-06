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
Elaborate the TestHarness testbench with Verilator.

Verilator builds `ariane_testharness`, the SystemVerilog harness of
`corev_apu/tb`, into a native binary that drives it from C++. The harness
talks to the core over AXI, so only the AXI targets are wired for it.
"""

from pathlib import Path
import os
import shlex
import shutil

import typer

from flows.utils.autocompletion import CompMode, TraceMode, autocompletion_target
from flows.utils.manifest import read_manifest, write_manifest
from flows.utils.testharness import elaboration_directory, validate_options
from flows.utils.recipe_report import RecipeReport
from flows.utils.run_cmd import run_cmd
from flows.utils.target_config import read_config_or_exit_testbench_cfg

app = typer.Typer()

TANDEM_SOURCES = (
    "verif/tb/core/uvma_core_cntrl_pkg.sv",
    "verif/tb/core/uvma_cva6pkg_utils_pkg.sv",
    "verif/tb/core/uvma_rvfi_pkg.sv",
    "verif/tb/core/uvmc_rvfi_reference_model_pkg.sv",
    "verif/tb/core/uvmc_rvfi_scoreboard_pkg.sv",
    "corev_apu/tb/common/spike.sv",
)

# C++ side of the harness: the driver, and the debug transport and JTAG
# models it calls. elfloader.cc is not among them, the driver loading the
# ELF through the Spike front-end server.
CXX_SOURCES = (
    "corev_apu/tb/ariane_tb.cpp",
    "corev_apu/tb/dpi/SimDTM.cc",
    "corev_apu/tb/dpi/SimJTAG.cc",
    "corev_apu/tb/dpi/remote_bitbang.cc",
    "corev_apu/tb/dpi/msim_helper.cc",
)


# ==========================================================
# RECIPE
# ==========================================================


@app.command()
def verilator_testharness_comp(
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="CVA6 user configuration",
        autocompletion=autocompletion_target,
    ),
    comp_mode: CompMode = typer.Option(
        CompMode.rtl, help="Compilation mode; only rtl is supported"
    ),
    trace_mode: TraceMode = typer.Option(
        TraceMode.notrace,
        help="notrace, fast (VCD), or compact (FST); gui is unsupported",
    ),
    stats: bool = typer.Option(False, help="RTL perf tracer; currently unsupported"),
    jobs: int = typer.Option(8, "--jobs", "-j", help="Verilator parallel jobs"),
    tandem_enabled: bool = typer.Option(
        False, help="Compile native live Spike/RVFI comparison"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (errors only)"
    ),
):
    """
    Elaborate the TestHarness testbench with Verilator
    """
    report = RecipeReport(
        "verilator-testharness-comp",
        title="VERILATOR TESTHARNESS COMPILATION",
        context={
            "target": target,
            "comp_mode": comp_mode,
            "trace_mode": trace_mode,
            "stats": stats,
            "jobs": jobs,
            "tandem_enabled": tandem_enabled,
        },
        quiet=quiet,
    )

    repo_dir = Path.cwd().resolve()
    elab_dir = elaboration_directory(repo_dir, target, comp_mode, tandem_enabled)
    report.set_out_dir(elab_dir)
    for stale in ("cook_manifest.yml", "cook_report.yml"):
        (elab_dir / stale).unlink(missing_ok=True)
    if jobs < 1:
        report.error_exit("jobs must be positive", env=True)

    if comp_mode != CompMode.rtl:
        report.error_exit(
            f"The TestHarness supports only the rtl compilation mode, got "
            f"{comp_mode.value}",
            env=True,
        )
    if trace_mode == TraceMode.gui:
        report.error_exit("The Verilator TestHarness has no GUI mode", env=True)
    if stats:
        report.error_exit(
            "The RTL perf tracer is not wired to the TestHarness", env=True
        )

    # Test tools in path
    verilator = shutil.which("verilator")
    if verilator is not None:
        report.success(f"verilator: {verilator}")
    else:
        report.error_exit(
            "verilator: Not found\n  Source setenv.sh, which puts it in the path.",
            env=True,
        )

    # Create files and folder paths
    build_root = repo_dir / "build" / target
    elab_dir = elaboration_directory(repo_dir, target, comp_mode, tandem_enabled)
    report.set_out_dir(elab_dir)
    spike_dir = Path(
        os.environ.get("SPIKE_INSTALL_DIR", repo_dir / "tools" / "spike")
    ).resolve()
    binary = elab_dir / "Variane_testharness"

    # ==========================================================
    # CHECK PREREQUISITES
    # ==========================================================
    report.step("Check prerequisites")

    cva6_hier = read_config_or_exit_testbench_cfg(target, report)
    if cva6_hier.value != "axi":
        report.error_exit(
            f"The TestHarness requires an AXI target, {target} is "
            f"{cva6_hier.value}",
            env=True,
        )
    if not (spike_dir / "lib").is_dir():
        report.error_exit(f"Missing Spike installation: {spike_dir}", env=True)

    version = run_cmd(
        cmd=[verilator, "--version"], report=report, log_file=None, timeout=60
    ).strip()
    report.add_context({"verilator": version})
    report.success("Prerequisites OK")

    # ==========================================================
    # CLEAN
    # ==========================================================
    report.step("Clean")
    try:
        if elab_dir.exists():
            shutil.rmtree(elab_dir)
            report.info(f"remove {elab_dir}")
    except Exception as e:
        report.error_exit(f"Clean error : {e}", env=True)

    elab_dir.mkdir(parents=True, exist_ok=True)
    report.info(f"create {elab_dir}")

    # ==========================================================
    # ENV VARIABLES (passed to run_cmd only)
    # ==========================================================
    env_vars = {
        "CVA6_REPO_DIR": str(repo_dir),
        "TARGET_CFG": target,
        "HPDCACHE_DIR": str(repo_dir / "core" / "cache_subsystem" / "hpdcache"),
        "SPIKE_INSTALL_DIR": str(spike_dir),
        "SPIKE_TANDEM": "",
    }

    # ==========================================================
    # BUILD VERILATOR COMMAND
    # ==========================================================
    # The C++ side links the Spike front-end server, disassembler and YAML
    # parser; the rpath lets the binary find them without LD_LIBRARY_PATH.
    cflags = [
        f"-I{repo_dir}",
        f"-I{spike_dir / 'include'}",
        f"-I{spike_dir / 'include' / 'riscv'}",
        f"-I{spike_dir / 'include' / 'disasm'}",
        f"-I{repo_dir / 'corev_apu' / 'tb' / 'dpi'}",
        "-std=c++17",
        "-O3",
        "-DVL_DEBUG",
    ]
    ldflags = [
        f"-L{spike_dir / 'lib'}",
        f"-Wl,-rpath,{spike_dir / 'lib'}",
        "-lfesvr",
        "-lriscv",
        "-ldisasm",
        "-lyaml-cpp",
        "-lpthread",
    ]
    if trace_mode == TraceMode.compact:
        ldflags.append("-lz")
    if tandem_enabled:
        cflags.append("-DCVA6_TANDEM_STACK_BYTES=268435456")
    harness_flist = repo_dir / "verif/tb/core/Flist.testharness"
    if tandem_enabled:
        # Keep the shared upstream source order, inserting the live packages
        # after their dependencies and before the harness that instantiates them.
        content = harness_flist.read_text()
        anchor = "${CVA6_REPO_DIR}/corev_apu/src/ariane.sv"
        if content.count(anchor) != 1:
            report.error_exit(
                "Shared TestHarness filelist changed; review live package ordering",
                env=True,
            )
        additions = "\n".join("${CVA6_REPO_DIR}/" + source for source in TANDEM_SOURCES)
        harness_flist = elab_dir / "Flist.live"
        harness_flist.write_text(content.replace(anchor, additions + "\n" + anchor))

    verilator_cmd = [
        verilator,
        "--build",
        "-j",
        str(jobs),
        "--no-timing",
        str(repo_dir / "verilator_config.vlt"),
        "-f",
        str(repo_dir / "config" / "target" / target / "Flist.cva6"),
        "-f",
        str(harness_flist),
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
    if tandem_enabled:
        verilator_cmd += ["+define+SPIKE_TANDEM=1", "-fno-inline-funcs-eager"]
    if trace_mode == TraceMode.fast:
        verilator_cmd += ["--trace", "+define+VM_TRACE"]
    elif trace_mode == TraceMode.compact:
        verilator_cmd += ["--trace-fst", "+define+VM_TRACE", "+define+VM_TRACE_FST"]
    verilator_cmd += [
        "--top-module",
        "ariane_testharness",
        "--threads-dpi",
        "none",
        "--Mdir",
        str(elab_dir),
        "-O3",
        "--exe",
    ]
    verilator_cmd += [str(repo_dir / source) for source in CXX_SOURCES]

    # ==========================================================
    # LAUNCH VERILATOR COMMAND
    # ==========================================================
    report.step("LAUNCH VERILATOR")

    log_file = elab_dir / "compilation.log"
    # Kept next to the objects they produced: a build directory cannot be
    # reproduced without the version and the command line.
    (elab_dir / "verilator.version").write_text(version + "\n", encoding="utf-8")
    (elab_dir / "compilation.command").write_text(
        shlex.join(verilator_cmd) + "\n", encoding="utf-8"
    )

    run_cmd(
        cmd=verilator_cmd,
        report=report,
        cwd=repo_dir,
        env=env_vars,
        error_patterns=[r"^%Error"],
        warning_patterns=[r"^%Warning"],
        log_file=log_file,
        timeout=1800,
        check=False,
    )

    report.analyze_log(
        log_file,
        name="compilation.log analysis",
        error_patterns=[r"^%Error"],
        warning_patterns=[r"^%Warning"],
        fail_on_error=False,
    )

    if report.failed or not binary.is_file():
        report.error_exit("Variane_testharness not generated")

    report.success("Variane_testharness generated")

    # ==========================================================
    # BUILD MANIFEST
    # ==========================================================
    write_manifest(
        elab_dir,
        "verilator-testharness-comp",
        {
            "target": target,
            "comp_mode": comp_mode,
            "trace_mode": trace_mode,
            "stats": stats,
            "tandem_enabled": tandem_enabled,
        },
        report=report,
    )
    manifest = read_manifest(elab_dir, report)
    if (
        not isinstance(manifest, dict)
        or manifest.get("options", {}).get("tandem_enabled") is not tandem_enabled
    ):
        report.error_exit("TestHarness manifest was not written correctly", env=True)

    # ==========================================================
    # List
    # ==========================================================
    report.step("Generated files")
    generated = []
    for genfile in [binary, log_file]:
        if genfile.exists():
            report.info(f"> {genfile}")
            generated.append(str(genfile.relative_to(repo_dir)))
    report.log("Generated files", generated)

    report.end("Completed")
