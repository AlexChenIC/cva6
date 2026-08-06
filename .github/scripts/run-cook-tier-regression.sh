#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Legacy CVA6 setup scripts are not nounset-safe, so keep strict error and
# pipeline handling without enabling `set -u` across sourced project scripts.
set -Ee -o pipefail

RESULTS_DIR="${RESULTS_DIR:-ci-results}"
COOK_CONFIG_DIR="${COOK_CONFIG_DIR:-${RUNNER_TEMP:-/tmp}/cva6-cook-config}"
RUN_LOG="${RESULTS_DIR}/run.log"
FAILURE_SUMMARY="${RESULTS_DIR}/failure_summary.log"
EXIT_CODE_FILE="${RESULTS_DIR}/exit_code"

: "${TIER_LEVEL:?TIER_LEVEL is required}"
: "${TIER_CONFIG:?TIER_CONFIG is required}"
: "${TIER_TESTLIST:?TIER_TESTLIST is required}"
: "${TIER_TOOLCHAIN:?TIER_TOOLCHAIN is required}"
: "${TIER_COMPILER_MARCH:?TIER_COMPILER_MARCH is required}"

mkdir -p "${RESULTS_DIR}"
: > "${RUN_LOG}"
: > "${FAILURE_SUMMARY}"
echo "1" > "${EXIT_CODE_FILE}"
exec > >(tee -a "${RUN_LOG}") 2>&1

collect_results() {
  mkdir -p "${RESULTS_DIR}/reports"
  if [ -f "${COOK_CONFIG_DIR}/environment.yml" ]; then
    cp "${COOK_CONFIG_DIR}/environment.yml" \
      "${RESULTS_DIR}/toolchain-environment.yml"
  fi
  if [ -d artifacts/reports ]; then
    find artifacts/reports -maxdepth 1 -type f -name 'report_*.yml' \
      -exec cp {} "${RESULTS_DIR}/reports/" \;
  fi
}

scan_failures() {
  local -a files=("${RUN_LOG}")
  while IFS= read -r -d '' file_path; do
    files+=("${file_path}")
  done < <(
    find "build/${TIER_CONFIG}" -type f \
      \( -name '*.log' -o -name '*.iss' \) -print0 2>/dev/null || true
  )
  python3 .github/scripts/summarize-cook-failures.py \
    --output "${FAILURE_SUMMARY}" \
    "${files[@]}"
}

write_metadata() {
  {
    echo "schema_version=1"
    echo "tier=${TIER_LEVEL}"
    echo "target=${TIER_CONFIG}"
    echo "testlist=${TIER_TESTLIST}"
    echo "toolchain=${TIER_TOOLCHAIN}"
    echo "compiler_march=${TIER_COMPILER_MARCH}"
    echo "compiler_march_reason=${TIER_COMPILER_MARCH_REASON:-not-specified}"
    echo "expected_enabled_tests=${TIER_EXPECTED_ENABLED_TESTS:-unknown}"
    echo "backend=veri-testharness,spike"
    echo "spike_tandem=${SPIKE_TANDEM:-unset}"
    echo "source_revision=$(git rev-parse HEAD)"
    echo "event_head_sha=${TIER_EVENT_HEAD_SHA:-unknown}"
    echo "event_base_sha=${TIER_EVENT_BASE_SHA:-unknown}"
  } > "${RESULTS_DIR}/metadata.txt"
}

finalize() {
  local rc="$?"
  trap - EXIT
  set +e
  collect_results
  scan_failures
  local scan_rc="$?"
  if [ "${rc}" -ne 0 ] && [ ! -s "${FAILURE_SUMMARY}" ]; then
    echo "Regression exited with code ${rc}; inspect run.log for details." \
      >> "${FAILURE_SUMMARY}"
  fi
  if [ "${rc}" -eq 0 ] && [ "${scan_rc}" -ne 0 ]; then
    rc=1
  fi
  echo "${rc}" > "${EXIT_CODE_FILE}"
  write_metadata
  exit "${rc}"
}
trap finalize EXIT

write_metadata
python3 .github/scripts/cook-tier-plan.py entry-report \
  --tier "${TIER_LEVEL}" \
  --target "${TIER_CONFIG}" \
  --testlist "${TIER_TESTLIST}" \
  --output "${RESULTS_DIR}/thales-matrix-membership.yml"

# shellcheck source=/dev/null
source verif/sim/setup-env.sh
if [ -n "${TIER_INSTALL_SCRIPT:-}" ]; then
  # shellcheck source=/dev/null
  source "verif/regress/${TIER_INSTALL_SCRIPT}.sh"
fi

python3 .github/scripts/prepare-cook-toolchains.py \
  --output-dir "${COOK_CONFIG_DIR}" \
  --required-toolchain "${TIER_TOOLCHAIN}"
export CONFIG_DIR="${COOK_CONFIG_DIR}"
if [ -d "${COOK_CONFIG_DIR}/llvm18/bin" ]; then
  export PATH="${COOK_CONFIG_DIR}/llvm18/bin:${PATH}"
fi

testlist_stem="$(basename "${TIER_TESTLIST}" .yaml)"
export DASHBOARD_JOB_TITLE="${TIER_CONFIG} ${testlist_stem} public tandem"
export DASHBOARD_JOB_DESCRIPTION="cook.py-aligned Verilator TestHarness and Spike validation"
export DASHBOARD_JOB_CATEGORY="testlist"
export CI_JOB_ID="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-${TIER_CONFIG}-${testlist_stem}"
export CI_JOB_URL="https://github.com/${GITHUB_REPOSITORY:-local}/actions/runs/${GITHUB_RUN_ID:-local}"
export CI_JOB_STAGE="${TIER_LEVEL}"

./cook.py sw-compile-testlist \
  --target "${TIER_CONFIG}" \
  --toolchain "${TIER_TOOLCHAIN}" \
  --testlist "${TIER_TESTLIST}" \
  --march "${TIER_COMPILER_MARCH}"

./cook.py verilator-testharness-run-testlist \
  --target "${TIER_CONFIG}" \
  --testlist "${TIER_TESTLIST}" \
  --tandem-enabled \
  --iss-timeout "${TIER_ISS_TIMEOUT:-30000}"
