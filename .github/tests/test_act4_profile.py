# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from flows.act4 import profile as PROFILE  # noqa: E402

PROFILE_ROOT = REPO_ROOT / "verif/tests/act4/cv32a65x_axi"
CHECKED_LOCK = PROFILE_ROOT / "generation-lock.json"
CHECKED_OVERLAY = PROFILE_ROOT / "profile-overlay.json"
ASSETS = PROFILE_ROOT / "profile"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Act4ProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.act4 = self.root / "riscv-arch-test"
        self.act_profile = self.act4 / "config/cores/cva6/cv32a65x"
        self.act_profile.mkdir(parents=True)
        self.shared_profile = self.act4 / "config/cores/cva6"

        extensions = [
            "I",
            "M",
            "C",
            "Zba",
            "Zbb",
            "Zbs",
            "Zca",
            "Zbc",
            "Zcb",
            "Zicsr",
            "Sm",
        ]
        base_udb = {
            "$schema": "config_schema.json#",
            "kind": "architecture configuration",
            "type": "fully configured",
            "name": "cv32a65x",
            "description": "unit-test ACT base profile",
            "implemented_extensions": [
                {"name": name, "version": "= 1.0.0"} for name in extensions
            ],
            "params": {
                "MXLEN": 32,
                "NUM_PMP_ENTRIES": 0,
                "HPM_COUNTER_EN": [True, False, True] + [False] * 29,
            },
        }
        base_sail = {
            "base": {
                "xlen": 32,
                "writable_misa": False,
                "writable_hpm_counters": {"len": 32, "value": "0x0000_0005"},
            },
            "memory": {
                "pmp": {
                    "grain": 0,
                    "count": 0,
                    "usable_count": 0,
                    "tor_supported": False,
                    "na4_supported": False,
                    "napot_supported": False,
                },
                "regions": [
                    {
                        "base": {"len": 64, "value": "0x10000000"},
                        "size": {"len": 64, "value": "0x00001000"},
                        "attributes": {
                            "mem_type": "IOMemory",
                            "cacheable": False,
                            "coherent": True,
                            "executable": False,
                            "readable": True,
                            "writable": True,
                        },
                        "include_in_device_tree": False,
                    },
                    {
                        "base": {"len": 64, "value": "0x80000000"},
                        "size": {"len": 64, "value": "0x00010000"},
                        "attributes": {
                            "mem_type": "MainMemory",
                            "cacheable": True,
                            "coherent": True,
                            "executable": True,
                            "readable": True,
                            "writable": True,
                        },
                        "include_in_device_tree": True,
                    },
                ],
            },
            "platform": {"simple_interrupt_generator": {"supported": False, "base": 0}},
            "extensions": {
                "S": {"supported": False},
                "U": {"supported": False},
                "Zifencei": {"supported": False},
            },
        }
        base_test_config = {
            "name": "cv32a65x",
            "compiler_exe": "riscv64-unknown-elf-gcc",
            "objdump_exe": "riscv64-unknown-elf-objdump",
            "ref_model_exe": "sail_riscv_sim",
            "udb_config": "cv32a65x.yaml",
            "linker_script": "link.ld",
            "dut_include_dir": ".",
        }

        (self.act_profile / "cv32a65x.yaml").write_text(
            json.dumps(base_udb, indent=2) + "\n", encoding="utf-8"
        )
        # Exercise comment removal as well as JSON parsing.
        sail_text = json.dumps(base_sail, indent=2).replace(
            '"base": {', '// pinned ACT comment\n  "base": {', 1
        )
        (self.act_profile / "sail.json").write_text(sail_text + "\n", encoding="utf-8")
        (self.act_profile / "test_config.yaml").write_text(
            json.dumps(base_test_config, indent=2) + "\n", encoding="utf-8"
        )
        (self.shared_profile / "link.ld").write_text(
            (ASSETS / "link.ld").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (self.shared_profile / "rvmodel_macros.h").write_text(
            (ASSETS / "rvmodel_macros.h").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        subprocess.run(["git", "init", "-q", str(self.act4)], check=True)
        subprocess.run(
            ["git", "-C", str(self.act4), "config", "user.name", "ACT profile test"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.act4),
                "config",
                "user.email",
                "act-profile-test@example.invalid",
            ],
            check=True,
        )
        subprocess.run(["git", "-C", str(self.act4), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.act4), "commit", "-q", "-m", "fixture"],
            check=True,
        )
        self.head = subprocess.run(
            ["git", "-C", str(self.act4), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        self.lock = deepcopy(json.loads(CHECKED_LOCK.read_text(encoding="utf-8")))
        self.lock["act4"]["commit"] = self.head
        for label, entry in self.lock["act4"]["files"].items():
            entry["sha256"] = sha256(self.act4 / entry["path"])
        self.lock_path = self.root / "generation-lock.json"
        self.write_lock()

    def write_lock(self) -> None:
        self.lock_path.write_text(
            json.dumps(self.lock, indent=2) + "\n", encoding="utf-8"
        )

    def resolve(self, output: Path | None = None, **kwargs):
        return PROFILE.resolve_profile(
            self.act4,
            output or self.root / "resolved",
            lock_path=self.lock_path,
            overlay_path=kwargs.pop("overlay_path", CHECKED_OVERLAY),
            assets_dir=ASSETS,
            **kwargs,
        )

    def test_checked_in_lock_and_overlay_capture_reviewed_contract(self) -> None:
        lock = PROFILE.load_generation_lock(CHECKED_LOCK)
        overlay = PROFILE.load_overlay(CHECKED_OVERLAY)

        self.assertEqual(
            lock["act4"]["commit"], "ffb1fffc78b264c6c0a0676532d89eaa2e8d8918"
        )
        self.assertEqual(
            lock["act4"]["files"]["linker_script"]["path"], "config/cores/cva6/link.ld"
        )
        self.assertEqual(
            lock["act4"]["files"]["rvmodel_macros"]["path"],
            "config/cores/cva6/rvmodel_macros.h",
        )
        self.assertEqual(
            lock["generation_environment"]["container"]["digest"],
            "sha256:3167a1e637af1ee068b3c2d14ef890689628490f469e5ac1b8238b1ecaa61a6d",
        )
        self.assertEqual(
            lock["generation_environment"]["observed_tools"],
            {
                "gcc": "16.1.0",
                "binutils": "2.46",
                "sail": "0.13.1",
                "mise": "2026.7.0",
                "uv": "0.11.33",
                "ruby": "3.4.10",
                "bundler": "4.0.18",
            },
        )
        self.assertFalse(overlay["generation"]["include_priv_tests"])
        self.assertEqual(overlay["generation"]["requested_suites"], "auto")
        self.assertIn("Zcmt", overlay["generation"]["known_suite_gaps"])
        self.assertIn("Zmmul", overlay["generation"]["declared_extensions"])
        self.assertIn("Sm", overlay["generation"]["declared_extensions"])
        self.assertEqual(
            set(lock["cva6"]["files"]),
            {"rtl_config", "isa_config", "spike_config"},
        )
        for entry in lock["cva6"]["files"].values():
            self.assertEqual(sha256(REPO_ROOT / entry["path"]), entry["sha256"])
        additions = {
            entry["name"]: entry["version"]
            for entry in overlay["implemented_extensions_add"]
        }
        self.assertEqual(additions["Zmmul"], "= 1.0.0")
        self.assertEqual(overlay["udb_updates"]["params"]["PMP_GRANULARITY"], 3)
        self.assertEqual(overlay["udb_updates"]["params"]["NUM_PMP_ENTRIES"], 16)
        self.assertEqual(overlay["udb_updates"]["params"]["NUM_USABLE_PMP_ENTRIES"], 8)
        self.assertEqual(overlay["udb_updates"]["params"]["JVT_BASE_MASK"], 0x7FFFFFC0)
        self.assertEqual(overlay["sail_updates"]["memory"]["pmp"]["grain"], 1)
        self.assertEqual(
            overlay["sail_memory_regions_append"][0]["size"]["value"],
            "0x00001000",
        )
        self.assertEqual(
            sha256(ASSETS / "link.ld"), lock["act4"]["files"]["linker_script"]["sha256"]
        )
        self.assertEqual(
            sha256(ASSETS / "rvmodel_macros.h"),
            lock["act4"]["files"]["rvmodel_macros"]["sha256"],
        )

    def test_resolves_profile_and_leaves_external_checkout_unchanged(self) -> None:
        before = {
            entry["path"]: sha256(self.act4 / entry["path"])
            for entry in self.lock["act4"]["files"].values()
        }
        resolved = self.resolve()

        udb = yaml.safe_load(resolved.udb_config.read_text(encoding="utf-8"))
        sail = json.loads(resolved.sail_config.read_text(encoding="utf-8"))
        test_config = yaml.safe_load(resolved.test_config.read_text(encoding="utf-8"))
        manifest = json.loads(resolved.manifest.read_text(encoding="utf-8"))

        self.assertEqual(udb["name"], "cv32a65x_axi")
        self.assertEqual(udb["params"]["PMP_GRANULARITY"], 3)
        self.assertEqual(udb["params"]["NUM_PMP_ENTRIES"], 16)
        self.assertEqual(udb["params"]["NUM_USABLE_PMP_ENTRIES"], 8)
        self.assertEqual(udb["params"]["JVT_BASE_TYPE"], "mask")
        self.assertFalse(udb["params"]["JVT_READ_ONLY"])
        self.assertEqual(udb["params"]["JVT_BASE_MASK"], 0x7FFFFFC0)
        self.assertEqual(udb["params"]["HPM_COUNTER_EN"], [False] * 32)
        extensions = {
            entry["name"]: entry["version"] for entry in udb["implemented_extensions"]
        }
        self.assertEqual(extensions["Zmmul"], "= 1.0.0")
        self.assertEqual(sail["memory"]["pmp"]["grain"], 1)
        self.assertEqual(sail["memory"]["pmp"]["count"], 16)
        self.assertEqual(sail["memory"]["pmp"]["usable_count"], 8)
        self.assertEqual(
            sail["platform"]["simple_interrupt_generator"],
            {"supported": True, "base": 0x15000000},
        )
        sig_regions = [
            region
            for region in sail["memory"]["regions"]
            if int(region["base"]["value"], 0) == 0x15000000
        ]
        self.assertEqual(len(sig_regions), 1)
        self.assertEqual(int(sig_regions[0]["size"]["value"], 0), 0x1000)
        region_bases = [
            int(region["base"]["value"], 0) for region in sail["memory"]["regions"]
        ]
        self.assertEqual(region_bases, sorted(region_bases))
        self.assertLess(region_bases.index(0x10000000), region_bases.index(0x15000000))
        self.assertLess(region_bases.index(0x15000000), region_bases.index(0x80000000))
        sig_end = 0x15000000 + 0x1000
        other_bounds = [
            (
                int(region["base"]["value"], 0),
                int(region["base"]["value"], 0) + int(region["size"]["value"], 0),
            )
            for region in sail["memory"]["regions"]
            if int(region["base"]["value"], 0) != 0x15000000
        ]
        self.assertTrue(
            all(sig_end <= start or end <= 0x15000000 for start, end in other_bounds)
        )
        self.assertFalse(test_config["include_priv_tests"])
        self.assertEqual(test_config["ref_model_type"], "sail")
        self.assertNotIn("15000000", resolved.rvmodel_macros.read_text().lower())
        self.assertFalse(
            manifest["sail_reference_only_mmio"]["simple_interrupt_generator"][
                "present_in_dut_macros"
            ]
        )
        self.assertEqual(
            manifest["sail_reference_only_mmio"]["simple_interrupt_generator"]["size"],
            0x1000,
        )
        self.assertIn("Zcmt", manifest["generation_scope"]["known_suite_gaps"])
        self.assertEqual(
            manifest["generation_environment"]["container"]["digest"],
            self.lock["generation_environment"]["container"]["digest"],
        )

        after = {
            entry["path"]: sha256(self.act4 / entry["path"])
            for entry in self.lock["act4"]["files"].values()
        }
        self.assertEqual(after, before)
        status = subprocess.run(
            ["git", "-C", str(self.act4), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertEqual(status, "")

    def test_rejects_commit_and_base_hash_mismatches(self) -> None:
        self.lock["act4"]["commit"] = "0" * 40
        self.write_lock()
        with self.assertRaisesRegex(PROFILE.ProfileError, "ACT commit mismatch"):
            self.resolve(self.root / "wrong-commit")

        self.lock["act4"]["commit"] = self.head
        self.lock["act4"]["files"]["sail"]["sha256"] = "0" * 64
        self.write_lock()
        with self.assertRaisesRegex(
            PROFILE.ProfileError, "base hash mismatch for sail"
        ):
            self.resolve(self.root / "wrong-hash")

    def test_rejects_dirty_act_checkout_and_cva6_source_mismatch(self) -> None:
        untracked = self.act4 / "tests/unlocked-generator.py"
        untracked.parent.mkdir()
        untracked.write_text("raise SystemExit(99)\n", encoding="utf-8")
        with self.assertRaisesRegex(PROFILE.ProfileError, "ACT checkout must be clean"):
            self.resolve(self.root / "untracked-act")
        untracked.unlink()

        tracked = self.act_profile / "cv32a65x.yaml"
        tracked.write_text(
            tracked.read_text(encoding="utf-8") + "# dirty\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(PROFILE.ProfileError, "ACT checkout must be clean"):
            self.resolve(self.root / "dirty-act")

        self.lock["cva6"]["files"]["rtl_config"]["sha256"] = "0" * 64
        self.write_lock()
        subprocess.run(
            [
                "git",
                "-C",
                str(self.act4),
                "restore",
                "config/cores/cva6/cv32a65x/cv32a65x.yaml",
            ],
            check=True,
        )
        with self.assertRaisesRegex(
            PROFILE.ProfileError, "CVA6 architecture-source hash mismatch"
        ):
            self.resolve(self.root / "wrong-cva6-hash")

    def test_rejects_output_inside_external_checkout(self) -> None:
        with self.assertRaisesRegex(PROFILE.ProfileError, "outside the read-only ACT"):
            self.resolve(self.act4 / "generated-profile")
        self.assertFalse((self.act4 / "generated-profile").exists())

    def test_rejects_privileged_or_overlapping_overlay(self) -> None:
        overlay = json.loads(CHECKED_OVERLAY.read_text(encoding="utf-8"))
        overlay["generation"]["include_priv_tests"] = True
        privileged = self.root / "privileged-overlay.json"
        privileged.write_text(json.dumps(overlay), encoding="utf-8")
        with self.assertRaisesRegex(PROFILE.ProfileError, "include_priv_tests=false"):
            self.resolve(self.root / "privileged", overlay_path=privileged)

        overlay = json.loads(CHECKED_OVERLAY.read_text(encoding="utf-8"))
        overlay["sail_memory_regions_append"][0]["base"]["value"] = "0x10000004"
        overlapping = self.root / "overlapping-overlay.json"
        overlapping.write_text(json.dumps(overlay), encoding="utf-8")
        with self.assertRaisesRegex(PROFILE.ProfileError, "overlaps existing region"):
            self.resolve(self.root / "overlapping", overlay_path=overlapping)

        overlay = json.loads(CHECKED_OVERLAY.read_text(encoding="utf-8"))
        overlay["sail_memory_regions_append"][0]["size"]["value"] = "0x00002000"
        oversized = self.root / "oversized-sig-overlay.json"
        oversized.write_text(json.dumps(overlay), encoding="utf-8")
        with self.assertRaisesRegex(PROFILE.ProfileError, "4 KiB memory region"):
            self.resolve(self.root / "oversized-sig", overlay_path=oversized)

    def test_comment_stripper_preserves_comment_tokens_inside_strings(self) -> None:
        source = '{\n  // comment\n  "url": "https://example.invalid/a/*b*/", /* block */\n  "n": 1\n}\n'
        self.assertEqual(
            json.loads(PROFILE._strip_json_comments(source)),
            {"url": "https://example.invalid/a/*b*/", "n": 1},
        )

    def test_module_cli_is_warning_free(self) -> None:
        output = self.root / "cli-resolved"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "flows.act4.profile",
                "--act4-root",
                str(self.act4),
                "--output-dir",
                str(output),
                "--lock",
                str(self.lock_path),
                "--overlay",
                str(CHECKED_OVERLAY),
                "--assets-dir",
                str(ASSETS),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertNotIn("RuntimeWarning", result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            Path(result.stdout.strip()).resolve(),
            (output / "resolved-profile.json").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
