# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from flows.act4 import corpus

TARGET = "cv32a65x_axi"
ARCHIVE_NAME = f"act4-elfs-{TARGET}.tar.gz"


class Act4CorpusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write_archive(self, members: list[tuple[str, bytes, str]]) -> Path:
        archive_path = self.root / ARCHIVE_NAME
        with tarfile.open(archive_path, "w:gz") as archive:
            for name, content, kind in members:
                member = tarfile.TarInfo(name)
                if kind == "file":
                    member.size = len(content)
                    archive.addfile(member, BytesIO(content))
                elif kind == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "../outside"
                    archive.addfile(member)
                else:
                    raise AssertionError(f"Unknown fixture type: {kind}")
        return archive_path

    def write_manifest(
        self,
        archive_path: Path,
        tests: list[dict[str, object]],
        *,
        target: str = TARGET,
        archive_sha256: str | None = None,
    ) -> Path:
        archive_hash = (
            archive_sha256 or hashlib.sha256(archive_path.read_bytes()).hexdigest()
        )
        profile_path = self.root / corpus.RESOLVED_PROFILE_FILENAME
        if not profile_path.exists():
            profile_path.write_text(
                json.dumps({"schema_version": 1, "target": target}) + "\n",
                encoding="utf-8",
            )
        profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        document = {
            "schema_version": 1,
            "target": target,
            "scope": "basic-architectural-subset",
            "certification_claim": False,
            "archive": {"name": ARCHIVE_NAME, "sha256": archive_hash},
            "generation": {
                "act_commit": "a" * 40,
                "cva6_commit": "b" * 40,
                "profile_sha256": profile_hash,
                "image_digest": "sha256:" + "d" * 64,
                "image_platform": "linux/arm64",
            },
            "tests": tests,
        }
        manifest = self.root / corpus.MANIFEST_FILENAME
        manifest.write_text(json.dumps(document), encoding="utf-8")
        return manifest

    @staticmethod
    def manifest_entry(content: bytes = b"ELF fixture") -> dict[str, object]:
        return {
            "id": "I-add-01",
            "elf": "elfs/I-add-01.elf",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
            "source": "I-add-01.S",
        }

    def test_prepares_integrity_verified_nonempty_corpus(self) -> None:
        content = b"ELF fixture"
        archive = self.write_archive([("elfs/I-add-01.elf", content, "file")])
        self.write_manifest(archive, [self.manifest_entry(content)])

        prepared = corpus.prepare_corpus(
            self.root, self.root / "extracted", expected_target=TARGET
        )

        self.assertEqual(len(prepared.tests), 1)
        self.assertEqual(prepared.tests[0].path.read_bytes(), content)
        self.assertEqual(prepared.tests[0].spec.expected_source, "I-add-01.S")

    def test_target_mismatch_fails_closed(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"ELF fixture", "file")])
        manifest = self.write_manifest(archive, [self.manifest_entry()])

        with self.assertRaisesRegex(corpus.ManifestError, "target mismatch"):
            corpus.load_manifest(manifest, expected_target="cv32a60x_axi")

    def test_zero_test_manifest_fails_closed(self) -> None:
        archive = self.write_archive([])
        manifest = self.write_manifest(archive, [])

        with self.assertRaisesRegex(corpus.ManifestError, "zero tests"):
            corpus.load_manifest(manifest, expected_target=TARGET)

    def test_zero_size_elf_and_duplicate_entries_fail_closed(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"ELF fixture", "file")])
        zero = self.manifest_entry()
        zero["size"] = 0
        manifest = self.write_manifest(archive, [zero])
        with self.assertRaisesRegex(corpus.ManifestError, "outside the allowed"):
            corpus.load_manifest(manifest, expected_target=TARGET)

        duplicate = self.manifest_entry()
        manifest = self.write_manifest(archive, [duplicate, dict(duplicate)])
        with self.assertRaisesRegex(corpus.ManifestError, "duplicate test ids"):
            corpus.load_manifest(manifest, expected_target=TARGET)

    def test_generation_commits_must_be_exact_full_sha1(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"ELF fixture", "file")])
        manifest = self.write_manifest(archive, [self.manifest_entry()])
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["generation"]["act_commit"] = "a" * 64
        manifest.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(corpus.ManifestError, "full Git SHA"):
            corpus.load_manifest(manifest, expected_target=TARGET)

    def test_generation_image_digest_must_be_pinned_sha256(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"ELF fixture", "file")])
        manifest = self.write_manifest(archive, [self.manifest_entry()])
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["generation"]["image_digest"] = "latest"
        manifest.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(corpus.ManifestError, "sha256:<64"):
            corpus.load_manifest(manifest, expected_target=TARGET)

    def test_archive_hash_mismatch_fails_before_extraction(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"ELF fixture", "file")])
        self.write_manifest(archive, [self.manifest_entry()], archive_sha256="0" * 64)

        with self.assertRaisesRegex(corpus.ExtractionError, "SHA-256 mismatch"):
            corpus.prepare_corpus(
                self.root, self.root / "extracted", expected_target=TARGET
            )
        self.assertFalse((self.root / "extracted").exists())

    def test_resolved_profile_hash_mismatch_fails_before_extraction(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"ELF fixture", "file")])
        self.write_manifest(archive, [self.manifest_entry()])
        (self.root / corpus.RESOLVED_PROFILE_FILENAME).write_text(
            "tampered\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(corpus.CorpusError, "profile SHA-256 mismatch"):
            corpus.prepare_corpus(
                self.root, self.root / "extracted", expected_target=TARGET
            )
        self.assertFalse((self.root / "extracted").exists())

    def test_per_elf_hash_mismatch_removes_partial_extraction(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"corrupted", "file")])
        entry = self.manifest_entry(b"expected!")
        # Keep the declared size equal so the content hash is the failing gate.
        self.assertEqual(entry["size"], len(b"corrupted"))
        self.write_manifest(archive, [entry])

        with self.assertRaisesRegex(corpus.ExtractionError, "SHA-256 mismatch"):
            corpus.prepare_corpus(
                self.root, self.root / "extracted", expected_target=TARGET
            )
        self.assertFalse((self.root / "extracted").exists())

    def test_path_traversal_member_is_rejected(self) -> None:
        content = b"ELF fixture"
        archive = self.write_archive(
            [
                ("elfs/I-add-01.elf", content, "file"),
                ("../escape", b"bad", "file"),
            ]
        )
        self.write_manifest(archive, [self.manifest_entry(content)])

        with self.assertRaisesRegex(corpus.ExtractionError, "Unsafe archive"):
            corpus.prepare_corpus(
                self.root, self.root / "extracted", expected_target=TARGET
            )
        self.assertFalse((self.root / "escape").exists())

    def test_symlink_member_is_rejected(self) -> None:
        archive = self.write_archive([("elfs/I-add-01.elf", b"", "symlink")])
        self.write_manifest(archive, [self.manifest_entry(b"x")])

        with self.assertRaisesRegex(corpus.ExtractionError, "forbidden"):
            corpus.prepare_corpus(
                self.root, self.root / "extracted", expected_target=TARGET
            )

    def test_unexpected_archive_file_is_rejected(self) -> None:
        content = b"ELF fixture"
        archive = self.write_archive(
            [
                ("elfs/I-add-01.elf", content, "file"),
                ("unexpected.txt", b"bad", "file"),
            ]
        )
        self.write_manifest(archive, [self.manifest_entry(content)])

        with self.assertRaisesRegex(corpus.ExtractionError, "Unexpected file"):
            corpus.prepare_corpus(
                self.root, self.root / "extracted", expected_target=TARGET
            )

    def test_member_limit_is_streamed_without_getmembers(self) -> None:
        content = b"ELF fixture"
        archive_path = self.root / ARCHIVE_NAME
        with tarfile.open(archive_path, "w:gz") as archive:
            directory = tarfile.TarInfo("elfs")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
            expected = tarfile.TarInfo("elfs/I-add-01.elf")
            expected.size = len(content)
            archive.addfile(expected, BytesIO(content))
            extra = tarfile.TarInfo("unexpected.txt")
            extra.size = 1
            archive.addfile(extra, BytesIO(b"x"))
        self.write_manifest(archive_path, [self.manifest_entry(content)])

        with patch.object(
            tarfile.TarFile,
            "getmembers",
            side_effect=AssertionError("getmembers must not be used"),
        ):
            with self.assertRaisesRegex(corpus.ExtractionError, "unexpected members"):
                corpus.prepare_corpus(
                    self.root, self.root / "streamed", expected_target=TARGET
                )


if __name__ == "__main__":
    unittest.main()
