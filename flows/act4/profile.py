"""Resolve a pinned upstream ACT profile without modifying its checkout.

The checked-in lock and overlay form a reviewable provenance boundary.  The
upstream riscv-arch-test checkout is always treated as immutable input; all
resolved files are written to a caller-provided directory outside that tree.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised only on bad installs
    yaml = None


TARGET = "cv32a65x_axi"
BASE_PROFILE = "cv32a65x"
SIG_BASE = 0x15000000
SIG_SIZE = 0x1000

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_ROOT = REPO_ROOT / "verif/tests/act4" / TARGET

_LOCKED_FILE_KEYS = {
    "udb",
    "sail",
    "test_config",
    "linker_script",
    "rvmodel_macros",
}
_CVA6_LOCKED_FILE_KEYS = {"rtl_config", "isa_config", "spike_config"}
_OVERLAY_KEYS = {
    "schema_version",
    "target",
    "base_profile",
    "generation",
    "base_assertions",
    "udb_updates",
    "implemented_extensions_add",
    "sail_updates",
    "sail_memory_regions_append",
    "test_config_updates",
    "resolved_assertions",
}


class ProfileError(ValueError):
    """Raised when provenance or profile validation fails."""


@dataclass(frozen=True)
class ResolvedProfile:
    """Paths emitted by :func:`resolve_profile`."""

    directory: Path
    udb_config: Path
    sail_config: Path
    test_config: Path
    linker_script: Path
    rvmodel_macros: Path
    manifest: Path


def _require_yaml() -> Any:
    if yaml is None:
        raise ProfileError(
            "PyYAML is required to resolve ACT profiles; install flows/requirements.txt"
        )
    return yaml


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError(f"{name} must be a JSON/YAML mapping")
    return value


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError(f"cannot read {name} at {path}: {error}") from error
    return _require_mapping(value, name)


def load_generation_lock(path: Path | str | None = None) -> dict[str, Any]:
    """Load and structurally validate the checked-in generation lock."""

    lock_path = (
        Path(path)
        if path is not None
        else DEFAULT_PROFILE_ROOT / "generation-lock.json"
    )
    lock = _read_json(lock_path, "generation lock")
    if lock.get("schema_version") != 1:
        raise ProfileError("generation lock schema_version must be 1")

    act4 = _require_mapping(lock.get("act4"), "generation lock act4")
    commit = act4.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ProfileError(
            "generation lock act4.commit must be a full lowercase Git SHA"
        )

    files = _require_mapping(act4.get("files"), "generation lock act4.files")
    if set(files) != _LOCKED_FILE_KEYS:
        raise ProfileError(
            "generation lock act4.files must contain exactly: "
            + ", ".join(sorted(_LOCKED_FILE_KEYS))
        )
    for label, entry_value in files.items():
        entry = _require_mapping(entry_value, f"generation lock file {label}")
        if not isinstance(entry.get("path"), str) or not entry["path"]:
            raise ProfileError(f"generation lock file {label} has no path")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ProfileError(f"generation lock file {label} has an invalid SHA256")

    environment = _require_mapping(
        lock.get("generation_environment"), "generation lock generation_environment"
    )
    container = _require_mapping(environment.get("container"), "generation container")
    digest = container.get("digest")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        raise ProfileError("generation container must be pinned by a sha256 digest")
    if container.get("pin_policy") != "digest":
        raise ProfileError("generation container pin_policy must be 'digest'")
    if container.get("platform") not in {"linux/amd64", "linux/arm64"}:
        raise ProfileError(
            "generation container platform must be pinned to linux/amd64 or linux/arm64"
        )
    tools = _require_mapping(environment.get("observed_tools"), "observed tools")
    required_tools = {"gcc", "binutils", "sail", "mise", "uv", "ruby", "bundler"}
    if set(tools) != required_tools or not all(
        isinstance(value, str) and value for value in tools.values()
    ):
        raise ProfileError("generation lock must record every observed tool version")

    cva6 = _require_mapping(lock.get("cva6"), "generation lock cva6")
    baseline = cva6.get("baseline_commit")
    if not isinstance(baseline, str) or re.fullmatch(r"[0-9a-f]{40}", baseline) is None:
        raise ProfileError(
            "generation lock cva6.baseline_commit must be a full lowercase Git SHA"
        )
    if cva6.get("target") != TARGET:
        raise ProfileError(f"generation lock cva6.target must be {TARGET}")
    cva6_files = _require_mapping(cva6.get("files"), "generation lock cva6.files")
    if set(cva6_files) != _CVA6_LOCKED_FILE_KEYS:
        raise ProfileError(
            "generation lock cva6.files must contain exactly: "
            + ", ".join(sorted(_CVA6_LOCKED_FILE_KEYS))
        )
    for label, entry_value in cva6_files.items():
        entry = _require_mapping(entry_value, f"generation lock CVA6 file {label}")
        if not isinstance(entry.get("path"), str) or not entry["path"]:
            raise ProfileError(f"generation lock CVA6 file {label} has no path")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ProfileError(
                f"generation lock CVA6 file {label} has an invalid SHA256"
            )
    return lock


def load_overlay(path: Path | str | None = None) -> dict[str, Any]:
    """Load and validate the restrictive CVA6 profile overlay schema."""

    overlay_path = (
        Path(path)
        if path is not None
        else DEFAULT_PROFILE_ROOT / "profile-overlay.json"
    )
    overlay = _read_json(overlay_path, "profile overlay")
    unknown = set(overlay) - _OVERLAY_KEYS
    if unknown:
        raise ProfileError(
            f"unsupported profile overlay keys: {', '.join(sorted(unknown))}"
        )
    if overlay.get("schema_version") != 1:
        raise ProfileError("profile overlay schema_version must be 1")
    if overlay.get("target") != TARGET or overlay.get("base_profile") != BASE_PROFILE:
        raise ProfileError(f"profile overlay must resolve {BASE_PROFILE} to {TARGET}")

    generation = _require_mapping(overlay.get("generation"), "overlay generation")
    if generation.get("include_priv_tests") is not False:
        raise ProfileError("the initial ACT profile must set include_priv_tests=false")
    if generation.get("selection_policy") != "all-compatible-unprivileged":
        raise ProfileError("ACT suite selection must be all-compatible-unprivileged")
    if generation.get("requested_suites") != "auto":
        raise ProfileError(
            "requested_suites must be 'auto' to avoid silently dropping suites"
        )
    declared = generation.get("declared_extensions")
    if not isinstance(declared, list) or not all(
        isinstance(item, str) for item in declared
    ):
        raise ProfileError("generation.declared_extensions must be a list of names")
    gaps = _require_mapping(generation.get("known_suite_gaps"), "known suite gaps")
    if "Zcmt" not in gaps:
        raise ProfileError(
            "the absent Zcmt ACT suite must be recorded as a coverage gap"
        )

    for key in (
        "base_assertions",
        "udb_updates",
        "sail_updates",
        "test_config_updates",
        "resolved_assertions",
    ):
        _require_mapping(overlay.get(key), f"overlay {key}")
    if not isinstance(overlay.get("implemented_extensions_add"), list):
        raise ProfileError("implemented_extensions_add must be a list")
    if not isinstance(overlay.get("sail_memory_regions_append"), list):
        raise ProfileError("sail_memory_regions_append must be a list")
    return overlay


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _git_head(repository: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProfileError(
            f"ACT root is not a readable Git checkout: {repository}"
        ) from error
    return result.stdout.strip()


def _git_status(repository: Path) -> str:
    """Return tracked/untracked changes which could alter an ACT generation."""

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProfileError(f"cannot inspect Git status at {repository}") from error
    return result.stdout


def _git_is_ancestor(repository: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "merge-base",
                "--is-ancestor",
                ancestor,
                descendant,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise ProfileError(f"cannot inspect Git ancestry at {repository}") from error
    if result.returncode not in (0, 1):
        raise ProfileError(
            f"cannot verify CVA6 baseline ancestry: {result.stderr.strip()}"
        )
    return result.returncode == 0


def _locked_path(
    repository_root: Path,
    relative_value: Any,
    label: str,
    repository_name: str,
) -> Path:
    if not isinstance(relative_value, str):
        raise ProfileError(f"locked path for {label} must be a string")
    relative = Path(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProfileError(
            f"locked path for {label} must stay inside the {repository_name} checkout"
        )
    try:
        resolved = (repository_root / relative).resolve(strict=True)
    except OSError as error:
        raise ProfileError(
            f"locked {repository_name} input is missing for {label}: {relative}"
        ) from error
    if not _is_relative_to(resolved, repository_root):
        raise ProfileError(
            f"locked {repository_name} input escapes the checkout for {label}: {relative}"
        )
    if not resolved.is_file():
        raise ProfileError(
            f"locked {repository_name} input is not a file for {label}: {relative}"
        )
    return resolved


def validate_act_checkout(
    act4_root: Path | str, lock_path: Path | str | None = None
) -> dict[str, Path]:
    """Validate the pinned ACT checkout and return its locked input paths."""

    root = Path(act4_root).resolve(strict=True)
    if not root.is_dir():
        raise ProfileError(f"ACT root is not a directory: {root}")
    lock = load_generation_lock(lock_path)
    expected_head = lock["act4"]["commit"]
    actual_head = _git_head(root)
    if actual_head != expected_head:
        raise ProfileError(
            f"ACT commit mismatch: expected {expected_head}, found {actual_head}"
        )
    dirty = _git_status(root)
    if dirty:
        first_change = dirty.splitlines()[0]
        raise ProfileError(
            "ACT checkout must be clean before profile resolution; "
            f"first change: {first_change}"
        )

    inputs: dict[str, Path] = {}
    for label, entry in lock["act4"]["files"].items():
        source = _locked_path(root, entry["path"], label, "ACT")
        actual_hash = _sha256(source)
        if actual_hash != entry["sha256"]:
            raise ProfileError(
                f"ACT base hash mismatch for {label}: expected {entry['sha256']}, found {actual_hash}"
            )
        inputs[label] = source
    return inputs


def validate_cva6_architecture_sources(lock: Mapping[str, Any]) -> dict[str, Path]:
    """Verify the CVA6 target facts used to construct the ACT overlay.

    The baseline may be an ancestor of the integration branch so ordinary CI
    and ACT adapter commits do not force regeneration.  Any change to a locked
    target source does require an explicit lock/profile update.
    """

    root = REPO_ROOT.resolve(strict=True)
    current_head = _git_head(root)
    cva6 = _require_mapping(lock.get("cva6"), "generation lock cva6")
    baseline = cva6["baseline_commit"]
    if not _git_is_ancestor(root, baseline, current_head):
        raise ProfileError(
            f"CVA6 architecture baseline {baseline} is not an ancestor of {current_head}"
        )

    inputs: dict[str, Path] = {}
    for label, entry_value in cva6["files"].items():
        entry = _require_mapping(entry_value, f"generation lock CVA6 file {label}")
        source = _locked_path(root, entry["path"], label, "CVA6")
        actual_hash = _sha256(source)
        if actual_hash != entry["sha256"]:
            raise ProfileError(
                "CVA6 architecture-source hash mismatch for "
                f"{label}: expected {entry['sha256']}, found {actual_hash}"
            )
        inputs[label] = source
    return inputs


def _strip_json_comments(text: str) -> str:
    """Remove // and /* */ comments while preserving strings and line numbers."""

    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and next_char == "/":
            output.extend("  ")
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue
        if char == "/" and next_char == "*":
            output.extend("  ")
            index += 2
            while index < len(text):
                if index + 1 < len(text) and text[index : index + 2] == "*/":
                    output.extend("  ")
                    index += 2
                    break
                output.append(text[index] if text[index] in "\r\n" else " ")
                index += 1
            else:
                raise ProfileError("unterminated block comment in Sail JSON")
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _load_yaml(path: Path, name: str) -> dict[str, Any]:
    parser = _require_yaml()
    try:
        value = parser.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, parser.YAMLError) as error:
        raise ProfileError(f"cannot parse {name} at {path}: {error}") from error
    return _require_mapping(value, name)


def _load_sail(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_strip_json_comments(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError(f"cannot parse Sail JSON at {path}: {error}") from error
    return _require_mapping(value, "Sail configuration")


def _assert_subset(actual: Any, expected: Any, path: str) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ProfileError(
                f"profile assertion failed at {path}: expected a mapping"
            )
        for key, expected_value in expected.items():
            if key not in actual:
                raise ProfileError(
                    f"profile assertion failed at {path}.{key}: field is missing"
                )
            _assert_subset(actual[key], expected_value, f"{path}.{key}")
        return
    if actual != expected:
        raise ProfileError(
            f"profile assertion failed at {path}: expected {expected!r}, found {actual!r}"
        )


def _deep_merge(base: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(base))
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _merge_extensions(udb: dict[str, Any], additions: list[Any]) -> None:
    extensions = udb.get("implemented_extensions")
    if not isinstance(extensions, list):
        raise ProfileError("UDB implemented_extensions must be a list")
    by_name: dict[str, int] = {}
    for index, entry in enumerate(extensions):
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            raise ProfileError("UDB implemented_extensions contains an invalid entry")
        by_name[entry["name"]] = index
    for addition_value in additions:
        addition = _require_mapping(addition_value, "implemented extension addition")
        name = addition.get("name")
        version = addition.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ProfileError(
                "implemented extension additions need string name/version"
            )
        if name in by_name:
            extensions[by_name[name]] = deepcopy(addition)
        else:
            by_name[name] = len(extensions)
            extensions.append(deepcopy(addition))


def _integer(value: Any, path: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value.replace("_", ""), 0)
        except ValueError as error:
            raise ProfileError(f"invalid integer at {path}: {value}") from error
    if isinstance(value, dict) and "value" in value:
        return _integer(value["value"], f"{path}.value")
    raise ProfileError(f"invalid integer at {path}: {value!r}")


def _region_bounds(region: Mapping[str, Any], path: str) -> tuple[int, int]:
    base = _integer(region.get("base"), f"{path}.base")
    size = _integer(region.get("size"), f"{path}.size")
    if size <= 0:
        raise ProfileError(f"memory region at {path} must have a positive size")
    return base, base + size


def _append_sail_regions(sail: dict[str, Any], specifications: list[Any]) -> None:
    memory = _require_mapping(sail.get("memory"), "Sail memory")
    regions = memory.get("regions")
    if not isinstance(regions, list):
        raise ProfileError("Sail memory.regions must be a list")

    for spec_value in specifications:
        spec = _require_mapping(spec_value, "Sail memory region overlay")
        helper_base = _integer(
            spec.get("copy_attributes_from_base"), "copy_attributes_from_base"
        )
        template = None
        for index, region_value in enumerate(regions):
            region = _require_mapping(region_value, f"Sail memory.regions[{index}]")
            if (
                _integer(region.get("base"), f"Sail memory.regions[{index}].base")
                == helper_base
            ):
                template = region
                break
        if template is None or not isinstance(template.get("attributes"), dict):
            raise ProfileError(
                f"cannot find Sail memory-region attributes at 0x{helper_base:x}"
            )

        candidate = {
            "base": deepcopy(spec.get("base")),
            "size": deepcopy(spec.get("size")),
            "attributes": deepcopy(template["attributes"]),
            "include_in_device_tree": spec.get("include_in_device_tree", False),
        }
        candidate_start, candidate_end = _region_bounds(
            candidate, "new Sail memory region"
        )
        for index, existing_value in enumerate(regions):
            existing = _require_mapping(existing_value, f"Sail memory.regions[{index}]")
            existing_start, existing_end = _region_bounds(
                existing, f"Sail memory.regions[{index}]"
            )
            if candidate_start < existing_end and existing_start < candidate_end:
                raise ProfileError(
                    "new Sail memory region overlaps existing region "
                    f"0x{existing_start:x}-0x{existing_end:x}"
                )
        regions.append(candidate)

    # Sail's schema requires memory regions to be strictly ascending.  The
    # pinned base ends with RAM at 0x80000000, while the reference-only SIG is
    # at 0x15000000, so a plain append would be structurally invalid.
    regions.sort(
        key=lambda region: _region_bounds(
            _require_mapping(region, "Sail memory region"), "Sail memory region"
        )[0]
    )


def _extension_names(udb: Mapping[str, Any]) -> set[str]:
    extensions = udb.get("implemented_extensions")
    if not isinstance(extensions, list):
        raise ProfileError("UDB implemented_extensions must be a list")
    names: set[str] = set()
    for entry_value in extensions:
        entry = _require_mapping(entry_value, "UDB extension")
        name = entry.get("name")
        if not isinstance(name, str):
            raise ProfileError("UDB extension name must be a string")
        names.add(name)
    return names


def _validate_sig_region(sail: Mapping[str, Any]) -> None:
    regions = sail["memory"]["regions"]
    bounds = [
        _region_bounds(
            _require_mapping(region, f"Sail memory.regions[{index}]"),
            f"Sail memory.regions[{index}]",
        )
        for index, region in enumerate(regions)
    ]
    if bounds != sorted(bounds):
        raise ProfileError("Sail memory regions must be ordered by ascending base")
    for (_, previous_end), (current_start, _) in zip(bounds, bounds[1:]):
        if current_start < previous_end:
            raise ProfileError("Sail memory regions must not overlap")

    containing: Mapping[str, Any] | None = None
    for index, region_value in enumerate(regions):
        region = _require_mapping(region_value, f"Sail memory.regions[{index}]")
        start, end = _region_bounds(region, f"Sail memory.regions[{index}]")
        # Sail requires this PMA region to end on a 4 KiB page boundary.  ACT's
        # register at base + 0x4 is therefore covered as part of the full page.
        if start == SIG_BASE and end == SIG_BASE + SIG_SIZE:
            containing = region
            break
    if containing is None:
        raise ProfileError(
            "Sail SIG must have a non-overlapping 4 KiB memory region at 0x15000000"
        )
    attributes = _require_mapping(containing.get("attributes"), "Sail SIG attributes")
    if attributes.get("mem_type") != "IOMemory":
        raise ProfileError("Sail SIG memory region must be IOMemory")
    if attributes.get("readable") is not True or attributes.get("writable") is not True:
        raise ProfileError("Sail SIG memory region must be readable and writable")


def _validate_resolved_profile(
    udb: dict[str, Any],
    sail: dict[str, Any],
    test_config: dict[str, Any],
    linker_text: str,
    macros_text: str,
    overlay: dict[str, Any],
) -> None:
    assertions = overlay["resolved_assertions"]
    _assert_subset(udb, assertions["udb"], "resolved.udb")
    _assert_subset(sail, assertions["sail"], "resolved.sail")
    _assert_subset(test_config, assertions["test_config"], "resolved.test_config")

    generation = overlay["generation"]
    if test_config.get("include_priv_tests") is not False:
        raise ProfileError("resolved test_config must keep include_priv_tests=false")
    if test_config.get("ref_model_type") != "sail":
        raise ProfileError("ACT expected signatures must use the Sail reference model")

    declared = set(generation["declared_extensions"])
    configured = _extension_names(udb)
    missing = declared - configured
    if missing:
        raise ProfileError(
            f"declared target extensions missing from UDB: {sorted(missing)}"
        )
    if "Zcmt" not in generation["known_suite_gaps"]:
        raise ProfileError("Zcmt must remain an explicit suite-coverage gap")
    if "M" in configured and "Zmmul" not in configured:
        raise ProfileError("M 2.0 requires an explicit Zmmul architectural subset")

    params = _require_mapping(udb.get("params"), "resolved UDB params")
    if params.get("PMP_GRANULARITY") != 3:
        raise ProfileError("cv32a65x_axi UDB PMP_GRANULARITY must be 3 (8 bytes)")
    if params.get("NUM_PMP_ENTRIES") != 16 or params.get("NUM_USABLE_PMP_ENTRIES") != 8:
        raise ProfileError(
            "cv32a65x_axi UDB PMP bank must be 16 entries with 8 usable entries"
        )
    if params.get("HPM_COUNTER_EN") != [False] * 32:
        raise ProfileError("cv32a65x_axi HPM_COUNTER_EN must contain 32 false entries")
    if params.get("JVT_BASE_MASK") != 0x7FFFFFC0:
        raise ProfileError("cv32a65x_axi JVT_BASE_MASK must be 0x7fffffc0")

    pmp = sail["memory"]["pmp"]
    expected_pmp = {
        "grain": 1,
        "count": 16,
        "usable_count": 8,
        "tor_supported": True,
        "na4_supported": False,
        "napot_supported": False,
    }
    _assert_subset(pmp, expected_pmp, "resolved.sail.memory.pmp")

    sig = sail["platform"]["simple_interrupt_generator"]
    if sig != {"supported": True, "base": SIG_BASE}:
        raise ProfileError(
            "Sail simple_interrupt_generator must be enabled at 0x15000000"
        )
    _validate_sig_region(sail)

    macros_lower = macros_text.lower()
    if "15000000" in macros_lower or "simple_interrupt_generator" in macros_lower:
        raise ProfileError(
            "the Sail-only interrupt generator must not appear in DUT macros"
        )
    for marker in ("rvmODEL_halt_pass".lower(), "rvmODEL_halt_fail".lower(), "tohost"):
        if marker not in macros_lower:
            raise ProfileError(f"rvmodel_macros.h is missing required marker {marker}")
    if "li x1, 1" not in macros_lower or "li x1, 3" not in macros_lower:
        raise ProfileError(
            "rvmodel_macros.h must preserve CVA6 pass/fail tohost values"
        )
    if "ENTRY(rvtest_entry_point)" not in linker_text:
        raise ProfileError("link.ld must use rvtest_entry_point")
    if "RAM_ORIGIN = 0x80000000" not in linker_text:
        raise ProfileError("link.ld must preserve the CVA6 ACT RAM origin")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def resolve_profile(
    act4_root: Path | str,
    output_dir: Path | str,
    *,
    lock_path: Path | str | None = None,
    overlay_path: Path | str | None = None,
    assets_dir: Path | str | None = None,
) -> ResolvedProfile:
    """Resolve the pinned ACT `cv32a65x` profile for `cv32a65x_axi`.

    ``act4_root`` is verified by exact Git SHA and file hashes.  ``output_dir``
    must be outside that checkout.  No path below ``act4_root`` is written.
    """

    lock_location = (
        Path(lock_path)
        if lock_path is not None
        else DEFAULT_PROFILE_ROOT / "generation-lock.json"
    )
    overlay_location = (
        Path(overlay_path)
        if overlay_path is not None
        else DEFAULT_PROFILE_ROOT / "profile-overlay.json"
    )
    asset_root = (
        Path(assets_dir) if assets_dir is not None else DEFAULT_PROFILE_ROOT / "profile"
    )

    lock = load_generation_lock(lock_location)
    overlay = load_overlay(overlay_location)
    act_root = Path(act4_root).resolve(strict=True)
    destination = Path(output_dir).resolve(strict=False)
    if _is_relative_to(destination, act_root):
        raise ProfileError(
            "resolved profile output must be outside the read-only ACT checkout"
        )

    inputs = validate_act_checkout(act_root, lock_location)
    validate_cva6_architecture_sources(lock)
    before_hashes = {label: _sha256(path) for label, path in inputs.items()}

    linker_path = (asset_root / "link.ld").resolve(strict=True)
    macros_path = (asset_root / "rvmodel_macros.h").resolve(strict=True)
    if _sha256(linker_path) != lock["act4"]["files"]["linker_script"]["sha256"]:
        raise ProfileError("checked-in link.ld does not match its pinned upstream base")
    if _sha256(macros_path) != lock["act4"]["files"]["rvmodel_macros"]["sha256"]:
        raise ProfileError(
            "checked-in rvmodel_macros.h does not match its pinned upstream base"
        )

    base_udb = _load_yaml(inputs["udb"], "base UDB configuration")
    base_sail = _load_sail(inputs["sail"])
    base_test_config = _load_yaml(inputs["test_config"], "base ACT test configuration")
    base_assertions = overlay["base_assertions"]
    _assert_subset(base_udb, base_assertions["udb"], "base.udb")
    _assert_subset(base_sail, base_assertions["sail"], "base.sail")
    _assert_subset(base_test_config, base_assertions["test_config"], "base.test_config")

    resolved_udb = _deep_merge(base_udb, overlay["udb_updates"])
    _merge_extensions(resolved_udb, overlay["implemented_extensions_add"])
    resolved_sail = _deep_merge(base_sail, overlay["sail_updates"])
    _append_sail_regions(resolved_sail, overlay["sail_memory_regions_append"])
    resolved_test_config = _deep_merge(base_test_config, overlay["test_config_updates"])
    linker_text = linker_path.read_text(encoding="utf-8")
    macros_text = macros_path.read_text(encoding="utf-8")
    _validate_resolved_profile(
        resolved_udb,
        resolved_sail,
        resolved_test_config,
        linker_text,
        macros_text,
        overlay,
    )

    parser = _require_yaml()
    output_paths = ResolvedProfile(
        directory=destination,
        udb_config=destination / f"{TARGET}.yaml",
        sail_config=destination / "sail.json",
        test_config=destination / "test_config.yaml",
        linker_script=destination / "link.ld",
        rvmodel_macros=destination / "rvmodel_macros.h",
        manifest=destination / "resolved-profile.json",
    )
    _atomic_write(
        output_paths.udb_config,
        parser.safe_dump(resolved_udb, sort_keys=False, allow_unicode=True),
    )
    _atomic_write(
        output_paths.sail_config,
        json.dumps(resolved_sail, indent=2, ensure_ascii=False) + "\n",
    )
    _atomic_write(
        output_paths.test_config,
        parser.safe_dump(resolved_test_config, sort_keys=False, allow_unicode=True),
    )
    _atomic_write(output_paths.linker_script, linker_text)
    _atomic_write(output_paths.rvmodel_macros, macros_text)

    resolved_files = {
        "udb": output_paths.udb_config,
        "sail": output_paths.sail_config,
        "test_config": output_paths.test_config,
        "linker_script": output_paths.linker_script,
        "rvmodel_macros": output_paths.rvmodel_macros,
    }
    manifest = {
        "schema_version": 1,
        "target": TARGET,
        "base_profile": BASE_PROFILE,
        "act4": {
            "repository": lock["act4"]["repository"],
            "branch": lock["act4"]["branch"],
            "commit": lock["act4"]["commit"],
            "inputs": {
                label: {
                    "path": lock["act4"]["files"][label]["path"],
                    "sha256": digest,
                }
                for label, digest in sorted(before_hashes.items())
            },
        },
        "cva6": deepcopy(lock["cva6"]),
        "generation_environment": deepcopy(lock["generation_environment"]),
        "generation_scope": deepcopy(overlay["generation"]),
        "overlay_sha256": _sha256(overlay_location),
        "sail_reference_only_mmio": {
            "simple_interrupt_generator": {
                "base": SIG_BASE,
                "size": SIG_SIZE,
                "present_in_dut_macros": False,
            }
        },
        "outputs": {
            label: {"path": path.name, "sha256": _sha256(path)}
            for label, path in sorted(resolved_files.items())
        },
    }
    _atomic_write(output_paths.manifest, json.dumps(manifest, indent=2) + "\n")

    after_hashes = {label: _sha256(path) for label, path in inputs.items()}
    if after_hashes != before_hashes:
        raise ProfileError(
            "the external ACT inputs changed while the profile was resolved"
        )
    return output_paths


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--act4-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--assets-dir", type=Path)
    arguments = parser.parse_args()
    profile = resolve_profile(
        arguments.act4_root,
        arguments.output_dir,
        lock_path=arguments.lock,
        overlay_path=arguments.overlay,
        assets_dir=arguments.assets_dir,
    )
    print(profile.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
