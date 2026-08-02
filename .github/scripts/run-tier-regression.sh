#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

set -o pipefail

RESULTS_DIR="${TIER_RESULTS_DIR:-$(pwd)/ci-results}"
RUN_LOG="${RESULTS_DIR}/run.log"
FAILURE_SUMMARY="${RESULTS_DIR}/failure_summary.log"
EXIT_CODE_FILE="${RESULTS_DIR}/exit_code"
METADATA_FILE="${RESULTS_DIR}/metadata.txt"

mkdir -p "${RESULTS_DIR}"
: > "${RUN_LOG}"
: > "${FAILURE_SUMMARY}"
echo "1" > "${EXIT_CODE_FILE}"

TIER_NAME="${TIER_NAME:-Tier}"
TIER_MODE="${TIER_MODE:-testlist}"
TIER_CONFIG="${TIER_CONFIG:?TIER_CONFIG is required}"
TIER_TESTCASE="${TIER_TESTCASE:?TIER_TESTCASE is required}"
TIER_SIMULATOR="${TIER_SIMULATOR:?TIER_SIMULATOR is required}"
TIER_INSTALL_SCRIPT="${TIER_INSTALL_SCRIPT:-}"
TIER_TESTLIST="${TIER_TESTLIST:-}"
TIER_TEST_NAME="${TIER_TEST_NAME:-}"
TIER_LINKER="${TIER_LINKER:-}"
TIER_ISA_EXTENSIONS="${TIER_ISA_EXTENSIONS:-}"
TIER_EXPECTED_HIER="${TIER_EXPECTED_HIER:-}"
TIER_ISS_TIMEOUT="${TIER_ISS_TIMEOUT:-30000}"
TIER_VALIDATE_ONLY="${TIER_VALIDATE_ONLY:-0}"

log_info() {
  echo "$*" | tee -a "${RUN_LOG}"
}

append_failure() {
  echo "$*" | tee -a "${FAILURE_SUMMARY}" >&2
}

run_logged() {
  set +e
  "$@" > >(tee -a "${RUN_LOG}") 2>&1
  local cmd_rc=$?
  return "${cmd_rc}"
}

source_logged() {
  local script_path="$1"
  set +e
  # shellcheck source=/dev/null
  source "${script_path}" > >(tee -a "${RUN_LOG}") 2>&1
  local source_rc=$?
  return "${source_rc}"
}

record_rc() {
  local step_rc="$1"
  if [ "${step_rc}" -ne 0 ] && [ "${rc}" -eq 0 ]; then
    rc="${step_rc}"
  fi
}

write_metadata() {
  {
    echo "schema_version=1"
    echo "tier=${TIER_NAME}"
    echo "mode=${TIER_MODE}"
    echo "config=${TIER_CONFIG}"
    echo "expected_hier=${TIER_EXPECTED_HIER}"
    echo "testcase=${TIER_TESTCASE}"
    echo "testlist=${TIER_TESTLIST}"
    echo "test_name=${TIER_TEST_NAME}"
    echo "simulator=${TIER_SIMULATOR}"
    echo "isa_extensions=${TIER_ISA_EXTENSIONS}"
    echo "validate_only=${TIER_VALIDATE_ONLY}"
    echo "spike_tandem=${SPIKE_TANDEM:-0}"
    echo "repository=${GITHUB_REPOSITORY:-local}"
    echo "workflow=${GITHUB_WORKFLOW:-local}"
    echo "run_id=${GITHUB_RUN_ID:-local}"
    echo "event=${GITHUB_EVENT_NAME:-local}"
    echo "tested_ref=${GITHUB_REF_NAME:-$(git branch --show-current)}"
    echo "tested_sha=${GITHUB_SHA:-$(git rev-parse HEAD)}"
    echo "source_sha=$(git rev-parse HEAD)"
    echo "core_v_verif_sha=$(git -C verif/core-v-verif rev-parse HEAD)"
    echo "cvfpu_sha=$(git -C core/cvfpu rev-parse HEAD)"
    echo "hpdcache_sha=$(git -C core/cache_subsystem/hpdcache rev-parse HEAD)"
  } > "${METADATA_FILE}"
}

validate_inputs() {
  local target_dir="config/target/${TIER_CONFIG}"
  local testlist_path=""
  local actual_hier=""

  if [ ! -d "${target_dir}" ]; then
    append_failure "ERROR: target directory does not exist: ${target_dir}"
    return 1
  fi

  if [ -n "${TIER_EXPECTED_HIER}" ]; then
    if [ ! -f "${target_dir}/testbench_cfg.yml" ]; then
      append_failure "ERROR: target has no testbench_cfg.yml: ${target_dir}"
      return 1
    fi
    actual_hier="$(sed -nE 's/^[[:space:]]*hier:[[:space:]]*([^;[:space:]]+).*/\1/p' "${target_dir}/testbench_cfg.yml" | head -n 1)"
    if [ "${actual_hier}" != "${TIER_EXPECTED_HIER}" ]; then
      append_failure "ERROR: ${TIER_CONFIG} uses hier=${actual_hier:-unknown}; expected ${TIER_EXPECTED_HIER}."
      return 1
    fi
  fi

  if [ "${TIER_MODE}" != "testlist" ]; then
    append_failure "ERROR: unsupported Tier mode: ${TIER_MODE}"
    return 1
  fi

  if [ -z "${TIER_TESTLIST}" ]; then
    append_failure "ERROR: TIER_TESTLIST is required in testlist mode."
    return 1
  fi

  testlist_path="verif/sim/${TIER_TESTLIST}"
  if [ ! -f "${testlist_path}" ]; then
    append_failure "ERROR: test list does not exist: ${testlist_path}"
    return 1
  fi

  if [ -n "${TIER_INSTALL_SCRIPT}" ] && [ ! -f "verif/regress/${TIER_INSTALL_SCRIPT}.sh" ]; then
    append_failure "ERROR: install script does not exist: verif/regress/${TIER_INSTALL_SCRIPT}.sh"
    return 1
  fi

  return 0
}

collect_reports() {
  local file_path=""
  local relative_path=""
  local safe_name=""

  while IFS= read -r -d '' file_path; do
    relative_path="${file_path#verif/sim/}"
    safe_name="${relative_path//\//__}"
    cp "${file_path}" "${RESULTS_DIR}/${safe_name}"
  done < <(find verif/sim -type f -name "iss_regr.log" -print0 2>/dev/null || true)
}

scan_for_failures() {
  local matches=""
  local -a scan_files=("${RUN_LOG}")

  while IFS= read -r -d '' file_path; do
    scan_files+=("${file_path}")
  done < <(
    find verif/sim -type f \
      \( -name "*.log" -o -name "*.txt" -o -name "iss_regr.log" \) \
      -print0 2>/dev/null || true
  )

  matches="$(
    grep -HnE \
      "\[FAILED\]|SIMULATION FAILED|(^|[^0-9])[1-9][0-9]* FAILED|ERROR return code:|bad syscall|unrecognized opcode|extension .* required|make(\[[0-9]+\])?: \*\*\*.*Error|terminate called|Traceback \(most recent call last\)" \
      "${scan_files[@]}" 2>/dev/null || true
  )"

  if [ -n "${matches}" ]; then
    append_failure "ERROR: ${TIER_NAME} command returned success, but failure patterns were found in logs."
    echo "${matches}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi

  return 0
}

scan_iss_traces() {
  local matches=""
  local critical_patterns=""
  local file_path=""
  local critical_matches=""
  local last_status=""

  critical_patterns="ERROR return code:|bad syscall|unrecognized opcode|extension .* required|terminate called|Traceback \(most recent call last\)"

  while IFS= read -r -d '' file_path; do
    critical_matches="$(grep -HnE "${critical_patterns}" "${file_path}" 2>/dev/null || true)"
    if [ -n "${critical_matches}" ]; then
      matches+="${critical_matches}"$'\n'
    fi

    last_status="$(
      grep -nE "\*\*\*[[:space:]]+(FAILED|SUCCESS)[[:space:]]+\*\*\*|SIMULATION FAILED" "${file_path}" 2>/dev/null | tail -n 1 || true
    )"
    if [[ -n "${last_status}" && "${last_status}" != *"SUCCESS"* ]]; then
      matches+="${file_path}:${last_status}"$'\n'
    fi
  done < <(find verif/sim -type f -name "*.iss" -print0 2>/dev/null || true)

  if [ -n "${matches}" ]; then
    append_failure "ERROR: ${TIER_NAME} command returned success, but ISS trace failures were found."
    printf "%s" "${matches}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi

  return 0
}

rc=0
write_metadata
log_info "Running ${TIER_NAME}: ${TIER_CONFIG} / ${TIER_TESTCASE}"

if ! validate_inputs; then
  rc=1
fi

if [ "${rc}" -eq 0 ] && [ "${TIER_VALIDATE_ONLY}" = "1" ]; then
  log_info "Validation-only mode completed successfully."
  echo "0" > "${EXIT_CODE_FILE}"
  exit 0
fi

if [ "${rc}" -eq 0 ]; then
  source_logged verif/sim/setup-env.sh
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ] && [[ "${TIER_SIMULATOR}" == *"veri-testharness"* ]]; then
  source_logged verif/regress/install-verilator.sh
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ] && [[ "${TIER_SIMULATOR}" == *"spike"* ]]; then
  source_logged verif/regress/install-spike.sh
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ] && [ -n "${TIER_INSTALL_SCRIPT}" ]; then
  source_logged "verif/regress/${TIER_INSTALL_SCRIPT}.sh"
  record_rc "$?"
fi

if [ "${rc}" -eq 0 ]; then
  cva6_cmd=(
    python3 cva6.py
    "--testlist=${TIER_TESTLIST}"
    --target "${TIER_CONFIG}"
    --iss_yaml=cva6.yaml
    "--iss=${TIER_SIMULATOR}"
    "--iss_timeout=${TIER_ISS_TIMEOUT}"
    "--issrun_opts=+tb_performance_mode+debug_disable=1+UVM_VERBOSITY=UVM_NONE"
  )

  if [ -n "${TIER_TEST_NAME}" ]; then
    cva6_cmd+=(--test "${TIER_TEST_NAME}")
  fi

  if [ -n "${TIER_LINKER}" ]; then
    cva6_cmd+=("--linker=${TIER_LINKER}")
  fi

  if [ -n "${TIER_ISA_EXTENSIONS}" ]; then
    cva6_cmd+=("--isa_extension=${TIER_ISA_EXTENSIONS}")
  fi

  pushd verif/sim > /dev/null || rc=$?
  if [ "${rc}" -eq 0 ]; then
    run_logged "${cva6_cmd[@]}"
    record_rc "$?"
  fi
  popd > /dev/null || true
fi

collect_reports

if [ "${rc}" -eq 0 ] && ! compgen -G "verif/sim/out*" > /dev/null; then
  append_failure "ERROR: ${TIER_NAME} command returned success but produced no verif/sim/out* results."
  rc=1
fi

if [ "${rc}" -eq 0 ] && ! scan_for_failures; then
  rc=1
fi

if [ "${rc}" -eq 0 ] && ! scan_iss_traces; then
  rc=1
fi

echo "${rc}" > "${EXIT_CODE_FILE}"
exit "${rc}"
