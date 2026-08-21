#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

set -o pipefail

RESULTS_DIR="${RESULTS_DIR:-ci-results}"
RUN_LOG="$(pwd)/${RESULTS_DIR}/run.log"
FAILURE_SUMMARY="$(pwd)/${RESULTS_DIR}/failure_summary.log"
EXIT_CODE_FILE="$(pwd)/${RESULTS_DIR}/exit_code"
COOK_CONFIG_DIR="${COOK_CONFIG_DIR:-${RUNNER_TEMP:-/tmp}/cva6-cook-config}"

mkdir -p "${RESULTS_DIR}"
: > "${RUN_LOG}"
: > "${FAILURE_SUMMARY}"
echo "1" > "${EXIT_CODE_FILE}"

TIER_NAME="${TIER_NAME:-Tier}"
TIER_MODE="${TIER_MODE:-script}"
TIER_CONFIG="${TIER_CONFIG:?TIER_CONFIG is required}"
TIER_TESTCASE="${TIER_TESTCASE:-}"
TIER_SIMULATOR="${TIER_SIMULATOR:-veri-testharness,spike}"
TIER_INSTALL_SCRIPT="${TIER_INSTALL_SCRIPT:-}"
TIER_TESTLIST="${TIER_TESTLIST:-}"
TIER_TEST_NAME="${TIER_TEST_NAME:-}"
TIER_LINKER="${TIER_LINKER:-}"
TIER_HWCONFIG_OPTS="${TIER_HWCONFIG_OPTS:-}"
TIER_TOOLCHAIN="${TIER_TOOLCHAIN:-github_actions_gcc}"
TIER_COMPILER_MARCH="${TIER_COMPILER_MARCH:-}"
TIER_ISS_TIMEOUT="${TIER_ISS_TIMEOUT:-500}"
TIER_ACT4_CORPUS="${TIER_ACT4_CORPUS:-verif/tests/act4/${TIER_CONFIG}/corpus}"
TIER_ACT4_SIMULATOR="${TIER_ACT4_SIMULATOR:-work-ver/Variane_testharness}"
TIER_ACT4_CYCLE_TIMEOUT="${TIER_ACT4_CYCLE_TIMEOUT:-10000000}"
TIER_ACT4_WALL_TIMEOUT_SECONDS="${TIER_ACT4_WALL_TIMEOUT_SECONDS:-300}"
TIER_ACT4_BUILD_JOBS="${TIER_ACT4_BUILD_JOBS:-${NUM_JOBS:-1}}"

require_positive_integer() {
  local value="$1"
  local name="$2"

  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: ${name} must be a positive integer" >&2
    exit 2
  fi
}

case "${TIER_MODE}" in
  script)
    : "${TIER_TESTCASE:?TIER_TESTCASE is required for script mode}"
    ;;
  testlist)
    : "${TIER_TESTCASE:?TIER_TESTCASE is required for testlist mode}"
    : "${TIER_TESTLIST:?TIER_TESTLIST is required for testlist mode}"
    ;;
  cook-testlist)
    : "${TIER_TESTLIST:?TIER_TESTLIST is required for cook-testlist mode}"
    : "${TIER_COMPILER_MARCH:?TIER_COMPILER_MARCH is required for cook-testlist mode}"
    ;;
  act4-prebuilt)
    if [ "${TIER_CONFIG}" != "cv32a65x_axi" ]; then
      echo "ERROR: act4-prebuilt currently supports only cv32a65x_axi" >&2
      exit 2
    fi
    : "${TIER_ACT4_CORPUS:?TIER_ACT4_CORPUS is required for act4-prebuilt mode}"
    : "${TIER_ACT4_SIMULATOR:?TIER_ACT4_SIMULATOR is required for act4-prebuilt mode}"
    require_positive_integer "${TIER_ACT4_CYCLE_TIMEOUT}" \
      "TIER_ACT4_CYCLE_TIMEOUT"
    require_positive_integer "${TIER_ACT4_WALL_TIMEOUT_SECONDS}" \
      "TIER_ACT4_WALL_TIMEOUT_SECONDS"
    require_positive_integer "${TIER_ACT4_BUILD_JOBS}" \
      "TIER_ACT4_BUILD_JOBS"
    ;;
  *)
    echo "ERROR: unsupported TIER_MODE=${TIER_MODE}" >&2
    exit 2
    ;;
esac

log_info() {
  echo "$*" | tee -a "${RUN_LOG}"
}

run_logged() {
  local cmd_rc
  set +e
  "$@" 2>&1 | tee -a "${RUN_LOG}"
  cmd_rc="${PIPESTATUS[0]}"
  return "${cmd_rc}"
}

source_logged() {
  local script_path="$1"
  local previous_size
  local first_new_byte
  local source_rc
  set +e
  previous_size="$(wc -c < "${RUN_LOG}")"
  # shellcheck source=/dev/null
  source "${script_path}" >> "${RUN_LOG}" 2>&1
  source_rc=$?
  first_new_byte=$((previous_size + 1))
  tail -c "+${first_new_byte}" "${RUN_LOG}"
  return "${source_rc}"
}

record_rc() {
  local step_rc="$1"
  if [ "${step_rc}" -ne 0 ] && [ "${rc}" -eq 0 ]; then
    rc="${step_rc}"
  fi
}

append_failure() {
  echo "$*" | tee -a "${FAILURE_SUMMARY}" >&2
}

collect_reports() {
  mkdir -p "${RESULTS_DIR}/reports"
  find verif/sim -name "iss_regr.log" \
    -exec cp {} "${RESULTS_DIR}/" \; 2>/dev/null || true
  if [ -f "${COOK_CONFIG_DIR}/environment.yml" ]; then
    cp "${COOK_CONFIG_DIR}/environment.yml" \
      "${RESULTS_DIR}/toolchain-environment.yml"
  fi
  if [ -d artifacts/reports ]; then
    find artifacts/reports -maxdepth 1 -type f -name 'report_*.yml' \
      -exec cp {} "${RESULTS_DIR}/reports/" \;
  fi
  if [ "${TIER_MODE}" = "act4-prebuilt" ] && \
    [ -f "${TIER_ACT4_CORPUS}/corpus-manifest.json" ]; then
    cp "${TIER_ACT4_CORPUS}/corpus-manifest.json" \
      "${RESULTS_DIR}/act4-corpus-manifest.json"
  fi
}

write_act4_metadata() {
  local manifest="${TIER_ACT4_CORPUS}/corpus-manifest.json"

  echo "act4_corpus=${TIER_ACT4_CORPUS}"
  echo "act4_simulator=${TIER_ACT4_SIMULATOR}"
  echo "act4_cycle_timeout=${TIER_ACT4_CYCLE_TIMEOUT}"
  echo "act4_wall_timeout_seconds=${TIER_ACT4_WALL_TIMEOUT_SECONDS}"
  echo "act4_build_jobs=${TIER_ACT4_BUILD_JOBS}"
  echo "act4_live_reference_model=disabled"
  echo "act4_testharness_spike_tandem=disabled"
  echo "act4_runtime_result=${ACT4_RUNTIME_RESULT:-not-run}"
  if [ ! -f "${manifest}" ]; then
    echo "act4_manifest_status=missing"
    return
  fi

  python3 - "${manifest}" "${ACT4_RUNTIME_RESULT:-not-run}" <<'PY'
import json
import sys
from pathlib import Path


def safe(value: object) -> str:
    if isinstance(value, bool):
        value = str(value).lower()
    return str(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


try:
    document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    runtime_result = sys.argv[2]
    generation = document.get("generation", {})
    archive = document.get("archive", {})
    values = {
        "act4_manifest_status": (
            "validated" if runtime_result == "pass" else "present-unvalidated"
        ),
        "act4_scope": document.get("scope", "unknown"),
        "act4_certification_claim": document.get("certification_claim", "unknown"),
        "act4_archive_sha256": archive.get("sha256", "unknown"),
        "act4_source_revision": generation.get("act_commit", "unknown"),
        "act4_generation_cva6_revision": generation.get("cva6_commit", "unknown"),
        "act4_profile_sha256": generation.get("profile_sha256", "unknown"),
        "act4_generation_image_digest": generation.get("image_digest", "unknown"),
        "act4_generation_image_platform": generation.get("image_platform", "unknown"),
        "act4_test_count": len(document.get("tests", [])),
    }
except (OSError, json.JSONDecodeError, AttributeError, TypeError) as error:
    print("act4_manifest_status=invalid")
    print(f"act4_manifest_error={safe(error)}")
else:
    for key, value in values.items():
        print(f"{key}={safe(value)}")
PY
}

write_metadata() {
  {
    echo "schema_version=1"
    echo "tier=${TIER_NAME}"
    echo "mode=${TIER_MODE}"
    echo "target=${TIER_CONFIG}"
    echo "testcase=${TIER_TESTCASE}"
    echo "testlist=${TIER_TESTLIST}"
    if [ "${TIER_MODE}" = "act4-prebuilt" ]; then
      echo "simulator=${TIER_ACT4_SIMULATOR}"
    else
      echo "simulator=${TIER_SIMULATOR}"
    fi
    echo "toolchain=${TIER_TOOLCHAIN}"
    echo "compiler_march=${TIER_COMPILER_MARCH}"
    echo "spike_tandem=${SPIKE_TANDEM:-unset}"
    echo "source_revision=$(git rev-parse HEAD)"
    echo "event_head_sha=${TIER_EVENT_HEAD_SHA:-unknown}"
    echo "event_base_sha=${TIER_EVENT_BASE_SHA:-unknown}"
    if [ "${TIER_MODE}" = "act4-prebuilt" ]; then
      write_act4_metadata
    fi
  } > "${RESULTS_DIR}/metadata.txt"
}

scan_for_failures() {
  local matches
  local -a scan_files=("${RUN_LOG}")

  while IFS= read -r -d '' file_path; do
    scan_files+=("${file_path}")
  done < <(
    find verif/sim -type f \
      \( -name "*.log" -o -name "*.txt" -o -name "iss_regr.log" \) \
      -print0 2>/dev/null || true
    if [ -d "build/${TIER_CONFIG}" ]; then
      find "build/${TIER_CONFIG}" -type f \
        \( -name "*.log" -o -name "*.txt" \) \
        -print0 2>/dev/null || true
    fi
    if [ "${TIER_MODE}" = "act4-prebuilt" ] && [ -d artifacts/act4 ]; then
      find artifacts/act4 -type f -name "*.log" \
        -print0 2>/dev/null || true
    fi
  )

  matches="$(
    grep -HnE \
      "\\[FAILED\\]|SIMULATION FAILED|(^|[^0-9])[1-9][0-9]* FAILED|:[[:space:]]+FAIL[[:space:]]+\\([1-9][0-9]*\\)|\\*\\*\\*[[:space:]]+FAILED[[:space:]]+\\*\\*\\*|ERROR[[:space:]]+return code:|bad syscall|unrecognized opcode|extension .* required|make(\\[[0-9]+\\])?: \\*\\*\\*.*Error|terminate called|Traceback \\(most recent call last\\)" \
      "${scan_files[@]}" 2>/dev/null || true
  )"

  if [ -n "${matches}" ]; then
    append_failure "ERROR: failure patterns were found in regression logs."
    echo "${matches}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi

  return 0
}

scan_iss_traces() {
  local matches=""
  local critical_patterns
  critical_patterns="ERROR[[:space:]]+return code:|bad syscall|unrecognized opcode|extension .* required|terminate called|Traceback \\(most recent call last\\)"

  while IFS= read -r -d '' file_path; do
    local critical_matches
    local last_status

    critical_matches="$(grep -HnE "${critical_patterns}" "${file_path}" 2>/dev/null || true)"
    if [ -n "${critical_matches}" ]; then
      matches+="${critical_matches}"$'\n'
    fi

    last_status="$(
      grep -nE "\\*\\*\\*[[:space:]]+(FAILED|SUCCESS)[[:space:]]+\\*\\*\\*|SIMULATION FAILED" \
        "${file_path}" 2>/dev/null | tail -n 1 || true
    )"
    if [[ -n "${last_status}" && "${last_status}" != *"SUCCESS"* ]]; then
      matches+="${file_path}:${last_status}"$'\n'
    fi
  done < <(
    find verif/sim -type f -name "*.iss" -print0 2>/dev/null || true
    if [ -d "build/${TIER_CONFIG}" ]; then
      find "build/${TIER_CONFIG}" -type f -name "*.iss" \
        -print0 2>/dev/null || true
    fi
  )

  if [ -n "${matches}" ]; then
    append_failure "ERROR: ISS trace failure patterns were found."
    printf "%s" "${matches}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi

  return 0
}

rc=0

log_info "Running ${TIER_NAME}: ${TIER_CONFIG} / ${TIER_TESTCASE} (${TIER_MODE})"
write_metadata

source_logged verif/sim/setup-env.sh
record_rc "$?"

if [ "${rc}" -eq 0 ] && [ "${TIER_MODE}" = "act4-prebuilt" ]; then
  log_info "Building standalone ${TIER_CONFIG} TestHarness without live Spike tandem"
  run_logged env -u SPIKE_TANDEM \
    make -j"${TIER_ACT4_BUILD_JOBS}" verilate target="${TIER_CONFIG}"
  record_rc "$?"

  if [ "${rc}" -eq 0 ]; then
    log_info "Running integrity-verified frozen ACT4 corpus without Sail or Spike"
    run_logged env -u SPIKE_TANDEM \
      ./cook.py act4-run \
      --target "${TIER_CONFIG}" \
      --corpus-directory "${TIER_ACT4_CORPUS}" \
      --simulator "${TIER_ACT4_SIMULATOR}" \
      --cycle-timeout "${TIER_ACT4_CYCLE_TIMEOUT}" \
      --wall-timeout-seconds "${TIER_ACT4_WALL_TIMEOUT_SECONDS}"
    act4_rc=$?
    if [ "${act4_rc}" -eq 0 ]; then
      ACT4_RUNTIME_RESULT="pass"
    else
      ACT4_RUNTIME_RESULT="fail"
    fi
    record_rc "${act4_rc}"
  fi
elif [ "${rc}" -eq 0 ] && [ "${TIER_MODE}" = "cook-testlist" ]; then
  if [ -n "${TIER_INSTALL_SCRIPT}" ]; then
    source_logged "verif/regress/${TIER_INSTALL_SCRIPT}.sh"
    record_rc "$?"
  fi

  if [ "${rc}" -eq 0 ]; then
    run_logged python3 .github/scripts/prepare-cook-toolchains.py \
      --output-dir "${COOK_CONFIG_DIR}"
    record_rc "$?"
  fi

  export CONFIG_DIR="${COOK_CONFIG_DIR}"

  export DASHBOARD_JOB_TITLE="${TIER_CONFIG} ${TIER_TESTCASE} public tandem"
  export DASHBOARD_JOB_DESCRIPTION="cook.py Verilator TestHarness and Spike validation"
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
    run_logged ./cook.py verilator-testharness-run-testlist \
      --target "${TIER_CONFIG}" \
      --testlist "${TIER_TESTLIST}" \
      --tandem-enabled \
      --iss-timeout "${TIER_ISS_TIMEOUT}"
    record_rc "$?"
  fi
elif [ "${rc}" -eq 0 ] && [ "${TIER_MODE}" = "testlist" ]; then
  if [[ "${TIER_SIMULATOR}" == *"veri-testharness"* ]]; then
    source_logged verif/regress/install-verilator.sh
    record_rc "$?"
  fi

  if [ "${rc}" -eq 0 ]; then
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
      "--issrun_opts=+tb_performance_mode+debug_disable=1+UVM_VERBOSITY=UVM_NONE"
    )

    if [ -n "${TIER_LINKER}" ]; then
      cva6_cmd+=("--linker=${TIER_LINKER}")
    fi

    if [ -n "${TIER_TEST_NAME}" ]; then
      cva6_cmd+=(--test "${TIER_TEST_NAME}")
    fi

    pushd verif/sim > /dev/null || rc=$?
    if [ "${rc}" -eq 0 ]; then
      run_logged "${cva6_cmd[@]}"
      record_rc "$?"
    fi
    popd > /dev/null || true
  fi
elif [ "${rc}" -eq 0 ]; then
  if [ -n "${TIER_HWCONFIG_OPTS}" ]; then
    export DV_HWCONFIG_OPTS="${TIER_HWCONFIG_OPTS}"
  fi

  run_logged env \
    DV_SIMULATORS="${TIER_SIMULATOR}" \
    DV_TARGET="${TIER_CONFIG}" \
    bash -e "verif/regress/${TIER_TESTCASE}.sh"
  record_rc "$?"
fi

collect_reports

if [ "${rc}" -eq 0 ]; then
  if [ "${TIER_MODE}" = "act4-prebuilt" ]; then
    act4_report="artifacts/reports/report_act4_${TIER_CONFIG}.yml"
    if [ ! -s "${act4_report}" ]; then
      append_failure "ERROR: act4-prebuilt mode produced no ACT4 Cook report."
      rc=1
    elif ! find "artifacts/act4/${TIER_CONFIG}" -type f -name "*.log" \
      -print -quit 2>/dev/null | grep -q .; then
      append_failure "ERROR: act4-prebuilt mode produced no per-test ACT4 logs."
      rc=1
    fi
  elif [ "${TIER_MODE}" = "cook-testlist" ]; then
    if ! find "build/${TIER_CONFIG}/simulation/sim_verilator_testharness" \
      -mindepth 1 -print -quit 2>/dev/null | grep -q .; then
      append_failure "ERROR: cook-testlist mode produced no simulation results."
      rc=1
    fi
  elif ! compgen -G "verif/sim/out*" > /dev/null; then
    append_failure "ERROR: ${TIER_NAME} job produced no verif/sim/out* results."
    rc=1
  fi
fi

scan_rc=0
scan_for_failures || scan_rc=1
scan_iss_traces || scan_rc=1
if [ "${rc}" -eq 0 ] && [ "${scan_rc}" -ne 0 ]; then
  rc=1
fi
if [ "${rc}" -ne 0 ] && [ ! -s "${FAILURE_SUMMARY}" ]; then
  append_failure "Regression exited with code ${rc}; inspect run.log for details."
fi

write_metadata
echo "${rc}" > "${EXIT_CODE_FILE}"
exit "${rc}"
