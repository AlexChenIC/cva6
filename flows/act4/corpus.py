"""Frozen ACT4 corpus validation and secure extraction.

The runtime corpus is deliberately independent from Sail, Spike, and the ACT4
generator.  A small JSON manifest integrity-checks a gzip-compressed tar archive
containing the already generated, self-checking ELFs.  Extraction is manual
rather than using :func:`tarfile.extractall`, so links, special files, path
traversal, duplicate members, unexpected files, and size/hash mismatches are
all rejected before an ELF can be executed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
from typing import Any, BinaryIO

MANIFEST_FILENAME = "corpus-manifest.json"
RESOLVED_PROFILE_FILENAME = "resolved-profile.json"
SCHEMA_VERSION = 1
SCOPE = "basic-architectural-subset"

# These limits are intentionally generous for architectural tests while still
# bounding malformed manifests and decompression bombs.
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
MAX_ELF_BYTES = 256 * 1024 * 1024
MAX_CORPUS_BYTES = 4 * 1024 * 1024 * 1024
MAX_TESTS = 10000
_COPY_CHUNK_BYTES = 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SAFE_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.S$")


class CorpusError(ValueError):
    """Base class for fail-closed corpus errors."""


class ManifestError(CorpusError):
    """The external corpus manifest is invalid."""


class ExtractionError(CorpusError):
    """The corpus archive cannot be integrity-verified or safely extracted."""


@dataclass(frozen=True)
class CorpusTest:
    """One integrity-verified self-checking ELF described by the manifest."""

    test_id: str
    elf: str
    sha256: str
    size: int
    source: str | None = None

    @property
    def expected_source(self) -> str:
        """Return the ACT source name expected in an optional RVCP summary."""

        return self.source or f"{PurePosixPath(self.elf).stem}.S"


@dataclass(frozen=True)
class GenerationProvenance:
    """Inputs needed to identify how the frozen corpus was produced."""

    act_commit: str
    cva6_commit: str
    profile_sha256: str
    image_digest: str
    image_platform: str


@dataclass(frozen=True)
class CorpusManifest:
    """Validated version-one corpus manifest."""

    schema_version: int
    target: str
    scope: str
    certification_claim: bool
    archive_name: str
    archive_sha256: str
    generation: GenerationProvenance
    tests: tuple[CorpusTest, ...]


@dataclass(frozen=True)
class PreparedTest:
    """A manifest entry paired with its securely extracted local path."""

    spec: CorpusTest
    path: Path


@dataclass(frozen=True)
class PreparedCorpus:
    """Integrity-verified corpus ready for the runtime runner."""

    manifest: CorpusManifest
    root: Path
    tests: tuple[PreparedTest, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _require_exact_keys(
    value: dict[str, Any], required: set[str], context: str
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ManifestError(f"Invalid {context} fields: {'; '.join(details)}")


def _require_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{context} must be a JSON object")
    return value


def _require_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value or not value.isprintable():
        raise ManifestError(f"{context} must be a non-empty printable string")
    return value


def _require_sha256(value: Any, context: str) -> str:
    digest = _require_text(value, context)
    if not _SHA256_RE.fullmatch(digest):
        raise ManifestError(f"{context} must be a lowercase SHA-256 digest")
    return digest


def _regular_file(path: Path, context: str, maximum_size: int) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise CorpusError(f"Cannot access {context} {path}: {error}") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CorpusError(f"{context} must be a regular non-symlink file: {path}")
    if metadata.st_size <= 0 or metadata.st_size > maximum_size:
        raise CorpusError(
            f"{context} has invalid size {metadata.st_size} bytes: {path}"
        )
    return metadata


def _validate_elf_path(value: Any, context: str) -> str:
    elf = _require_text(value, context)
    if "\\" in elf or "\x00" in elf:
        raise ManifestError(f"{context} contains an unsafe path")
    path = PurePosixPath(elf)
    if (
        path.is_absolute()
        or len(path.parts) != 2
        or path.parts[0] != "elfs"
        or path.parts[1] in {"", ".", ".."}
        or path.suffix.lower() != ".elf"
        or str(path) != elf
    ):
        raise ManifestError(f"{context} must match elfs/<name>.elf: {elf}")
    return elf


def _parse_test(value: Any, index: int) -> CorpusTest:
    test = _require_mapping(value, f"tests[{index}]")
    required = {"id", "elf", "sha256", "size"}
    optional = {"source"}
    actual = set(test)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required - optional)
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unexpected:
            details.append("unexpected " + ", ".join(unexpected))
        raise ManifestError(f"Invalid tests[{index}] fields: {'; '.join(details)}")

    test_id = _require_text(test["id"], f"tests[{index}].id")
    if not _TEST_ID_RE.fullmatch(test_id):
        raise ManifestError(f"Unsafe tests[{index}].id: {test_id}")
    elf = _validate_elf_path(test["elf"], f"tests[{index}].elf")
    digest = _require_sha256(test["sha256"], f"tests[{index}].sha256")
    size = test["size"]
    if isinstance(size, bool) or not isinstance(size, int):
        raise ManifestError(f"tests[{index}].size must be an integer")
    if size <= 0 or size > MAX_ELF_BYTES:
        raise ManifestError(f"tests[{index}].size is outside the allowed range")

    source = test.get("source")
    if source is not None:
        source = _require_text(source, f"tests[{index}].source")
        if not _SAFE_SOURCE_RE.fullmatch(source):
            raise ManifestError(f"tests[{index}].source must be a safe .S basename")
    return CorpusTest(test_id, elf, digest, size, source)


def load_manifest(path: Path, expected_target: str) -> CorpusManifest:
    """Load and strictly validate an external version-one manifest.

    ``expected_target`` is supplied by the Cook invocation.  Requiring an exact
    match prevents a valid corpus for one CVA6 configuration from being run
    under another configuration by accident.
    """

    _regular_file(path, "corpus manifest", MAX_MANIFEST_BYTES)
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ManifestError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"Cannot parse corpus manifest {path}: {error}") from error

    document = _require_mapping(raw, "manifest")
    _require_exact_keys(
        document,
        {
            "schema_version",
            "target",
            "scope",
            "certification_claim",
            "archive",
            "generation",
            "tests",
        },
        "manifest",
    )

    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or schema_version != SCHEMA_VERSION:
        raise ManifestError(
            f"Unsupported schema_version {schema_version!r}; expected {SCHEMA_VERSION}"
        )
    target = _require_text(document["target"], "target")
    if target != expected_target:
        raise ManifestError(
            f"Corpus target mismatch: expected {expected_target}, got {target}"
        )
    scope = _require_text(document["scope"], "scope")
    if scope != SCOPE:
        raise ManifestError(f"Unsupported ACT4 corpus scope: {scope}")
    certification_claim = document["certification_claim"]
    if certification_claim is not False:
        raise ManifestError(
            "certification_claim must be false for this regression corpus"
        )

    archive = _require_mapping(document["archive"], "archive")
    _require_exact_keys(archive, {"name", "sha256"}, "archive")
    archive_name = _require_text(archive["name"], "archive.name")
    if Path(archive_name).name != archive_name or "\\" in archive_name:
        raise ManifestError("archive.name must be a safe basename")
    expected_archive_name = f"act4-elfs-{target}.tar.gz"
    if archive_name != expected_archive_name:
        raise ManifestError(
            f"archive.name must be {expected_archive_name}, got {archive_name}"
        )
    archive_sha256 = _require_sha256(archive["sha256"], "archive.sha256")

    generation = _require_mapping(document["generation"], "generation")
    _require_exact_keys(
        generation,
        {
            "act_commit",
            "cva6_commit",
            "profile_sha256",
            "image_digest",
            "image_platform",
        },
        "generation",
    )
    act_commit = _require_text(generation["act_commit"], "generation.act_commit")
    cva6_commit = _require_text(generation["cva6_commit"], "generation.cva6_commit")
    if not _GIT_SHA_RE.fullmatch(act_commit):
        raise ManifestError("generation.act_commit must be a full Git SHA")
    if not _GIT_SHA_RE.fullmatch(cva6_commit):
        raise ManifestError("generation.cva6_commit must be a full Git SHA")
    profile_sha256 = _require_sha256(
        generation["profile_sha256"], "generation.profile_sha256"
    )
    image_digest = _require_text(generation["image_digest"], "generation.image_digest")
    if not _IMAGE_DIGEST_RE.fullmatch(image_digest):
        raise ManifestError(
            "generation.image_digest must be sha256:<64 lowercase hex digits>"
        )
    image_platform = _require_text(
        generation["image_platform"], "generation.image_platform"
    )
    if image_platform not in {"linux/amd64", "linux/arm64"}:
        raise ManifestError(
            "generation.image_platform must be linux/amd64 or linux/arm64"
        )

    raw_tests = document["tests"]
    if not isinstance(raw_tests, list):
        raise ManifestError("tests must be a JSON array")
    if not raw_tests:
        raise ManifestError("Corpus contains zero tests")
    if len(raw_tests) > MAX_TESTS:
        raise ManifestError(f"Corpus contains more than {MAX_TESTS} tests")
    tests = tuple(_parse_test(value, index) for index, value in enumerate(raw_tests))

    ids = [test.test_id for test in tests]
    elfs = [test.elf for test in tests]
    if len(set(ids)) != len(ids):
        raise ManifestError("Corpus contains duplicate test ids")
    if len(set(elfs)) != len(elfs):
        raise ManifestError("Corpus contains duplicate ELF paths")
    total_size = sum(test.size for test in tests)
    if total_size > MAX_CORPUS_BYTES:
        raise ManifestError("Corpus uncompressed size exceeds the safety limit")

    provenance = GenerationProvenance(
        act_commit=act_commit,
        cva6_commit=cva6_commit,
        profile_sha256=profile_sha256,
        image_digest=image_digest,
        image_platform=image_platform,
    )
    return CorpusManifest(
        schema_version=SCHEMA_VERSION,
        target=target,
        scope=scope,
        certification_claim=False,
        archive_name=archive_name,
        archive_sha256=archive_sha256,
        generation=provenance,
        tests=tests,
    )


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 digest for ``path``."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, expected_sha256: str) -> None:
    """Require a regular archive whose complete bytes match the manifest."""

    _regular_file(path, "corpus archive", MAX_ARCHIVE_BYTES)
    try:
        actual = sha256_file(path)
    except OSError as error:
        raise ExtractionError(f"Cannot hash corpus archive {path}: {error}") from error
    if actual != expected_sha256:
        raise ExtractionError(
            f"Corpus archive SHA-256 mismatch: expected {expected_sha256}, got {actual}"
        )


def _validate_tar_members(
    archive: tarfile.TarFile, manifest: CorpusManifest
) -> dict[str, tarfile.TarInfo]:
    expected = {test.elf: test for test in manifest.tests}
    files: dict[str, tarfile.TarInfo] = {}
    seen: set[str] = set()
    maximum_members = len(manifest.tests) + 1
    # Iterate instead of calling getmembers(), which would materialize an
    # attacker-controlled number of TarInfo objects before the bound is
    # checked.  Iteration stops parsing as soon as the small manifest-derived
    # limit is exceeded.
    for member_count, member in enumerate(archive, start=1):
        if member_count > maximum_members:
            raise ExtractionError("Corpus archive contains unexpected members")
        name = member.name
        if (
            not name
            or "\\" in name
            or "\x00" in name
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
        ):
            raise ExtractionError(f"Unsafe archive member path: {name!r}")
        normalized = str(PurePosixPath(name))
        if member.isdir() and name.endswith("/"):
            name = name.rstrip("/")
            normalized = str(PurePosixPath(name))
        if name != normalized:
            raise ExtractionError(f"Non-canonical archive member path: {member.name}")
        if name in seen:
            raise ExtractionError(f"Duplicate archive member: {name}")
        seen.add(name)

        if member.isdir():
            if name != "elfs":
                raise ExtractionError(f"Unexpected directory in corpus archive: {name}")
            continue
        if not member.isfile():
            raise ExtractionError(
                f"Links and special files are forbidden in corpus archive: {name}"
            )
        if name not in expected:
            raise ExtractionError(f"Unexpected file in corpus archive: {name}")
        if member.size != expected[name].size:
            raise ExtractionError(
                f"Archive size mismatch for {name}: "
                f"expected {expected[name].size}, got {member.size}"
            )
        files[name] = member

    missing = sorted(set(expected) - set(files))
    if missing:
        raise ExtractionError("Corpus archive is missing: " + ", ".join(missing))
    return files


def _copy_and_hash(
    source: BinaryIO, destination: Path, expected_size: int, expected_sha256: str
) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    digest = hashlib.sha256()
    copied = 0
    try:
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            while chunk := source.read(_COPY_CHUNK_BYTES):
                copied += len(chunk)
                if copied > expected_size:
                    raise ExtractionError(
                        f"Archive payload exceeds declared size for {destination.name}"
                    )
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except OSError as error:
        raise ExtractionError(f"Cannot extract {destination}: {error}") from error

    if copied != expected_size:
        raise ExtractionError(
            f"Extracted size mismatch for {destination.name}: "
            f"expected {expected_size}, got {copied}"
        )
    actual_sha256 = digest.hexdigest()
    if actual_sha256 != expected_sha256:
        raise ExtractionError(
            f"Extracted SHA-256 mismatch for {destination.name}: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    destination.chmod(0o400)


def extract_archive(
    archive_path: Path, manifest: CorpusManifest, destination: Path
) -> PreparedCorpus:
    """Securely extract all and only the integrity-verified manifest ELFs.

    ``destination`` must not already exist.  This gives extraction exclusive
    ownership of every path it creates and avoids following attacker-controlled
    files left by an earlier run.
    """

    if os.path.lexists(destination):
        raise ExtractionError(f"Extraction destination already exists: {destination}")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(mode=0o700)
        elf_directory = destination / "elfs"
        elf_directory.mkdir(mode=0o700)

        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = _validate_tar_members(archive, manifest)
            prepared: list[PreparedTest] = []
            for test in manifest.tests:
                member = members[test.elf]
                source = archive.extractfile(member)
                if source is None:
                    raise ExtractionError(f"Cannot read archive member: {test.elf}")
                output = destination / Path(*PurePosixPath(test.elf).parts)
                with source:
                    _copy_and_hash(source, output, test.size, test.sha256)
                prepared.append(PreparedTest(test, output.resolve(strict=True)))
    except (CorpusError, tarfile.TarError, OSError) as error:
        shutil.rmtree(destination, ignore_errors=True)
        if isinstance(error, CorpusError):
            raise
        raise ExtractionError(f"Cannot extract corpus archive: {error}") from error

    return PreparedCorpus(manifest, destination.resolve(strict=True), tuple(prepared))


def prepare_corpus(
    corpus_directory: Path, destination: Path, expected_target: str
) -> PreparedCorpus:
    """Integrity-check the external manifest/archive and return extracted ELFs."""

    manifest_path = corpus_directory / MANIFEST_FILENAME
    manifest = load_manifest(manifest_path, expected_target)
    resolved_profile = corpus_directory / RESOLVED_PROFILE_FILENAME
    _regular_file(resolved_profile, "resolved ACT4 profile", MAX_MANIFEST_BYTES * 16)
    try:
        actual_profile_sha256 = sha256_file(resolved_profile)
    except OSError as error:
        raise CorpusError(
            f"Cannot hash resolved ACT4 profile {resolved_profile}: {error}"
        ) from error
    if actual_profile_sha256 != manifest.generation.profile_sha256:
        raise CorpusError(
            "Resolved ACT4 profile SHA-256 mismatch: expected "
            f"{manifest.generation.profile_sha256}, got {actual_profile_sha256}"
        )
    archive_path = corpus_directory / manifest.archive_name
    verify_archive(archive_path, manifest.archive_sha256)
    return extract_archive(archive_path, manifest, destination)
