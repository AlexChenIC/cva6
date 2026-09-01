#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

set -o pipefail

RESULTS_DIR="${RESULTS_DIR:-ci-results}"
COOK_CONFIG_DIR="${COOK_CONFIG_DIR:-${RUNNER_TEMP:-/tmp}/cva6-cook-config}"
RUN_LOG="$(pwd)/${RESULTS_DIR}/run.log"
FAILURE_SUMMARY="$(pwd)/${RESULTS_DIR}/failure_summary.log"
EXIT_CODE_FILE="$(pwd)/${RESULTS_DIR}/exit_code"

TIER_NAME="${TIER_NAME:-Tier}"
TIER_CONFIG="${TIER_CONFIG:?TIER_CONFIG is required}"
TIER_TESTCASE="${TIER_TESTCASE:?TIER_TESTCASE is required}"
TIER_TESTLIST="${TIER_TESTLIST:?TIER_TESTLIST is required}"
TIER_INSTALL_SCRIPT="${TIER_INSTALL_SCRIPT:-}"
TIER_TOOLCHAIN="${TIER_TOOLCHAIN:-github_actions_gcc}"
TIER_COMPILER_MARCH="${TIER_COMPILER_MARCH:?TIER_COMPILER_MARCH is required}"
TIER_COMP_MODE="${TIER_COMP_MODE:-rtl}"
TIER_TRACE_MODE="${TIER_TRACE_MODE:-notrace}"

mkdir -p "${RESULTS_DIR}"
: > "${RUN_LOG}"
: > "${FAILURE_SUMMARY}"
echo "1" > "${EXIT_CODE_FILE}"

run_logged() {
  set +e
  "$@" > >(tee -a "${RUN_LOG}") 2>&1
  local command_rc=$?
  return "${command_rc}"
}

source_logged() {
  local script_path="$1"
  set +e
  # shellcheck source=/dev/null
  source "${script_path}" > >(tee -a "${RUN_LOG}") 2>&1
  local command_rc=$?
  return "${command_rc}"
}

record_rc() {
  local command_rc="$1"
  if [ "${command_rc}" -ne 0 ] && [ "${rc}" -eq 0 ]; then
    rc="${command_rc}"
  fi
}

write_metadata() {
  {
    echo "schema_version=1"
    echo "tier=${TIER_NAME}"
    echo "target=${TIER_CONFIG}"
    echo "testcase=${TIER_TESTCASE}"
    echo "testlist=${TIER_TESTLIST}"
    echo "simulator=verilator-testharness"
    echo "reference_model=spike-offline"
    echo "toolchain=${TIER_TOOLCHAIN}"
    echo "compiler_march=${TIER_COMPILER_MARCH}"
    echo "comp_mode=${TIER_COMP_MODE}"
    echo "trace_mode=${TIER_TRACE_MODE}"
    echo "source_revision=$(git rev-parse HEAD)"
    echo "event_head_sha=${TIER_EVENT_HEAD_SHA:-unknown}"
    echo "event_base_sha=${TIER_EVENT_BASE_SHA:-unknown}"
  } > "${RESULTS_DIR}/metadata.txt"
}

collect_results() {
  if [ -f "${COOK_CONFIG_DIR}/environment.yml" ]; then
    cp "${COOK_CONFIG_DIR}/environment.yml" \
      "${RESULTS_DIR}/toolchain-environment.yml"
  fi
  if [ -d "build/${TIER_CONFIG}" ]; then
    find "build/${TIER_CONFIG}" -type f \
      \( -name 'iss_regr.log' -o -name '*_report.yml' \) \
      -exec cp {} "${RESULTS_DIR}/" \; 2>/dev/null || true
  fi
}

verify_results() {
  local binary
  local report
  local simulations
  local testlist_label
  binary="build/${TIER_CONFIG}/elab/sim_${TIER_COMP_MODE}_verilator_testharness/Variane_testharness"
  testlist_label="$(basename "${TIER_TESTLIST}")"
  testlist_label="${testlist_label%.*}"
  report="build/${TIER_CONFIG}/simulation/testharness_verilator_${testlist_label}_report.yml"
  simulations="build/${TIER_CONFIG}/simulation/sim_${TIER_COMP_MODE}_verilator_testharness"

  if [ ! -x "${binary}" ]; then
    echo "ERROR: missing TestHarness binary: ${binary}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi
  if [ ! -f "${report}" ]; then
    echo "ERROR: missing testlist report: ${report}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi
  if ! find "${simulations}" -mindepth 1 -type d -print -quit 2>/dev/null | grep -q .; then
    echo "ERROR: no TestHarness simulation results found" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi
}

rc=0
write_metadata

source_logged verif/sim/setup-env.sh
record_rc "$?"

if [ "${rc}" -eq 0 ] && [ -n "${TIER_INSTALL_SCRIPT}" ]; then
  source_logged "verif/regress/${TIER_INSTALL_SCRIPT}.sh"
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ]; then
  run_logged python3 .github/scripts/prepare-cook-toolchains.py \
    --output-dir "${COOK_CONFIG_DIR}"
  record_rc "$?"
fi

export CONFIG_DIR="${COOK_CONFIG_DIR}"
export DASHBOARD_JOB_TITLE="${TIER_CONFIG} ${TIER_TESTCASE}"
export DASHBOARD_JOB_DESCRIPTION="Cook Verilator TestHarness and Spike comparison"
export DASHBOARD_JOB_CATEGORY="testlist"
export CI_JOB_ID="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-${TIER_CONFIG}-${TIER_TESTCASE}"
export CI_JOB_URL="https://github.com/${GITHUB_REPOSITORY:-local}/actions/runs/${GITHUB_RUN_ID:-local}"
export CI_JOB_STAGE="${TIER_NAME}"

if [ "${rc}" -eq 0 ]; then
  run_logged ./cook.py sw-compile-testlist \
    --target "${TIER_CONFIG}" \
    --toolchain "${TIER_TOOLCHAIN}" \
    --testlist "${TIER_TESTLIST}" \
    --march "${TIER_COMPILER_MARCH}"
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ]; then
  run_logged ./cook.py verilator-testharness-comp \
    --target "${TIER_CONFIG}" \
    --comp-mode "${TIER_COMP_MODE}" \
    --trace-mode "${TIER_TRACE_MODE}"
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ]; then
  run_logged ./cook.py testharness-run-testlist \
    --simulator verilator \
    --target "${TIER_CONFIG}" \
    --testlist "${TIER_TESTLIST}" \
    --comp-mode "${TIER_COMP_MODE}" \
    --trace-mode "${TIER_TRACE_MODE}" \
    --iss-enabled
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ]; then
  verify_results
  record_rc "$?"
fi

collect_results
if [ "${rc}" -ne 0 ] && [ ! -s "${FAILURE_SUMMARY}" ]; then
  echo "Regression exited with code ${rc}; inspect run.log." \
    | tee -a "${FAILURE_SUMMARY}" >&2
fi
write_metadata
echo "${rc}" > "${EXIT_CODE_FILE}"
exit "${rc}"
