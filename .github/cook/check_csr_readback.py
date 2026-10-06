#!/usr/bin/env python3
# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Small real-RTL regression, independent of Spike and the instruction pipeline."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    target = root / "config/target" / args.target / "rtl_cfg_pkg.sv"
    if Path(args.target).name != args.target or not target.is_file():
        parser.error("Expected an existing target name")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    install = os.environ.get("VERILATOR_INSTALL_DIR")
    verilator = str(Path(install) / "bin/verilator") if install else "verilator"
    command = [
        verilator,
        "--binary",
        "--timing",
        "--assert",
        "-j",
        "2",
        "--top-module",
        "csr_readback_tb",
        "--Mdir",
        str(output / "obj"),
        "-Wno-fatal",
        "-Wno-PINMISSING",
        "-Wno-TIMESCALEMOD",
        "-Icore/include",
        "-Ivendor/pulp-platform/common_cells/include",
        "vendor/pulp-platform/common_cells/src/cf_math_pkg.sv",
        "vendor/pulp-platform/obi/src/obi_pkg.sv",
        "core/include/config_pkg.sv",
        str(target),
        "core/include/riscv_pkg.sv",
        "core/include/build_config_pkg.sv",
        "core/include/ariane_pkg.sv",
        "core/csr_regfile.sv",
        ".github/cook/tests/csr_readback_tb.sv",
    ]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    for name, argv in (
        ("build", command),
        ("run", [str(output / "obj/Vcsr_readback_tb")]),
    ):
        with (output / f"{name}.log").open("w") as log:
            result = subprocess.run(
                argv, stdout=log, stderr=subprocess.STDOUT, timeout=120
            )
        if result.returncode:
            print((output / f"{name}.log").read_text(errors="replace")[-8000:])
            raise SystemExit(1)
    text = (output / "run.log").read_text()
    if "CSR_READBACK_PASS" not in text:
        raise SystemExit("Missing CSR readback completion marker")
    print(text)


if __name__ == "__main__":
    main()
