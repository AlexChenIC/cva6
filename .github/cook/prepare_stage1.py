# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0
"""Materialize finite reviewed suites; preserve source/runtime and hash provenance."""

import copy
import hashlib
from pathlib import Path

import yaml


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
    config_path = Path(".github/cook/stage1.yml")
    config = yaml.safe_load(config_path.read_text())[selection][profile]
    output.mkdir(parents=True, exist_ok=True)
    lists, seen = {}, set()
    hashes = {str(config_path): hashlib.sha256(config_path.read_bytes()).hexdigest()}
    for suite, spec in config["suites"].items():
        path = Path(spec["source"])
        data = yaml.safe_load(path.read_text())
        planned = names(data)
        if len(planned) != spec["enabled"] or seen.intersection(planned):
            raise ValueError("Reviewed count changed or cross-suite ELF names collide")
        seen.update(planned)
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        data = copy.deepcopy(data)
        for entry in data["testlist"]:
            entry.update(march=spec.get("march", config["march"]), mabi=config["mabi"])
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
                sources=hashes,
            ),
            sort_keys=False,
        )
    )
    return config, lists
