# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

from pathlib import Path


SIMULATION_MODE = "sim_verilator_testharness"


def target_directory(repo_dir: Path, target: str) -> Path:
    if target in {"", ".", ".."} or Path(target).name != target:
        raise ValueError(f"Invalid target name: {target}")
    return repo_dir / "config" / "target" / target


def require_target_files(repo_dir: Path, target: str, names: tuple[str, ...]) -> Path:
    directory = target_directory(repo_dir, target)
    missing = [
        str(directory / name) for name in names if not (directory / name).is_file()
    ]
    if missing:
        raise ValueError("Missing target file(s): " + ", ".join(missing))
    return directory


def verilator_elab_directory(
    repo_dir: Path, target: str, tandem_enabled: bool
) -> Path:
    suffix = "_tandem" if tandem_enabled else ""
    return repo_dir / "build" / target / "elab" / f"{SIMULATION_MODE}{suffix}"


def verilator_binary(repo_dir: Path, target: str, tandem_enabled: bool) -> Path:
    return verilator_elab_directory(repo_dir, target, tandem_enabled) / (
        "Variane_testharness"
    )


def test_simulation_directory(repo_dir: Path, target: str, test_name: str) -> Path:
    return (
        repo_dir
        / "build"
        / target
        / "simulation"
        / SIMULATION_MODE
        / test_name
    )
