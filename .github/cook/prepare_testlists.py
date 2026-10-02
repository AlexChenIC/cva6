#!/usr/bin/env python3
# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Copy Thales Cook base lists; retain the old selection for explicit diagnostics."""

import argparse
import copy
import hashlib
from pathlib import Path

import yaml


def read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def materialize(profile, output, diagnostic=False):
    selection = "diagnostic_profiles" if diagnostic else "profiles"
    config = read(Path(".github/cook/tier1.yml"))[selection][profile]
    output.mkdir(parents=True, exist_ok=True)
    basic_path = Path(config["basic_source"])
    source = read(basic_path)["testlist"]
    if not diagnostic and [entry["test"] for entry in source] != config["basic_tests"]:
        raise ValueError(
            "Thales base list changed; review the complete supported scope"
        )
    by_name = {entry["test"]: entry for entry in source}
    basic = [copy.deepcopy(by_name[name]) for name in config["basic_tests"]]
    sources = [basic_path, Path(".github/cook/tier1.yml")]
    arch = []
    if diagnostic:
        hello_path = Path("verif/tests/testlist_verilator_testharness_smoke.yaml")
        hello = copy.deepcopy(read(hello_path)["testlist"][0])
        hello["gcc_opts"] += " -nostdlib -lgcc"
        basic.append(hello)
        arch_path = Path(config["arch_source"])
        arch = copy.deepcopy(read(arch_path)["testlist"])
        sources.extend((hello_path, arch_path))
    # Legacy RV64 lists repeat lb-align01. Preserve both invocations without
    # overwriting a compiled ELF or hiding the duplicate from the evidence.
    seen, renamed = {}, []
    for entry in arch:
        name = entry["test"]
        if name in seen:
            if entry != seen[name]:
                raise ValueError(f"Conflicting legacy test definitions: {name}")
            entry["test"] = name + "-repeat2"
            renamed.append({"source_name": name, "cook_name": entry["test"]})
        else:
            seen[name] = copy.deepcopy(entry)
    count = sum(entry.get("iterations", 1) for entry in arch)
    if diagnostic and count != config["arch_enabled"]:
        raise ValueError(f"Legacy enabled count changed: {count}")
    lists = {}
    suites = [("basic", basic)]
    if diagnostic:
        suites.append(("arch", arch))
    for suite, entries in suites:
        for entry in entries:
            entry["march"], entry["mabi"] = config["march"], config["mabi"]
            # GCC builtins used by the legacy VM runtime must appear after sources.
            if (
                suite == "basic"
                and profile == "rv64"
                and "-lgcc" not in entry["gcc_opts"]
            ):
                entry["gcc_opts"] += " -lgcc"
        path = output / f"{profile}-{suite}.yaml"
        path.write_text(
            yaml.safe_dump({"testlist": entries}, sort_keys=False), encoding="utf-8"
        )
        lists[suite] = str(path)
    provenance = {
        "profile": profile,
        "selection": selection,
        **config,
        "lists": lists,
        "renamed_duplicate_invocations": renamed,
        "sources": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources
        },
        "notes": [
            "Existing assembly sources, compiler options, iterations and runtimes are retained.",
            "Target linker is selected by Cook; compiler ISA/ABI are explicit in tier1.yml.",
            "Live comparison only; no independent Spike or offline trace comparison.",
        ],
    }
    (output / f"{profile}-provenance.yml").write_text(
        yaml.safe_dump(provenance, sort_keys=False), encoding="utf-8"
    )
    return config, lists


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("rv32", "rv64"), required=True)
    parser.add_argument("--output", type=Path, default=Path("ci-results/testlists"))
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    materialize(args.profile, args.output, diagnostic=args.diagnostic)
