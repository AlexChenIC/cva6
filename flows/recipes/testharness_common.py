# Copyright 2026 OpenHW Group
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple, Protocol

from flows.utils.utils import CompMode, TraceMode


class TestHarnessResult(NamedTuple):
    name: str
    compiler_isa: str
    mabi: str
    backend: str
    passed: bool
    detail: str


class TestHarnessRunner(Protocol):
    def __call__(
        self,
        *,
        target: str,
        test_name: str,
        comp_mode: CompMode,
        trace_mode: TraceMode,
        tandem_enabled: bool,
        iss_enabled: bool,
        iss_timeout: int,
        seed: str,
        emulator_options: list[str],
        run_options: list[str],
    ) -> TestHarnessResult: ...


BUILD_MANIFEST = "testharness-build.json"


def validate_path_component(value: str, label: str) -> str:
    if value in {"", ".", ".."} or Path(value).name != value:
        raise ValueError(f"Invalid {label}: {value}")
    return value


def simulation_mode(comp_mode: CompMode, tandem_enabled: bool) -> str:
    suffix = "_tandem" if tandem_enabled else ""
    return f"sim_{comp_mode.value}_verilator_testharness{suffix}"


def validate_verilator_options(
    *,
    comp_mode: CompMode,
    trace_mode: TraceMode,
    stats: bool = False,
    interactive_gui: bool = False,
) -> None:
    if comp_mode != CompMode.rtl:
        raise ValueError(
            "Verilator TestHarness currently supports only rtl compilation mode; "
            f"requested {comp_mode.value}"
        )
    if trace_mode == TraceMode.gui or interactive_gui:
        raise ValueError(
            "Interactive GUI is not supported by the Verilator TestHarness recipe"
        )
    if stats:
        raise ValueError(
            "RTL perf tracer statistics are not supported by the Verilator "
            "TestHarness recipe"
        )


def validate_iss_options(*, iss_enabled: bool, tandem_enabled: bool) -> None:
    if tandem_enabled and not iss_enabled:
        raise ValueError("Live Spike tandem mode requires --iss-enabled")


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
    repo_dir: Path,
    target: str,
    comp_mode: CompMode,
    tandem_enabled: bool,
) -> Path:
    target = validate_path_component(target, "target name")
    return (
        repo_dir
        / "build"
        / target
        / "elab"
        / simulation_mode(comp_mode, tandem_enabled)
    )


def verilator_binary(
    repo_dir: Path,
    target: str,
    comp_mode: CompMode,
    tandem_enabled: bool,
) -> Path:
    return verilator_elab_directory(
        repo_dir, target, comp_mode, tandem_enabled
    ) / "Variane_testharness"


def write_build_manifest(
    directory: Path,
    *,
    target: str,
    comp_mode: CompMode,
    trace_mode: TraceMode,
    tandem_enabled: bool,
) -> Path:
    manifest = directory / BUILD_MANIFEST
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "simulator": "verilator",
                "target": target,
                "comp_mode": comp_mode.value,
                "trace_mode": trace_mode.value,
                "tandem_enabled": tandem_enabled,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def require_matching_build(
    directory: Path,
    *,
    target: str,
    comp_mode: CompMode,
    trace_mode: TraceMode,
    tandem_enabled: bool,
) -> None:
    manifest = directory / BUILD_MANIFEST
    if not manifest.is_file():
        raise ValueError(f"Missing TestHarness build manifest: {manifest}")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid TestHarness build manifest: {error}") from error

    expected = {
        "schema_version": 1,
        "simulator": "verilator",
        "target": target,
        "comp_mode": comp_mode.value,
        "trace_mode": trace_mode.value,
        "tandem_enabled": tandem_enabled,
    }
    if not isinstance(data, dict):
        raise ValueError("TestHarness build manifest must contain an object")
    actual = {key: data.get(key) for key in expected}
    if actual != expected:
        raise ValueError(
            "TestHarness build options do not match the requested run; "
            f"expected {expected}, found {actual}"
        )


def test_simulation_directory(
    repo_dir: Path,
    target: str,
    test_name: str,
    comp_mode: CompMode,
    tandem_enabled: bool,
) -> Path:
    target = validate_path_component(target, "target name")
    test_name = validate_path_component(test_name, "test name")
    return (
        repo_dir
        / "build"
        / target
        / "simulation"
        / simulation_mode(comp_mode, tandem_enabled)
        / test_name
    )
