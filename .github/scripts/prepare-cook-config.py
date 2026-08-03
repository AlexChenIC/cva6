#!/usr/bin/env python3
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Create the environment-specific cook.py configuration for GitHub Actions."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess

import yaml


def require_tool(tool_path: Path) -> None:
    if not tool_path.is_file() or not os.access(tool_path, os.X_OK):
        raise SystemExit(f"Missing executable tool: {tool_path}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    riscv = Path(os.environ["RISCV"]).resolve()
    prefix = os.environ["CV_SW_PREFIX"]
    bin_dir = riscv / "bin"

    tools = {
        "GCC": f"{prefix}gcc",
        "OBJDUMP": f"{prefix}objdump",
        "NM": f"{prefix}nm",
    }
    for tool in tools.values():
        require_tool(bin_dir / tool)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    compiler_data = {
        "github_actions_gcc": {
            "TOOLS_PATH": str(riscv),
            "CLANG": None,
            **tools,
            "TARGET_TOOLCHAIN": prefix.rstrip("-"),
        }
    }
    (output_dir / "compiler.yml").write_text(
        yaml.safe_dump(compiler_data, sort_keys=False), encoding="utf-8"
    )
    (output_dir / "techno.yml").write_text("{}\n", encoding="utf-8")

    version = subprocess.run(
        [str(bin_dir / tools["GCC"]), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    environment_data = {
        "config_schema": 1,
        "cook_config_dir": str(output_dir),
        "toolchain": "github_actions_gcc",
        "tools_path": str(riscv),
        "target_toolchain": prefix.rstrip("-"),
        "gcc_version": version,
        "gcc_binary": str(bin_dir / tools["GCC"]),
        "gcc_binary_sha256": sha256(bin_dir / tools["GCC"]),
        "objdump_binary_sha256": sha256(bin_dir / tools["OBJDUMP"]),
        "nm_binary_sha256": sha256(bin_dir / tools["NM"]),
    }
    (output_dir / "environment.yml").write_text(
        yaml.safe_dump(environment_data, sort_keys=False), encoding="utf-8"
    )

    print(f"Prepared cook.py compiler configuration in {output_dir}")
    print(version)


if __name__ == "__main__":
    main()
