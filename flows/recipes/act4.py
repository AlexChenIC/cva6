# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

"""Cook recipe for the frozen, self-checking ACT4 runtime corpus."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile

import typer

from flows.act4.corpus import CorpusError, prepare_corpus
from flows.act4.package import PackageError, package_corpus
from flows.act4.runner import RunnerError, run_corpus
from flows.utils.report_builder import Report, TableStatusMetric
from flows.utils.utils import (
    autocompletion_target,
    print_error,
    print_param_table,
    print_recipe_end,
    print_recipe_title,
    print_step,
    print_success,
)

app = typer.Typer()
SUPPORTED_TARGETS = frozenset({"cv32a65x_axi"})
DEFAULT_CYCLE_TIMEOUT = 10_000_000
DEFAULT_WALL_TIMEOUT_SECONDS = 300


def _safe_filename_component(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:100]
    return sanitized or "invalid-target"


def _resolve_from_repo(repo_directory: Path, value: Path) -> Path:
    return value if value.is_absolute() else repo_directory / value


def _result_metric() -> TableStatusMetric:
    metric = TableStatusMetric("ACT4 frozen-corpus results")
    metric.add_column("Target", "text")
    metric.add_column("Test", "text")
    metric.add_column("ELF", "text")
    metric.add_column("Duration (s)", "text")
    metric.add_column("Detail", "text")
    metric.add_column("Log", "text")
    return metric


@app.command("act4-package")
def act4_package(
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="CVA6 configuration represented by the generated ACT4 ELFs",
        autocompletion=autocompletion_target,
    ),
    elf_directory: Path = typer.Option(
        ...,
        "--elf-directory",
        help="ACT work/<config>/elfs directory containing final .elf files",
    ),
    resolved_profile: Path = typer.Option(
        ...,
        "--resolved-profile",
        help="Resolved profile JSON used to generate the final ELFs",
    ),
    act_commit: str = typer.Option(
        ..., "--act-commit", help="Pinned full ACT Git commit SHA"
    ),
    cva6_commit: str = typer.Option(
        ..., "--cva6-commit", help="Pinned full CVA6 Git commit SHA"
    ),
    image_digest: str = typer.Option(
        ..., "--image-digest", help="Pinned generation container sha256 digest"
    ),
    output_directory: Path | None = typer.Option(
        None,
        "--output-directory",
        help="Destination for corpus-manifest.json and the deterministic archive",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Explicitly replace an existing manifest/archive pair",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress command output and summaries"
    ),
) -> None:
    """Package final ACT4 ELFs deterministically; never commit the outputs."""

    print_recipe_title("ACT4 DETERMINISTIC PACKAGER", quiet=quiet)
    repo_directory = Path.cwd().resolve()
    if target not in SUPPORTED_TARGETS:
        supported = ", ".join(sorted(SUPPORTED_TARGETS))
        print_error(
            f"Unsupported ACT4 target: {target}; supported targets: {supported}",
            quiet=quiet,
        )
        raise typer.Exit(code=1)
    elf_directory = _resolve_from_repo(repo_directory, elf_directory)
    resolved_profile = _resolve_from_repo(repo_directory, resolved_profile)
    if output_directory is None:
        output_directory = (
            repo_directory / "verif" / "tests" / "act4" / target / "corpus"
        )
    else:
        output_directory = _resolve_from_repo(repo_directory, output_directory)

    print_param_table(
        {
            "Target": target,
            "ELF directory": elf_directory,
            "Resolved profile": resolved_profile,
            "ACT commit": act_commit,
            "CVA6 commit": cva6_commit,
            "Image digest": image_digest,
            "Output directory": output_directory,
            "Replace existing output": replace,
            "Git operation": "none",
        },
        "Options",
        quiet=quiet,
    )
    try:
        result = package_corpus(
            elf_directory,
            resolved_profile,
            output_directory,
            target=target,
            act_commit=act_commit,
            cva6_commit=cva6_commit,
            image_digest=image_digest,
            replace=replace,
        )
    except (PackageError, CorpusError, OSError) as error:
        print_error(str(error), quiet=quiet)
        raise typer.Exit(code=1) from error

    print_success(
        f"Packaged {result.test_count} ACT4 ELF(s): {result.archive_path}",
        quiet=quiet,
    )
    print_success(f"Manifest: {result.manifest_path}", quiet=quiet)
    print_recipe_end("Completed (no Git operation performed)", quiet=quiet)


@app.command("act4-run")
def act4_run(
    target: str = typer.Option(
        ...,
        "--target",
        "-t",
        help="CVA6 configuration matching the frozen ACT4 corpus",
        autocompletion=autocompletion_target,
    ),
    corpus_directory: Path | None = typer.Option(
        None,
        "--corpus-directory",
        help=(
            "Directory containing corpus-manifest.json and the integrity-verified "
            "ACT4 ELF archive"
        ),
    ),
    simulator: Path = typer.Option(
        Path("work-ver/Variane_testharness"),
        "--simulator",
        help="Already-built standalone CVA6 Verilator TestHarness binary",
    ),
    cycle_timeout: int = typer.Option(
        DEFAULT_CYCLE_TIMEOUT,
        "--cycle-timeout",
        min=1,
        help="RTL rvfi_tracer time_out limit for each ELF",
    ),
    wall_timeout_seconds: int = typer.Option(
        DEFAULT_WALL_TIMEOUT_SECONDS,
        "--wall-timeout-seconds",
        min=1,
        help="Outer process timeout for each ELF",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress command output and summaries"
    ),
) -> None:
    """Run every integrity-verified self-checking ELF without Sail or Spike."""

    print_recipe_title("ACT4 FROZEN CORPUS", quiet=quiet)
    repo_directory = Path.cwd().resolve()
    target_supported = target in SUPPORTED_TARGETS
    if corpus_directory is None and target_supported:
        corpus_directory = (
            repo_directory / "verif" / "tests" / "act4" / target / "corpus"
        )
    elif corpus_directory is None:
        # Do not interpolate an untrusted unsupported target into a path.
        corpus_directory = repo_directory / "verif" / "tests" / "act4" / "invalid"
    else:
        corpus_directory = _resolve_from_repo(repo_directory, corpus_directory)
    simulator = _resolve_from_repo(repo_directory, simulator)

    print_param_table(
        {
            "Target": target,
            "Corpus": corpus_directory,
            "Simulator": simulator,
            "Cycle timeout": cycle_timeout,
            "Wall timeout (seconds)": wall_timeout_seconds,
            "Reference model at runtime": "none (self-checking ELF)",
        },
        "Options",
        quiet=quiet,
    )

    metric = _result_metric()
    failed = False
    expected_error: str | None = None
    if not target_supported:
        supported = ", ".join(sorted(SUPPORTED_TARGETS))
        expected_error = (
            f"Unsupported ACT4 target: {target}; supported targets: {supported}"
        )

    if expected_error is None:
        runtime_root = repo_directory / "build" / target / "act4-runtime"
        runtime_root.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(
                prefix="corpus-", dir=runtime_root
            ) as temporary:
                prepared = prepare_corpus(
                    corpus_directory,
                    Path(temporary) / "extracted",
                    expected_target=target,
                )
                profile_id = prepared.manifest.generation.profile_sha256[:16]
                archive_id = prepared.manifest.archive_sha256[:16]
                log_directory = (
                    repo_directory
                    / "artifacts"
                    / "act4"
                    / target
                    / f"{profile_id}-{archive_id}"
                    / "logs"
                )
                if os.path.lexists(log_directory):
                    if log_directory.is_symlink() or not log_directory.is_dir():
                        raise RunnerError(
                            f"ACT4 log path must be a regular directory: {log_directory}"
                        )
                    shutil.rmtree(log_directory)
                print_step(
                    f"Run {len(prepared.tests)} integrity-verified ACT4 ELF(s)",
                    quiet=quiet,
                )
                results = run_corpus(
                    prepared,
                    simulator,
                    log_directory,
                    cycle_timeout=cycle_timeout,
                    wall_timeout_seconds=wall_timeout_seconds,
                    cwd=Path(temporary) / "work",
                )
                if not results:
                    raise RunnerError("ACT4 runner returned zero test results")
                for result in results:
                    row = (
                        target,
                        result.test_id,
                        result.elf,
                        f"{result.duration_seconds:.3f}",
                        result.detail,
                        str(result.log_path.relative_to(repo_directory)),
                    )
                    if result.passed:
                        metric.add_pass(*row)
                        print_success(
                            f"{result.test_id}: PASS ({result.detail})", quiet=quiet
                        )
                    else:
                        metric.add_fail(*row)
                        print_error(
                            f"{result.test_id}: FAIL ({result.detail})", quiet=quiet
                        )
                        failed = True
        except (CorpusError, RunnerError, OSError) as error:
            expected_error = str(error)

    if expected_error is not None:
        failed = True
        metric.add_fail(target, "<preflight>", "-", "0.000", expected_error, "-")
        print_error(expected_error, quiet=quiet)

    report = Report()
    report.add_metric(metric)
    report_path = (
        repo_directory
        / "artifacts"
        / "reports"
        / f"report_act4_{_safe_filename_component(target)}.yml"
    )
    report.dump(str(report_path.relative_to(repo_directory)))
    print_recipe_end("Failed" if failed else "Completed", quiet=quiet)
    if failed:
        raise typer.Exit(code=1)
