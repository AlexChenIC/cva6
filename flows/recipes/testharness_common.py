# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

from pathlib import Path


SIMULATION_MODE = "sim_verilator_testharness"


def validate_path_component(value: str, label: str) -> str:
    if value in {"", ".", ".."} or Path(value).name != value:
        raise ValueError(f"Invalid {label}: {value}")
    return value


def simulation_mode(tandem_enabled: bool) -> str:
    suffix = "_tandem" if tandem_enabled else ""
    return f"{SIMULATION_MODE}{suffix}"


def target_directory(repo_dir: Path, target: str) -> Path:
    target = validate_path_component(target, "target name")
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
    target = validate_path_component(target, "target name")
    return repo_dir / "build" / target / "elab" / simulation_mode(tandem_enabled)


def verilator_binary(repo_dir: Path, target: str, tandem_enabled: bool) -> Path:
    return verilator_elab_directory(repo_dir, target, tandem_enabled) / (
        "Variane_testharness"
    )


def test_simulation_directory(
    repo_dir: Path, target: str, test_name: str, tandem_enabled: bool
) -> Path:
    target = validate_path_component(target, "target name")
    test_name = validate_path_component(test_name, "test name")
    return (
        repo_dir
        / "build"
        / target
        / "simulation"
        / simulation_mode(tandem_enabled)
        / test_name
    )
