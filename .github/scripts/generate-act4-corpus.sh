#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Low-frequency ACT4 regeneration.  This script never commits or pushes.  It
# exports the locked ACT Git object into a fresh scratch tree, runs the pinned
# generation image, and hands final self-checking ELFs to the Cook packager.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "${ROOT_DIR}"

TARGET="cv32a65x_axi"
PROFILE_ROOT="verif/tests/act4/${TARGET}"
LOCK_FILE="${PROFILE_ROOT}/generation-lock.json"
CORPUS_DIRECTORY="${ACT4_CORPUS_DIRECTORY:-${PROFILE_ROOT}/corpus}"
EVIDENCE_DIRECTORY="${ACT4_EVIDENCE_DIRECTORY:-artifacts/act4-generation/${TARGET}}"
PYTHON="${ACT4_PYTHON:-python3}"
ACT_SOURCE="${ACT4_SOURCE:-${1:-}}"

if [[ -z "${ACT_SOURCE}" ]]; then
  echo "ERROR: set ACT4_SOURCE or pass the pinned riscv-arch-test checkout as argument 1" >&2
  exit 2
fi
if [[ ! -d "${ACT_SOURCE}/.git" && ! -f "${ACT_SOURCE}/.git" ]]; then
  echo "ERROR: ACT4_SOURCE is not a Git checkout: ${ACT_SOURCE}" >&2
  exit 2
fi

for command_name in "${PYTHON}" git tar docker mktemp; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "ERROR: required command is unavailable: ${command_name}" >&2
    exit 2
  fi
done

read_lock() {
  "${PYTHON}" - "${LOCK_FILE}" "$1" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
for component in sys.argv[2].split("."):
    value = value[component]
if not isinstance(value, (str, int, float)):
    raise SystemExit(f"lock value {sys.argv[2]} is not scalar")
print(value)
PY
}

ACT_COMMIT="$(read_lock act4.commit)"
CVA6_COMMIT="$(read_lock cva6.baseline_commit)"
IMAGE="$(read_lock generation_environment.container.image)"
IMAGE_DIGEST="$(read_lock generation_environment.container.digest)"
IMAGE_PLATFORM="$(read_lock generation_environment.container.platform)"
IMAGE_REPOSITORY="${IMAGE%:*}"
IMAGE_REFERENCE="${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"

if [[ "${ACT4_REPLACE:-0}" != "0" && "${ACT4_REPLACE:-0}" != "1" ]]; then
  echo "ERROR: ACT4_REPLACE must be 0 or 1" >&2
  exit 2
fi
if [[ "${ACT4_KEEP_WORK:-0}" != "0" && "${ACT4_KEEP_WORK:-0}" != "1" ]]; then
  echo "ERROR: ACT4_KEEP_WORK must be 0 or 1" >&2
  exit 2
fi
if [[ ! "${ACT4_JOBS:-12}" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: ACT4_JOBS must be a positive integer" >&2
  exit 2
fi
if [[ "${ACT4_REPLACE:-0}" == "0" ]] && \
  [[ -e "${CORPUS_DIRECTORY}/corpus-manifest.json" || \
     -e "${CORPUS_DIRECTORY}/act4-elfs-${TARGET}.tar.gz" || \
     -e "${CORPUS_DIRECTORY}/resolved-profile.json" ]]; then
  echo "ERROR: corpus output exists; review it and set ACT4_REPLACE=1 to replace it" >&2
  exit 2
fi

TEMPORARY_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/cva6-act4-generation.XXXXXX")"
cleanup() {
  if [[ "${ACT4_KEEP_WORK:-0}" == "1" ]]; then
    echo "ACT4 generation work retained at ${TEMPORARY_ROOT}"
    return
  fi
  case "${TEMPORARY_ROOT}" in
    "${TMPDIR:-/tmp}"/cva6-act4-generation.*)
      rm -rf -- "${TEMPORARY_ROOT}"
      ;;
    *)
      echo "ERROR: refusing to remove unexpected temporary path: ${TEMPORARY_ROOT}" >&2
      ;;
  esac
}
trap cleanup EXIT

SOURCE_TREE="${TEMPORARY_ROOT}/act-source"
SOURCE_ARCHIVE="${TEMPORARY_ROOT}/act-source.tar"
RESOLVED_PROFILE="${TEMPORARY_ROOT}/resolved-profile"
GENERATION_OUTPUT="${TEMPORARY_ROOT}/generation-output"
mkdir -p "${SOURCE_TREE}" "${RESOLVED_PROFILE}" "${GENERATION_OUTPUT}" \
  "${EVIDENCE_DIRECTORY}"

# This validates the exact ACT HEAD, rejects tracked/untracked changes, checks
# every locked ACT/CVA6 source hash, and writes only outside the ACT checkout.
"${PYTHON}" -m flows.act4.profile \
  --act4-root "${ACT_SOURCE}" \
  --output-dir "${RESOLVED_PROFILE}"

# Export the committed object rather than copying a developer work tree.  This
# excludes ignored virtualenvs and every other non-committed input by design.
git -C "${ACT_SOURCE}" archive \
  --format=tar \
  --output="${SOURCE_ARCHIVE}" \
  "${ACT_COMMIT}"
tar -xf "${SOURCE_ARCHIVE}" -C "${SOURCE_TREE}"

DOCKER=(docker)
if [[ -n "${ACT4_DOCKER_CONTEXT:-}" ]]; then
  DOCKER+=(--context "${ACT4_DOCKER_CONTEXT}")
fi

GENERATION_LOG="${EVIDENCE_DIRECTORY}/generation.log"
# ACT4_JOBS expands inside the container, not in the host shell.
# shellcheck disable=SC2016
"${DOCKER[@]}" run --rm \
  --platform "${IMAGE_PLATFORM}" \
  --cpus "${ACT4_CPUS:-12}" \
  --memory "${ACT4_MEMORY:-20g}" \
  --env "ACT4_JOBS=${ACT4_JOBS:-12}" \
  --mount "type=bind,src=${SOURCE_TREE},dst=/src,readonly" \
  --mount "type=bind,src=${RESOLVED_PROFILE},dst=/profile,readonly" \
  --mount "type=bind,src=${GENERATION_OUTPUT},dst=/out" \
  "${IMAGE_REFERENCE}" \
  bash -c '
    set -eu
    cp -a /src/. /act4/
    cd /act4
    mise install
    CONFIG_FILES=/profile/test_config.yaml \
    WORKDIR=/out FAST=True make elfs --jobs "${ACT4_JOBS:-12}"
  ' 2>&1 | tee "${GENERATION_LOG}"

ACTUAL_PLATFORM="$(
  "${DOCKER[@]}" image inspect "${IMAGE_REFERENCE}" \
    --format '{{.Os}}/{{.Architecture}}'
)"
if [[ "${ACTUAL_PLATFORM}" != "${IMAGE_PLATFORM}" ]]; then
  echo "ERROR: generation image platform mismatch: expected ${IMAGE_PLATFORM}, got ${ACTUAL_PLATFORM}" >&2
  exit 1
fi

cp "${RESOLVED_PROFILE}/resolved-profile.json" \
  "${EVIDENCE_DIRECTORY}/resolved-profile.json"

PACKAGE_ARGS=(
  act4-package
  --target "${TARGET}"
  --elf-directory "${GENERATION_OUTPUT}/${TARGET}/elfs"
  --resolved-profile "${RESOLVED_PROFILE}/resolved-profile.json"
  --act-commit "${ACT_COMMIT}"
  --cva6-commit "${CVA6_COMMIT}"
  --image-digest "${IMAGE_DIGEST}"
  --output-directory "${CORPUS_DIRECTORY}"
)
if [[ "${ACT4_REPLACE:-0}" == "1" ]]; then
  PACKAGE_ARGS+=(--replace)
fi
"${PYTHON}" ./cook.py "${PACKAGE_ARGS[@]}"

echo "ACT4 corpus generated locally; no Git operation was performed."
echo "Corpus: ${CORPUS_DIRECTORY}"
echo "Review evidence: ${EVIDENCE_DIRECTORY}"
