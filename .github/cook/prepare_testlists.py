# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Bound upstream integer tests, explicitly adapting only the RV64 startup."""

import copy
import hashlib
from pathlib import Path
import shlex

import yaml

# RV32 retains upstream startup; RV64 has a documented, limited M-mode profile.
_RV32_PROFILE = {
    "target": "cv32a60x_axi",
    "march": "rv32imc_zicsr_zifencei",
    "mabi": "ilp32",
    "environment": "upstream-riscv-tests-p",
    "suites": {
        "basic": {
            "source": "verif/tests/base_rv32_p.yaml",
            "tests": [
                "rv32ui-p-add",
                "rv32ui-p-lw",
                "rv32ui-p-sw",
                "rv32ui-p-beq",
                "rv32ui-p-jal",
            ],
            "enabled": 5,
        },
        "integer-extra": {
            "source": "verif/tests/testlist_riscv-tests-cv32a60x-p.yaml",
            "tests": ["rv32ui-p-sub", "rv32ui-p-xor", "rv32ui-p-sll"],
            "enabled": 3,
        },
    },
}

REGRESSION_CONFIG = {
    "schema_version": 1,
    "profiles": {
        "rv32-60x": _RV32_PROFILE,
        "rv32-65x": {**_RV32_PROFILE, "target": "cv32a65x_sv32_axi"},
        "rv64": {
            **_RV32_PROFILE,
            "target": "cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi",
            "march": "rv64imc_zicsr_zifencei",
            "mabi": "lp64",
            "environment": "stage1-integer-m",
            "startup_header": ".github/cook/env/m/riscv_test.h",
            "suites": {
                "basic": {
                    "source": "verif/tests/base_rv64_p.yaml",
                    "tests": [
                        "rv64ui-p-add",
                        "rv64ui-p-lw",
                        "rv64ui-p-sw",
                        "rv64ui-p-beq",
                        "rv64ui-p-jal",
                    ],
                    "enabled": 5,
                },
                "integer-extra": {
                    "source": "verif/tests/testlist_riscv-tests-cv64a6_imafdc_sv39-p.yaml",
                    "tests": ["rv64ui-p-sub", "rv64ui-p-xor", "rv64ui-p-sll"],
                    "enabled": 3,
                },
            },
        },
    },
    "pilots": {
        "rv32-extra": {
            **_RV32_PROFILE,
            "suites": {
                **_RV32_PROFILE["suites"],
                "multiply-divide": {
                    "source": "verif/tests/testlist_riscv-tests-cv32a60x-p.yaml",
                    "tests": ["rv32um-p-div", "rv32um-p-rem", "rv32um-p-mulh"],
                    "enabled": 3,
                },
            },
        },
    },
}


def names(data):
    if not isinstance(data, dict) or not isinstance(data.get("testlist"), list):
        raise ValueError("Expected a testlist sequence")
    result = []
    for entry in data["testlist"]:
        name = entry.get("test") if isinstance(entry, dict) else None
        if (
            not isinstance(name, str)
            or name in ("", ".", "..")
            or Path(name).name != name
        ):
            raise ValueError("Invalid test name")
        iterations = entry.get("iterations", 1)
        if type(iterations) is not int or iterations < 0:
            raise ValueError("Invalid iterations")
        result.extend(f"{name}_{i}" for i in range(iterations))
    if not result or len(set(result)) != len(result):
        raise ValueError("Empty or duplicate testlist")
    return result


def materialize(profile, output, selection="profiles"):
    config = copy.deepcopy(REGRESSION_CONFIG[selection][profile])
    output.mkdir(parents=True, exist_ok=True)
    lists, seen, adaptations = {}, set(), {}
    if "startup_header" in config:
        content = Path(config["startup_header"]).read_bytes()
        config["startup_sha256"] = hashlib.sha256(content).hexdigest()
        (output / "riscv_test.h").write_bytes(content)
    for suite, spec in config["suites"].items():
        path = Path(spec["source"])
        entries = yaml.safe_load(path.read_text())["testlist"]
        if "tests" in spec:
            selected = []
            for name in spec["tests"]:
                matches = [entry for entry in entries if entry.get("test") == name]
                if len(matches) != 1:
                    raise ValueError(f"Missing or duplicate source test: {name}")
                selected.append(matches[0])
            entries = selected
        data = {"testlist": copy.deepcopy(entries)}
        for entry in data["testlist"]:
            entry.setdefault("march", spec.get("march", config["march"]))
            entry.setdefault("mabi", config["mabi"])
            if "startup_header" in config:
                original = entry["test"]
                if not original.startswith("rv64ui-p-"):
                    raise ValueError(
                        "Restricted startup supports selected RV64 integer tests only"
                    )
                original_options = {
                    key: entry[key] for key in ("gcc_opts", "llvm_opts") if key in entry
                }
                for key, value in original_options.items():
                    options = shlex.split(value)
                    include = "-I<path_var>/riscv-tests/env/p/"
                    if options.count(include) != 1:
                        raise ValueError("Expected one upstream p environment include")
                    options[options.index(include)] = "-I.github/cook/env/m/"
                    options.append("-mno-relax")
                    entry[key] = shlex.join(options)
                entry["test"] = "rv64ui-m-stage1-" + original.removeprefix("rv64ui-p-")
                adaptations[entry["test"]] = {
                    "source_test": original,
                    "asm_tests": entry["asm_tests"],
                    "original_compiler_options": original_options,
                    "gcc_opts": entry["gcc_opts"],
                }
        planned = names(data)
        if len(planned) != spec["enabled"] or seen.intersection(planned):
            raise ValueError("Reviewed count changed or cross-suite ELF names collide")
        seen.update(planned)
        destination = output / f"{profile}-{suite}.yaml"
        destination.write_text(yaml.safe_dump(data, sort_keys=False))
        lists[suite] = str(destination)
    (output / "provenance.yml").write_text(
        yaml.safe_dump(
            dict(
                profile=profile,
                selection=selection,
                config=config,
                lists=lists,
                adaptations=adaptations,
            ),
            sort_keys=False,
        )
    )
    return config, lists
