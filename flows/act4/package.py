"""Deterministically package final ACT4 ELFs for the routine CI runtime.

The packager belongs to the low-frequency generation path.  It does not run
Sail, build CVA6, execute tests, or interact with Git.  Its only outputs are a
deterministic tar.gz archive and the external version-one corpus manifest
consumed by :mod:`flows.act4.corpus`.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import tempfile
from typing import Any

from flows.act4.corpus import (
    MANIFEST_FILENAME,
    MAX_ELF_BYTES,
    MAX_TESTS,
    SCHEMA_VERSION,
    SCOPE,
    RESOLVED_PROFILE_FILENAME,
    prepare_corpus,
    sha256_file,
)

ARCHIVE_TEMPLATE = "act4-elfs-{target}.tar.gz"
SUPPORTED_TARGETS = frozenset({"cv32a65x_axi"})
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_COPY_CHUNK_BYTES = 1024 * 1024


class PackageError(ValueError):
    """Generation inputs cannot produce an integrity-verified runtime corpus."""


@dataclass(frozen=True)
class PackageInput:
    """One final ELF selected for the deterministic archive."""

    test_id: str
    source_path: Path
    archive_path: str
    sha256: str
    size: int
    source: str


@dataclass(frozen=True)
class PackagedCorpus:
    """Paths and identity of a completed corpus package."""

    manifest_path: Path
    archive_path: Path
    resolved_profile_path: Path
    archive_sha256: str
    test_count: int
    profile_sha256: str


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PackageError(f"Duplicate JSON key in resolved profile: {key}")
        value[key] = item
    return value


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PackageError(f"{context} must be a JSON object")
    return value


def _regular_file(path: Path, context: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise PackageError(f"Cannot access {context} {path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PackageError(f"{context} must be a regular non-symlink file: {path}")
    return metadata


def _validate_git_sha(value: str, context: str) -> None:
    if not isinstance(value, str) or not _GIT_SHA_RE.fullmatch(value):
        raise PackageError(f"{context} must be a full lowercase 40-character Git SHA")


def _load_profile(
    path: Path,
    *,
    target: str,
    act_commit: str,
    cva6_commit: str,
    image_digest: str,
) -> tuple[str, str]:
    metadata = _regular_file(path, "resolved profile")
    if metadata.st_size <= 0 or metadata.st_size > 16 * 1024 * 1024:
        raise PackageError("resolved-profile.json has an invalid size")
    try:
        profile_bytes = path.read_bytes()
        document = json.loads(
            profile_bytes.decode("utf-8"), object_pairs_hook=_no_duplicate_keys
        )
    except PackageError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PackageError(f"Cannot parse resolved profile {path}: {error}") from error

    profile = _mapping(document, "resolved profile")
    if profile.get("schema_version") != 1:
        raise PackageError("resolved profile schema_version must be 1")
    if profile.get("target") != target:
        raise PackageError(
            f"resolved profile target mismatch: expected {target}, "
            f"got {profile.get('target')}"
        )

    act4 = _mapping(profile.get("act4"), "resolved profile act4")
    if act4.get("commit") != act_commit:
        raise PackageError("ACT commit does not match resolved-profile.json")
    cva6 = _mapping(profile.get("cva6"), "resolved profile cva6")
    if cva6.get("baseline_commit") != cva6_commit:
        raise PackageError("CVA6 commit does not match resolved-profile.json")
    environment = _mapping(
        profile.get("generation_environment"),
        "resolved profile generation_environment",
    )
    container = _mapping(environment.get("container"), "resolved profile container")
    if container.get("digest") != image_digest:
        raise PackageError("image digest does not match resolved-profile.json")
    image_platform = container.get("platform")
    if image_platform not in {"linux/amd64", "linux/arm64"}:
        raise PackageError("resolved profile must pin a supported container platform")
    return hashlib.sha256(profile_bytes).hexdigest(), image_platform


def _discover_final_elfs(elf_directory: Path) -> tuple[PackageInput, ...]:
    try:
        root_metadata = elf_directory.lstat()
    except OSError as error:
        raise PackageError(
            f"Cannot access ELF directory {elf_directory}: {error}"
        ) from error
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise PackageError(
            f"ELF input must be a regular non-symlink directory: {elf_directory}"
        )

    discovered: list[Path] = []
    for directory, child_directories, filenames in os.walk(
        elf_directory, followlinks=False
    ):
        current = Path(directory)
        for child in child_directories:
            child_path = current / child
            if child_path.is_symlink():
                raise PackageError(f"Symlink directory in ELF input: {child_path}")
        for filename in filenames:
            path = current / filename
            if path.is_symlink():
                raise PackageError(f"Symlink file in ELF input: {path}")
            if filename.lower().endswith(".sig.elf"):
                raise PackageError(
                    f"Signature-producing ELF is not a final ELF: {path}"
                )
            if filename.lower().endswith(".elf"):
                discovered.append(path)

    if not discovered:
        raise PackageError("ACT ELF directory contains zero final .elf files")
    if len(discovered) > MAX_TESTS:
        raise PackageError(f"ACT ELF directory contains more than {MAX_TESTS} ELFs")

    by_id: dict[str, Path] = {}
    by_archive_path: dict[str, Path] = {}
    selected: list[PackageInput] = []
    for path in discovered:
        metadata = _regular_file(path, "ACT final ELF")
        if metadata.st_size <= 0 or metadata.st_size > MAX_ELF_BYTES:
            raise PackageError(
                f"ACT final ELF has invalid size {metadata.st_size}: {path}"
            )
        try:
            with path.open("rb") as stream:
                if stream.read(4) != b"\x7fELF":
                    raise PackageError(f"ACT final ELF has no ELF magic: {path}")
        except OSError as error:
            raise PackageError(f"Cannot read ACT final ELF {path}: {error}") from error

        test_id = path.stem
        if not _TEST_ID_RE.fullmatch(test_id):
            raise PackageError(f"Unsafe or unsupported ACT test id: {test_id}")
        archive_path = f"elfs/{path.name}"
        if len(archive_path.encode("ascii")) > 100:
            raise PackageError(
                f"ACT ELF path is too long for deterministic USTAR: {path}"
            )
        if test_id in by_id:
            raise PackageError(
                f"Duplicate ACT test id {test_id}: {by_id[test_id]} and {path}"
            )
        if archive_path in by_archive_path:
            raise PackageError(
                "Duplicate flattened ACT ELF path "
                f"{archive_path}: {by_archive_path[archive_path]} and {path}"
            )
        by_id[test_id] = path
        by_archive_path[archive_path] = path
        try:
            digest = sha256_file(path)
        except OSError as error:
            raise PackageError(f"Cannot hash ACT final ELF {path}: {error}") from error
        selected.append(
            PackageInput(
                test_id=test_id,
                source_path=path.resolve(strict=True),
                archive_path=archive_path,
                sha256=digest,
                size=metadata.st_size,
                source=f"{test_id}.S",
            )
        )
    return tuple(sorted(selected, key=lambda entry: entry.archive_path))


def _tar_info(name: str, *, size: int = 0, directory: bool = False) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
    info.size = 0 if directory else size
    info.mode = 0o755 if directory else 0o444
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    return info


def _write_deterministic_archive(path: Path, tests: tuple[PackageInput, ...]) -> None:
    try:
        with path.open("wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
                ) as archive:
                    archive.addfile(_tar_info("elfs", directory=True))
                    for test in tests:
                        with test.source_path.open("rb") as source:
                            archive.addfile(
                                _tar_info(test.archive_path, size=test.size), source
                            )
            raw.flush()
            os.fsync(raw.fileno())
    except (OSError, tarfile.TarError) as error:
        raise PackageError(
            f"Cannot create deterministic ACT4 archive: {error}"
        ) from error


def _manifest_document(
    *,
    target: str,
    archive_name: str,
    archive_sha256: str,
    profile_sha256: str,
    act_commit: str,
    cva6_commit: str,
    image_digest: str,
    image_platform: str,
    tests: tuple[PackageInput, ...],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "scope": SCOPE,
        "certification_claim": False,
        "archive": {"name": archive_name, "sha256": archive_sha256},
        "generation": {
            "act_commit": act_commit,
            "cva6_commit": cva6_commit,
            "profile_sha256": profile_sha256,
            "image_digest": image_digest,
            "image_platform": image_platform,
        },
        "tests": [
            {
                "id": test.test_id,
                "elf": test.archive_path,
                "sha256": test.sha256,
                "size": test.size,
                "source": test.source,
            }
            for test in tests
        ],
    }


def package_corpus(
    elf_directory: Path,
    resolved_profile: Path,
    output_directory: Path,
    *,
    target: str,
    act_commit: str,
    cva6_commit: str,
    image_digest: str,
    replace: bool = False,
) -> PackagedCorpus:
    """Create validator-compatible deterministic ACT4 runtime assets."""

    if target not in SUPPORTED_TARGETS:
        raise PackageError(f"Unsupported ACT4 package target: {target}")
    _validate_git_sha(act_commit, "act_commit")
    _validate_git_sha(cva6_commit, "cva6_commit")
    if not isinstance(image_digest, str) or not _IMAGE_DIGEST_RE.fullmatch(
        image_digest
    ):
        raise PackageError("image_digest must be sha256:<64 lowercase hex digits>")
    profile_sha256, image_platform = _load_profile(
        resolved_profile,
        target=target,
        act_commit=act_commit,
        cva6_commit=cva6_commit,
        image_digest=image_digest,
    )
    tests = _discover_final_elfs(elf_directory)

    archive_name = ARCHIVE_TEMPLATE.format(target=target)
    manifest_path = output_directory / MANIFEST_FILENAME
    archive_path = output_directory / archive_name
    resolved_profile_path = output_directory / RESOLVED_PROFILE_FILENAME
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(output_directory):
        metadata = output_directory.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise PackageError(
                f"Output must be a regular non-symlink directory: {output_directory}"
            )
    else:
        output_directory.mkdir(mode=0o755)

    existing = [
        path
        for path in (manifest_path, archive_path, resolved_profile_path)
        if os.path.lexists(path)
    ]
    if existing and not replace:
        raise PackageError(
            "Refusing to replace existing corpus output without replace=True: "
            + ", ".join(str(path) for path in existing)
        )

    with tempfile.TemporaryDirectory(
        prefix=".act4-package-", dir=output_directory.parent
    ) as temporary_name:
        staging = Path(temporary_name)
        staged_archive = staging / archive_name
        staged_manifest = staging / MANIFEST_FILENAME
        staged_profile = staging / RESOLVED_PROFILE_FILENAME
        try:
            with resolved_profile.open("rb") as source, staged_profile.open(
                "xb"
            ) as destination:
                while chunk := source.read(_COPY_CHUNK_BYTES):
                    destination.write(chunk)
        except OSError as error:
            raise PackageError(
                f"Cannot stage resolved ACT4 profile: {error}"
            ) from error
        _write_deterministic_archive(staged_archive, tests)
        archive_sha256 = sha256_file(staged_archive)
        document = _manifest_document(
            target=target,
            archive_name=archive_name,
            archive_sha256=archive_sha256,
            profile_sha256=profile_sha256,
            act_commit=act_commit,
            cva6_commit=cva6_commit,
            image_digest=image_digest,
            image_platform=image_platform,
            tests=tests,
        )
        staged_manifest.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        # Exercise the same public validator/extractor used by routine CI before
        # publishing either output file.
        prepare_corpus(staging, staging / "validation", expected_target=target)
        os.replace(staged_profile, resolved_profile_path)
        os.replace(staged_archive, archive_path)
        # Publish the manifest last.  If replacement is interrupted, the old
        # manifest cannot integrity-check a partially updated profile/archive,
        # so routine CI fails closed.
        os.replace(staged_manifest, manifest_path)

    return PackagedCorpus(
        manifest_path=manifest_path.resolve(strict=True),
        archive_path=archive_path.resolve(strict=True),
        resolved_profile_path=resolved_profile_path.resolve(strict=True),
        archive_sha256=archive_sha256,
        test_count=len(tests),
        profile_sha256=profile_sha256,
    )
