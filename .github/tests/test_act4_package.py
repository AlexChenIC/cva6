# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

from flows.act4.corpus import MANIFEST_FILENAME, prepare_corpus
from flows.act4 import package as packager

TARGET = "cv32a65x_axi"
ACT_COMMIT = "a" * 40
CVA6_COMMIT = "b" * 40
IMAGE_DIGEST = "sha256:" + "c" * 64


class Act4PackageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.elf_root = self.root / "act-work/elfs"
        self.elf_root.mkdir(parents=True)
        self.profile = self.root / "resolved-profile.json"
        self.write_profile()

    def write_profile(
        self,
        *,
        target: str = TARGET,
        act_commit: str = ACT_COMMIT,
        cva6_commit: str = CVA6_COMMIT,
        image_digest: str = IMAGE_DIGEST,
    ) -> None:
        document = {
            "schema_version": 1,
            "target": target,
            "act4": {"commit": act_commit},
            "cva6": {"baseline_commit": cva6_commit},
            "generation_environment": {
                "container": {
                    "digest": image_digest,
                    "platform": "linux/arm64",
                },
            },
        }
        self.profile.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def write_elf(self, relative: str, payload: bytes = b"test") -> Path:
        path = self.elf_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x7fELF" + payload)
        return path

    def package(self, output: Path, **overrides):
        arguments = {
            "target": TARGET,
            "act_commit": ACT_COMMIT,
            "cva6_commit": CVA6_COMMIT,
            "image_digest": IMAGE_DIGEST,
            "replace": False,
        }
        arguments.update(overrides)
        return packager.package_corpus(
            self.elf_root,
            self.profile,
            output,
            **arguments,
        )

    def test_output_is_deterministic_and_validator_compatible(self) -> None:
        second = self.write_elf("z/Z-xor-00.elf", b"xor")
        first = self.write_elf("a/I-add-00.elf", b"add")
        output_one = self.root / "corpus-one"
        packaged_one = self.package(output_one)

        os.utime(first, (2_000_000_000, 2_000_000_000))
        os.utime(second, (1_000_000_000, 1_000_000_000))
        output_two = self.root / "corpus-two"
        packaged_two = self.package(output_two)

        self.assertEqual(
            packaged_one.archive_path.read_bytes(),
            packaged_two.archive_path.read_bytes(),
        )
        self.assertEqual(
            packaged_one.manifest_path.read_bytes(),
            packaged_two.manifest_path.read_bytes(),
        )
        self.assertEqual(packaged_one.test_count, 2)

        document = json.loads(packaged_one.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [entry["id"] for entry in document["tests"]],
            ["I-add-00", "Z-xor-00"],
        )
        self.assertEqual(
            [entry["elf"] for entry in document["tests"]],
            ["elfs/I-add-00.elf", "elfs/Z-xor-00.elf"],
        )
        self.assertEqual(
            [entry["source"] for entry in document["tests"]],
            ["I-add-00.S", "Z-xor-00.S"],
        )
        self.assertEqual(
            document["generation"]["profile_sha256"],
            hashlib.sha256(self.profile.read_bytes()).hexdigest(),
        )
        self.assertEqual(document["generation"]["image_platform"], "linux/arm64")
        self.assertEqual(
            packaged_one.resolved_profile_path.read_bytes(), self.profile.read_bytes()
        )

        prepared = prepare_corpus(
            output_one, self.root / "validated", expected_target=TARGET
        )
        self.assertEqual(len(prepared.tests), 2)

        with tarfile.open(packaged_one.archive_path, "r:gz") as archive:
            members = archive.getmembers()
        self.assertEqual(
            [member.name for member in members],
            ["elfs", "elfs/I-add-00.elf", "elfs/Z-xor-00.elf"],
        )
        for member in members:
            self.assertEqual(member.uid, 0)
            self.assertEqual(member.gid, 0)
            self.assertEqual(member.uname, "")
            self.assertEqual(member.gname, "")
            self.assertEqual(member.mtime, 0)
        self.assertEqual(members[0].mode, 0o755)
        self.assertTrue(all(member.mode == 0o444 for member in members[1:]))

    def test_zero_final_elf_fails_closed(self) -> None:
        (self.elf_root / "README.txt").write_text("not a test", encoding="utf-8")

        with self.assertRaisesRegex(packager.PackageError, "zero final"):
            self.package(self.root / "corpus")

    def test_duplicate_flattened_elf_and_test_id_fail_closed(self) -> None:
        self.write_elf("one/I-add-00.elf")
        self.write_elf("two/I-add-00.elf")

        with self.assertRaisesRegex(packager.PackageError, "Duplicate ACT test id"):
            self.package(self.root / "corpus")

    def test_signature_elf_and_symlink_are_rejected(self) -> None:
        self.write_elf("I-add-00.sig.elf")
        with self.assertRaisesRegex(packager.PackageError, "not a final ELF"):
            self.package(self.root / "signature-corpus")

        (self.elf_root / "I-add-00.sig.elf").unlink()
        real = self.write_elf("real/I-add-00.elf")
        symlink = self.elf_root / "linked.elf"
        try:
            symlink.symlink_to(real)
        except OSError as error:
            self.skipTest(f"symlinks unavailable: {error}")
        with self.assertRaisesRegex(packager.PackageError, "Symlink file"):
            self.package(self.root / "symlink-corpus")

    def test_profile_provenance_mismatches_fail_closed(self) -> None:
        self.write_elf("I-add-00.elf")
        cases = (
            ("act", {"act_commit": "d" * 40}, "ACT commit"),
            ("cva6", {"cva6_commit": "e" * 40}, "CVA6 commit"),
            (
                "image",
                {"image_digest": "sha256:" + "f" * 64},
                "image digest",
            ),
        )
        for label, overrides, message in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(packager.PackageError, message):
                    self.package(self.root / f"corpus-{label}", **overrides)

        self.write_profile(target="cv32a60x_axi")
        with self.assertRaisesRegex(packager.PackageError, "target mismatch"):
            self.package(self.root / "corpus-target")

    def test_generation_commits_must_be_full_lowercase_sha1(self) -> None:
        self.write_elf("I-add-00.elf")
        invalid_commits = ("a" * 39, "a" * 41, "A" * 40, "g" * 40)
        for commit in invalid_commits:
            with self.subTest(commit=commit):
                with self.assertRaisesRegex(
                    packager.PackageError, "full lowercase 40-character"
                ):
                    self.package(self.root / "corpus", act_commit=commit)

    def test_existing_output_requires_explicit_replace(self) -> None:
        self.write_elf("I-add-00.elf")
        output = self.root / "corpus"
        first = self.package(output)

        with self.assertRaisesRegex(packager.PackageError, "replace=True"):
            self.package(output)
        second = self.package(output, replace=True)
        self.assertEqual(first.archive_sha256, second.archive_sha256)
        self.assertTrue((output / MANIFEST_FILENAME).is_file())


if __name__ == "__main__":
    unittest.main()
