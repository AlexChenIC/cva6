# Copyright 2026 OpenHW Foundation
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
"""Native live-comparison evidence for the Verilator TestHarness."""

import hashlib
import stat

import yaml


def testharness_mode(tandem_enabled):
    return "sim_rtl_verilator_testharness" + ("_tandem" if tandem_enabled else "")


def read_tandem_report(path):
    """A successful RTL run is insufficient without an active native comparison."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Tandem report must be a regular file")
    result = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Missing or malformed native tandem report")
    for key in ("exit_code", "instr_count", "csrs_match_count", "mismatches_count"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError(f"Invalid native tandem field: {key}")
    if (
        result.get("exit_cause") != "SUCCESS"
        or result["exit_code"] != 0
        or result["instr_count"] == 0
        or result["mismatches_count"] != 0
        or "mismatches" not in result
        or result["mismatches"] not in (None, [])
        or result.get("mismatch_description") != ""
    ):
        raise ValueError(
            f"Native tandem failed: cause={result.get('exit_cause')}, "
            f"compared={result['instr_count']}, mismatches={result['mismatches_count']}"
        )
    return result


def snapshot_spike_config(repo, target, output):
    """Use target parameters unchanged, or the existing RTL-derived defaults."""
    source = repo / "config" / "target" / target / "spike.yaml"
    metadata = {"mode": "rtl-derived"}
    snapshot = None
    if source.exists() or source.is_symlink():
        if not stat.S_ISREG(source.lstat().st_mode):
            raise ValueError(f"Spike configuration must be a regular file: {source}")
        content = source.read_bytes()
        data = yaml.safe_load(content)
        if not isinstance(data, dict) or not isinstance(
            data.get("spike_param_tree"), dict
        ):
            raise ValueError(f"Invalid Spike parameter tree: {source}")
        snapshot = output / "spike-config.yaml"
        snapshot.write_bytes(content)
        metadata = {
            "mode": "target-yaml",
            "source": str(source.relative_to(repo)),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    (output / "spike-config-source.yml").write_text(
        yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
    )
    return snapshot
