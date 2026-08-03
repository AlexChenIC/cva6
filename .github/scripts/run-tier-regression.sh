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
COOK_CONFIG_DIR="${RESULTS_DIR}/cook-config"

mkdir -p "${RESULTS_DIR}"
: > "${RUN_LOG}"
: > "${FAILURE_SUMMARY}"
echo "1" > "${EXIT_CODE_FILE}"

TIER_NAME="${TIER_NAME:-Tier}"
TIER_MODE="${TIER_MODE:-script}"
TIER_CONFIG="${TIER_CONFIG:?TIER_CONFIG is required}"
TIER_TESTCASE="${TIER_TESTCASE:?TIER_TESTCASE is required}"
TIER_SIMULATOR="${TIER_SIMULATOR:?TIER_SIMULATOR is required}"
TIER_INSTALL_SCRIPT="${TIER_INSTALL_SCRIPT:-}"
TIER_TESTLIST="${TIER_TESTLIST:-}"
TIER_TEST_NAME="${TIER_TEST_NAME:-}"
TIER_LINKER="${TIER_LINKER:-}"
TIER_ISA_EXTENSIONS="${TIER_ISA_EXTENSIONS:-}"
TIER_HWCONFIG_OPTS="${TIER_HWCONFIG_OPTS:-}"
TIER_TOOLCHAIN="${TIER_TOOLCHAIN:-github_actions_gcc}"
TIER_COMPILER_MARCH="${TIER_COMPILER_MARCH:-}"
TIER_COMPILER_MARCH_REASON="${TIER_COMPILER_MARCH_REASON:-}"
TIER_EXPECTED_HIER="${TIER_EXPECTED_HIER:-}"
TIER_ISS_TIMEOUT="${TIER_ISS_TIMEOUT:-30000}"
TIER_VALIDATE_ONLY="${TIER_VALIDATE_ONLY:-0}"
TIER_EVENT_HEAD_SHA="${TIER_EVENT_HEAD_SHA:-}"
TIER_EVENT_BASE_SHA="${TIER_EVENT_BASE_SHA:-}"

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

yaml_scalar() {
  local key="$1"
  local file_path="$2"
  sed -nE "s/^[[:space:]]*${key}:[[:space:]]*([^#[:space:]]+).*/\1/p" \
    "${file_path}" | head -n 1
}

source_worktree_dirty() {
  [ -n "$(
    git status --porcelain --untracked-files=normal \
      --ignore-submodules=untracked -- \
      . \
      ':(exclude)ci-results' ':(exclude)ci-results/**' \
      ':(exclude)build' ':(exclude)build/**' \
      ':(exclude)artifacts' ':(exclude)artifacts/**' \
      2>/dev/null
  )" ]
}

write_metadata() {
  local target_dir="config/target/${TIER_CONFIG}"
  local isa_file="${target_dir}/isa.yml"
  local spike_file="${target_dir}/spike.yaml"
  local linker_file="${target_dir}/link.ld"
  local testbench_file="${target_dir}/testbench_cfg.yml"
  local execution_entry="verif/regress/${TIER_TESTCASE}.sh"
  local compile_recipe="not_applicable"
  local run_recipe="legacy_script"
  local testbench="legacy_regression"
  local public_backend="${TIER_SIMULATOR}"
  local reference_model="not_enabled"

  if [[ "${TIER_SIMULATOR}" == *"spike"* ]]; then
    reference_model="Spike"
  fi

  if [ "${TIER_MODE}" = "testlist" ]; then
    execution_entry="verif/sim/cva6.py"
    run_recipe="legacy_cva6_testlist"
    testbench="legacy_cva6"
  elif [ "${TIER_MODE}" = "cook-testlist" ]; then
    execution_entry="./cook.py"
    compile_recipe="sw-compile-testlist"
    run_recipe="verilator-testharness-run-testlist"
    testbench="TestHarness"
    public_backend="Verilator_TestHarness"
  fi

  {
    echo "schema_version=2"
    echo "comparison_contract_version=1"
    echo "tier=${TIER_NAME}"
    echo "mode=${TIER_MODE}"
    echo "config=${TIER_CONFIG}"
    echo "expected_hier=${TIER_EXPECTED_HIER}"
    echo "testcase=${TIER_TESTCASE}"
    echo "testlist=${TIER_TESTLIST}"
    echo "test_name=${TIER_TEST_NAME}"
    echo "execution_entry=${execution_entry}"
    echo "compile_recipe=${compile_recipe}"
    echo "run_recipe=${run_recipe}"
    echo "toolchain=${TIER_TOOLCHAIN}"
    echo "compiler_march=${TIER_COMPILER_MARCH}"
    echo "compiler_march_reason=${TIER_COMPILER_MARCH_REASON}"
    echo "canonical_march=$(yaml_scalar march "${isa_file}" 2>/dev/null || true)"
    echo "canonical_mabi=$(yaml_scalar mabi "${isa_file}" 2>/dev/null || true)"
    echo "simulator=${TIER_SIMULATOR}"
    echo "testbench=${testbench}"
    echo "reference_model=${reference_model}"
    echo "public_backend=${public_backend}"
    echo "linker=${TIER_LINKER}"
    echo "isa_extensions=${TIER_ISA_EXTENSIONS}"
    echo "validate_only=${TIER_VALIDATE_ONLY}"
    echo "spike_tandem=${SPIKE_TANDEM:-0}"
    if [ "${TIER_MODE}" = "cook-testlist" ]; then
      echo "shared_with_thales=target,testlist,linker,spike_yaml,cook_compile_contract,report_schema"
      echo "different_from_thales=compiler_binary,rtl_simulator,testbench"
      echo "thales_backend=VCS_UVM"
    fi
    echo "repository=${GITHUB_REPOSITORY:-local}"
    echo "workflow=${GITHUB_WORKFLOW:-local}"
    echo "run_id=${GITHUB_RUN_ID:-local}"
    echo "run_attempt=${GITHUB_RUN_ATTEMPT:-local}"
    echo "event=${GITHUB_EVENT_NAME:-local}"
    echo "tested_ref=${GITHUB_REF_NAME:-$(git branch --show-current)}"
    echo "event_sha=${GITHUB_SHA:-not_available}"
    echo "event_head_sha=${TIER_EVENT_HEAD_SHA:-not_available}"
    echo "event_base_sha=${TIER_EVENT_BASE_SHA:-not_available}"
    echo "source_sha=$(git rev-parse HEAD)"
    if source_worktree_dirty; then
      echo "source_worktree_dirty=true"
    else
      echo "source_worktree_dirty=false"
    fi
    echo "core_v_verif_sha=$(git -C verif/core-v-verif rev-parse HEAD)"
    echo "cvfpu_sha=$(git -C core/cvfpu rev-parse HEAD)"
    echo "hpdcache_sha=$(git -C core/cache_subsystem/hpdcache rev-parse HEAD)"
    [ ! -f "${isa_file}" ] || echo "isa_config_blob=$(git hash-object "${isa_file}")"
    [ ! -f "${spike_file}" ] || echo "spike_config_blob=$(git hash-object "${spike_file}")"
    [ ! -f "${linker_file}" ] || echo "linker_blob=$(git hash-object "${linker_file}")"
    [ ! -f "${testbench_file}" ] || echo "testbench_config_blob=$(git hash-object "${testbench_file}")"
    [ ! -f "${TIER_TESTLIST}" ] || echo "testlist_blob=$(git hash-object "${TIER_TESTLIST}")"
    echo "cook_config_dir=${CONFIG_DIR:-not_prepared}"
    echo "cv_sw_prefix=${CV_SW_PREFIX:-not_prepared}"
    [ ! -f "${COOK_CONFIG_DIR}/compiler.yml" ] || echo "compiler_config_blob=$(git hash-object "${COOK_CONFIG_DIR}/compiler.yml")"
    [ ! -f "${COOK_CONFIG_DIR}/environment.yml" ] || echo "compiler_environment_blob=$(git hash-object "${COOK_CONFIG_DIR}/environment.yml")"
    [ ! -f "${RESULTS_DIR}/thales-matrix-alignment.yml" ] || echo "thales_alignment_blob=$(git hash-object "${RESULTS_DIR}/thales-matrix-alignment.yml")"
    [ ! -f "flows/recipes/sw_compile_testlist.py" ] || echo "cook_compile_recipe_blob=$(git hash-object flows/recipes/sw_compile_testlist.py)"
    [ ! -f "flows/recipes/verilator_testharness_run_testlist.py" ] || echo "public_run_recipe_blob=$(git hash-object flows/recipes/verilator_testharness_run_testlist.py)"
    if [ -f "${RESULTS_DIR}/thales-matrix-alignment.yml" ]; then
      echo "thales_matrix_alignment=PASS"
    else
      echo "thales_matrix_alignment=not_checked"
    fi
  } > "${METADATA_FILE}"
}

validate_expected_hierarchy() {
  local target_dir="config/target/${TIER_CONFIG}"
  local actual_hier=""

  if [ -z "${TIER_EXPECTED_HIER}" ]; then
    return 0
  fi
  if [ ! -f "${target_dir}/testbench_cfg.yml" ]; then
    append_failure "ERROR: target has no testbench_cfg.yml: ${target_dir}"
    return 1
  fi
  actual_hier="$(yaml_scalar hier "${target_dir}/testbench_cfg.yml")"
  if [ "${actual_hier}" != "${TIER_EXPECTED_HIER}" ]; then
    append_failure "ERROR: ${TIER_CONFIG} uses hier=${actual_hier:-unknown}; expected ${TIER_EXPECTED_HIER}."
    return 1
  fi
}

validate_inputs() {
  local target_dir="config/target/${TIER_CONFIG}"
  local testlist_path=""
  local required_file=""

  if [ -n "${TIER_INSTALL_SCRIPT}" ] && [ ! -f "verif/regress/${TIER_INSTALL_SCRIPT}.sh" ]; then
    append_failure "ERROR: install script does not exist: verif/regress/${TIER_INSTALL_SCRIPT}.sh"
    return 1
  fi

  if ! validate_expected_hierarchy; then
    return 1
  fi

  case "${TIER_MODE}" in
    script)
      if [ ! -f "verif/regress/${TIER_TESTCASE}.sh" ]; then
        append_failure "ERROR: regression script does not exist: verif/regress/${TIER_TESTCASE}.sh"
        return 1
      fi
      ;;
    testlist)
      if [ -z "${TIER_TESTLIST}" ]; then
        append_failure "ERROR: TIER_TESTLIST is required in testlist mode."
        return 1
      fi
      testlist_path="verif/sim/${TIER_TESTLIST}"
      if [ ! -f "${testlist_path}" ]; then
        append_failure "ERROR: test list does not exist: ${testlist_path}"
        return 1
      fi
      ;;
    cook-testlist)
      if [ ! -d "${target_dir}" ]; then
        append_failure "ERROR: target directory does not exist: ${target_dir}"
        return 1
      fi
      for required_file in isa.yml link.ld spike.yaml testbench_cfg.yml; do
        if [ ! -f "${target_dir}/${required_file}" ]; then
          append_failure "ERROR: target file does not exist: ${target_dir}/${required_file}"
          return 1
        fi
      done
      if [ "${TIER_SIMULATOR}" != "veri-testharness,spike" ]; then
        append_failure "ERROR: unsupported public backend: ${TIER_SIMULATOR}; expected veri-testharness,spike."
        return 1
      fi
      if [ -z "${TIER_TESTLIST}" ] || [ ! -f "${TIER_TESTLIST}" ]; then
        append_failure "ERROR: test list does not exist: ${TIER_TESTLIST:-unset}"
        return 1
      fi
      if [ ! -f "flows/recipes/verilator_testharness_run_testlist.py" ]; then
        append_failure "ERROR: cook.py Verilator TestHarness recipe is missing."
        return 1
      fi
      ;;
    *)
      append_failure "ERROR: unsupported Tier mode: ${TIER_MODE}"
      return 1
      ;;
  esac
}

collect_reports() {
  local file_path=""
  local relative_path=""
  local safe_name=""

  if [ "${TIER_MODE}" = "cook-testlist" ]; then
    while IFS= read -r -d '' file_path; do
      relative_path="${file_path#build/"${TIER_CONFIG}"/}"
      safe_name="${relative_path//\//__}"
      cp "${file_path}" "${RESULTS_DIR}/${safe_name}"
    done < <(
      find "build/${TIER_CONFIG}" -type f \
        \( -name "iss_regr.log" -o -name "cook_testharness.log" \) \
        -print0 2>/dev/null || true
    )

    while IFS= read -r -d '' file_path; do
      cp "${file_path}" "${RESULTS_DIR}/$(basename "${file_path}")"
    done < <(find artifacts/reports -type f -name "report_*.yml" -print0 2>/dev/null || true)
  else
    while IFS= read -r -d '' file_path; do
      relative_path="${file_path#verif/sim/}"
      safe_name="${relative_path//\//__}"
      cp "${file_path}" "${RESULTS_DIR}/${safe_name}"
    done < <(find verif/sim -type f -name "iss_regr.log" -print0 2>/dev/null || true)
  fi
}

append_scan_files() {
  local file_path=""

  if [ "${TIER_MODE}" = "cook-testlist" ]; then
    while IFS= read -r -d '' file_path; do
      scan_files+=("${file_path}")
    done < <(
      find "build/${TIER_CONFIG}" -type f \
        \( -name "*.log" -o -name "*.txt" -o -name "*.iss" \) \
        -print0 2>/dev/null || true
    )
  else
    while IFS= read -r -d '' file_path; do
      scan_files+=("${file_path}")
    done < <(
      find verif/sim -type f \
        \( -name "*.log" -o -name "*.txt" -o -name "*.iss" \) \
        -print0 2>/dev/null || true
    )
  fi
}

scan_for_failures() {
  local matches=""
  local -a scan_files=("${RUN_LOG}")

  append_scan_files
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
}

scan_one_iss_trace() {
  local file_path="$1"
  local critical_patterns="ERROR return code:|bad syscall|unrecognized opcode|extension .* required|terminate called|Traceback \(most recent call last\)"
  local critical_matches=""
  local last_status=""

  critical_matches="$(grep -HnE "${critical_patterns}" "${file_path}" 2>/dev/null || true)"
  if [ -n "${critical_matches}" ]; then
    iss_matches+="${critical_matches}"$'\n'
  fi
  last_status="$(
    grep -nE "\*\*\*[[:space:]]+(FAILED|SUCCESS)[[:space:]]+\*\*\*|SIMULATION FAILED" \
      "${file_path}" 2>/dev/null | tail -n 1 || true
  )"
  if [[ -n "${last_status}" && "${last_status}" != *"SUCCESS"* ]]; then
    iss_matches+="${file_path}:${last_status}"$'\n'
  fi
}

scan_iss_traces() {
  local file_path=""
  local iss_matches=""

  if [ "${TIER_MODE}" = "cook-testlist" ]; then
    while IFS= read -r -d '' file_path; do
      scan_one_iss_trace "${file_path}"
    done < <(find "build/${TIER_CONFIG}" -type f -name "*.iss" -print0 2>/dev/null || true)
  else
    while IFS= read -r -d '' file_path; do
      scan_one_iss_trace "${file_path}"
    done < <(find verif/sim -type f -name "*.iss" -print0 2>/dev/null || true)
  fi

  if [ -n "${iss_matches}" ]; then
    append_failure "ERROR: ${TIER_NAME} command returned success, but ISS trace failures were found."
    printf "%s" "${iss_matches}" | tee -a "${FAILURE_SUMMARY}" >&2
    return 1
  fi
}

rc=0
write_metadata
log_info "Running ${TIER_NAME}: ${TIER_CONFIG} / ${TIER_TESTCASE} (${TIER_MODE})"

if ! validate_inputs; then
  rc=1
fi

if [ "${rc}" -eq 0 ] && [ "${TIER_MODE}" = "cook-testlist" ]; then
  matrix_check_cmd=(
    python3 .github/scripts/check-thales-matrix-alignment.py
    --target "${TIER_CONFIG}"
    --testlist "${TIER_TESTLIST}"
    --output "${RESULTS_DIR}/thales-matrix-alignment.yml"
  )
  if [ -n "${TIER_TEST_NAME}" ]; then
    matrix_check_cmd+=(--test-name "${TIER_TEST_NAME}")
  fi
  run_logged "${matrix_check_cmd[@]}"
  record_rc "$?"
  write_metadata
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

if [ "${rc}" -eq 0 ] && [ "${TIER_MODE}" != "script" ]; then
  if [[ "${TIER_SIMULATOR}" == *"veri-testharness"* ]]; then
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
fi

if [ "${rc}" -eq 0 ] && [ "${TIER_MODE}" = "cook-testlist" ]; then
  run_logged python3 .github/scripts/prepare-cook-config.py \
    --output-dir "${COOK_CONFIG_DIR}"
  record_rc "$?"
  export CONFIG_DIR="${COOK_CONFIG_DIR}"
  write_metadata
fi

if [ "${rc}" -eq 0 ]; then
  case "${TIER_MODE}" in
    script)
      if [ -n "${TIER_HWCONFIG_OPTS}" ]; then
        export DV_HWCONFIG_OPTS="${TIER_HWCONFIG_OPTS}"
      fi
      run_logged env \
        DV_SIMULATORS="${TIER_SIMULATOR}" \
        DV_TARGET="${TIER_CONFIG}" \
        bash -e "verif/regress/${TIER_TESTCASE}.sh"
      record_rc "$?"
      ;;
    testlist)
      cva6_cmd=(
        python3 cva6.py
        "--testlist=${TIER_TESTLIST}"
        --target "${TIER_CONFIG}"
        --iss_yaml=cva6.yaml
        "--iss=${TIER_SIMULATOR}"
        "--iss_timeout=${TIER_ISS_TIMEOUT}"
        "--issrun_opts=+tb_performance_mode+debug_disable=1+UVM_VERBOSITY=UVM_NONE"
      )
      [ -z "${TIER_TEST_NAME}" ] || cva6_cmd+=(--test "${TIER_TEST_NAME}")
      [ -z "${TIER_LINKER}" ] || cva6_cmd+=("--linker=${TIER_LINKER}")
      [ -z "${TIER_ISA_EXTENSIONS}" ] || cva6_cmd+=("--isa_extension=${TIER_ISA_EXTENSIONS}")
      pushd verif/sim > /dev/null || rc=$?
      if [ "${rc}" -eq 0 ]; then
        run_logged "${cva6_cmd[@]}"
        record_rc "$?"
      fi
      popd > /dev/null || true
      ;;
    cook-testlist)
      export DASHBOARD_JOB_TITLE="${TIER_CONFIG} ${TIER_TESTCASE} public tandem"
      export DASHBOARD_JOB_DESCRIPTION="cook.py-aligned Verilator TestHarness and Spike validation"
      export DASHBOARD_JOB_CATEGORY="testlist"
      export CI_JOB_ID="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-${TIER_CONFIG}-${TIER_TESTCASE}"
      export CI_JOB_URL="https://github.com/${GITHUB_REPOSITORY:-local}/actions/runs/${GITHUB_RUN_ID:-local}"
      export CI_JOB_STAGE="${TIER_NAME}"

      cook_compile_cmd=(
        ./cook.py sw-compile-testlist
        --target "${TIER_CONFIG}"
        --toolchain "${TIER_TOOLCHAIN}"
        --testlist "${TIER_TESTLIST}"
      )
      [ -z "${TIER_TEST_NAME}" ] || cook_compile_cmd+=(--testname "${TIER_TEST_NAME}")
      [ -z "${TIER_COMPILER_MARCH}" ] || cook_compile_cmd+=(--march "${TIER_COMPILER_MARCH}")
      run_logged "${cook_compile_cmd[@]}"
      record_rc "$?"

      if [ "${rc}" -eq 0 ]; then
        cook_run_cmd=(
          ./cook.py verilator-testharness-run-testlist
          --target "${TIER_CONFIG}"
          --testlist "${TIER_TESTLIST}"
          --tandem-enabled
          --iss-timeout "${TIER_ISS_TIMEOUT}"
        )
        [ -z "${TIER_TEST_NAME}" ] || cook_run_cmd+=(--testname "${TIER_TEST_NAME}")
        run_logged "${cook_run_cmd[@]}"
        record_rc "$?"
      fi
      ;;
  esac
fi

collect_reports

if [ "${rc}" -eq 0 ]; then
  if [ "${TIER_MODE}" = "cook-testlist" ]; then
    if [ ! -d "build/${TIER_CONFIG}/compile" ]; then
      append_failure "ERROR: cook.py produced no compile directory for ${TIER_CONFIG}."
      rc=1
    elif [ ! -d "build/${TIER_CONFIG}/simulation/sim_verilator_testharness" ]; then
      append_failure "ERROR: cook.py produced no TestHarness simulation results for ${TIER_CONFIG}."
      rc=1
    fi
  elif ! compgen -G "verif/sim/out*" > /dev/null; then
    append_failure "ERROR: ${TIER_NAME} command returned success but produced no verif/sim/out* results."
    rc=1
  fi
fi

if [ "${rc}" -eq 0 ] && ! scan_for_failures; then
  rc=1
fi

if [ "${rc}" -eq 0 ] && ! scan_iss_traces; then
  rc=1
fi

echo "${rc}" > "${EXIT_CODE_FILE}"
exit "${rc}"
