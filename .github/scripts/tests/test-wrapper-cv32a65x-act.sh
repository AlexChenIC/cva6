#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# The single-quoted strings below intentionally generate mock shell scripts.
# shellcheck disable=SC2016

set -euo pipefail

CVA6_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WRAPPER="${CVA6_REPO_DIR}/verif/regress/wrapper-cv32a65x-act.sh"
SOURCE_CONFIG="${CVA6_REPO_DIR}/external/act4/config/cores/cva6/cv32a65x/cv32a65x.yaml"
SOURCE_PATCH="${CVA6_REPO_DIR}/verif/regress/act4/cv32a65x-hpm.patch"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEST_ROOT}"' EXIT

write_executable() {
  local path="$1"
  shift
  printf '%s\n' "$@" > "${path}"
  chmod +x "${path}"
}

run_case() {
  local name="$1"
  local sim_mode="$2"
  local expected_rc="$3"
  local expected_summary="$4"
  local fixture="${TEST_ROOT}/${name}"
  local fake_root="${fixture}/cva6"
  local fake_act4="${fixture}/act4"
  local fake_bin="${fixture}/bin"
  local results="${fixture}/results"
  local config_path="${fake_act4}/config/cores/cva6/cv32a65x/cv32a65x.yaml"
  local expected_manifest="${fixture}/expected-manifest.txt"
  local act4_gcc_alias_dir="${fake_root}/tools/act4-gcc/aliases"

  mkdir -p \
    "${fake_root}/verif/regress/act4" \
    "${fake_root}/verif/sim" \
    "${fake_root}/config/gen_from_riscv_config/cv32a65x/spike" \
    "${fake_root}/riscv" \
    "${act4_gcc_alias_dir}" \
    "${fake_act4}/config/cores/cva6/cv32a65x" \
    "${fake_act4}/framework/src/act/data/vendor/bundle/mock gem" \
    "${fake_bin}"

  cp "${SOURCE_PATCH}" "${fake_root}/verif/regress/act4/cv32a65x-hpm.patch"
  cp "${SOURCE_CONFIG}" "${config_path}"
  : > "${fake_root}/config/gen_from_riscv_config/cv32a65x/spike/spike.yaml"

  write_executable "${fake_root}/verif/regress/install-verilator.sh" '#!/usr/bin/env bash' ':'
  write_executable "${fake_root}/verif/regress/install-spike.sh" '#!/usr/bin/env bash' ':'
  write_executable "${fake_root}/verif/sim/setup-env.sh" '#!/usr/bin/env bash' ':'

  for command_name in uv bundle sail_riscv_sim; do
    write_executable "${fake_bin}/${command_name}" '#!/usr/bin/env bash' 'exit 0'
  done

  # setup-env.sh would leave this generic GCC first on PATH.
  write_executable "${fake_bin}/riscv64-unknown-elf-gcc" \
    '#!/usr/bin/env bash' \
    'echo "13.2.0"'
  write_executable "${act4_gcc_alias_dir}/riscv64-unknown-elf-gcc" \
    '#!/usr/bin/env bash' \
    'echo "15.2.0"'

  write_executable "${fake_bin}/riscv64-unknown-elf-nm" \
    '#!/usr/bin/env bash' \
    'echo "00001000 D tohost"'

  write_executable "${fake_bin}/make" \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'if [[ "$1" == "-C" && "$2" == "${MOCK_ACT4_PKG}" ]]; then' \
    '  if [[ " $* " == *" clean "* ]]; then' \
    '    rm -rf "${MOCK_ACT4_PKG}/work"' \
    '    exit 0' \
    '  fi' \
    '  values="$(awk '"'"'/HPM_COUNTER_EN:/{capture=1; next} capture && /true|false/{gsub(/[ ,]/, ""); print; count++; if (count == 3) exit}'"'"' "${MOCK_ACT4_PKG}/config/cores/cva6/cv32a65x/cv32a65x.yaml" | paste -sd, -)"' \
    '  [[ "${values}" == "false,false,false" ]] || exit 33' \
    '  mkdir -p "${MOCK_ACT4_PKG}/work/cv32a65x/elfs/rv32i/I"' \
    '  : > "${MOCK_ACT4_PKG}/work/cv32a65x/elfs/rv32i/I/mock.elf"' \
    '  exit 0' \
    'fi' \
    'mkdir -p "${MOCK_CVA6_ROOT}/work-ver"' \
    'cp "${MOCK_SIMULATOR_TEMPLATE}" "${MOCK_CVA6_ROOT}/work-ver/Variane_testharness"' \
    'chmod +x "${MOCK_CVA6_ROOT}/work-ver/Variane_testharness"'

  if [[ "${sim_mode}" == "manifest-mismatch" ]]; then
    printf 'rv32i/I/not-generated.elf\n' > "${expected_manifest}"
  else
    printf 'rv32i/I/mock.elf\n' > "${expected_manifest}"
  fi

  write_executable "${fixture}/simulator-template.sh" \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'report_file=""' \
    'have_core=0' \
    'have_config=0' \
    'have_elf=0' \
    'have_max_cycles=0' \
    'have_uvm_test=0' \
    'for arg in "$@"; do' \
    '  case "${arg}" in' \
    '    +report_file=*) report_file="${arg#+report_file=}" ;;' \
    '    +core_name=cv32a65x) have_core=1 ;;' \
    '    +config_file=*) have_config=1 ;;' \
    '    ++*.elf) have_elf=1 ;;' \
    '    +max-cycles=10000000) have_max_cycles=1 ;;' \
    '    +UVM_TESTNAME=uvmt_cva6_firmware_test_c) have_uvm_test=1 ;;' \
    '  esac' \
    'done' \
    '[[ -n "${report_file}" ]] || exit 2' \
    '[[ "${have_core}${have_config}${have_elf}${have_max_cycles}${have_uvm_test}" == "11111" ]] || exit 3' \
    'mkdir -p "$(dirname "${report_file}")"' \
    'if [[ "${MOCK_SIM_MODE}" == "pass" ]]; then' \
    '  printf "exit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST PASSED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    'elif [[ "${MOCK_SIM_MODE}" == "process-failure" ]]; then' \
    '  printf "exit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST PASSED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    '  exit 9' \
    'elif [[ "${MOCK_SIM_MODE}" == "bad-report" ]]; then' \
    '  printf "exit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x1\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST PASSED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    'elif [[ "${MOCK_SIM_MODE}" == "rvcp-failure" ]]; then' \
    '  printf "exit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST FAILED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    'elif [[ "${MOCK_SIM_MODE}" == "missing-rvcp" ]]; then' \
    '  printf "exit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo "SIMULATION PASSED"' \
    'elif [[ "${MOCK_SIM_MODE}" == "zero-instr" ]]; then' \
    '  printf "exit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x0\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST PASSED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    'elif [[ "${MOCK_SIM_MODE}" == "bad-exit-cause" ]]; then' \
    '  printf "exit_cause: MISMATCH\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST PASSED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    'elif [[ "${MOCK_SIM_MODE}" == "duplicate-report-key" ]]; then' \
    '  printf "exit_cause: MISMATCH\\nexit_cause: SUCCESS\\nexit_code: 0x0000\\ninstr_count: 0x10\\nmismatches_count: 0x0\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST PASSED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION PASSED"' \
    'else' \
    '  printf "exit_cause: MISMATCH\\nexit_code: 0x0001\\ninstr_count: 0x10\\nmismatches_count: 0x1\\n" > "${report_file}"' \
    '  echo '\''RVCP-SUMMARY: TEST FAILED - Test File "mock.elf"'\''' \
    '  echo "SIMULATION FAILED"' \
    'fi'

  git init -q "${fake_act4}"
  git -C "${fake_act4}" config user.name "ACT4 Tier Test"
  git -C "${fake_act4}" config user.email "act4-tier-test@example.invalid"
  git -C "${fake_act4}" add config
  git -C "${fake_act4}" commit -qm "fixture"
  expected_sha="$(git -C "${fake_act4}" rev-parse HEAD)"
  # ruby/setup-ruby installs locked gems here before the wrapper runs.
  : > "${fake_act4}/framework/src/act/data/vendor/bundle/mock gem/library file.rb"
  if [[ "${sim_mode}" == "dirty-act4" ]]; then
    : > "${fake_act4}/untracked-input.yaml"
  fi

  set +e
  PATH="${fake_bin}:${PATH}" \
  CVA6_REPO_DIR="${fake_root}" \
  ACT4_PKG="${fake_act4}" \
  ACT4_EXPECTED_SHA="${expected_sha}" \
  ACT4_EXPECTED_MANIFEST="${expected_manifest}" \
  ACT4_EXPECTED_TESTS=1 \
  ACT4_GCC_ALIAS_DIR="${act4_gcc_alias_dir}" \
  ACT4_RESULTS_DIR="${results}" \
  RISCV="${fake_root}/riscv" \
  NUM_JOBS=2 \
  MOCK_ACT4_PKG="${fake_act4}" \
  MOCK_CVA6_ROOT="${fake_root}" \
  MOCK_SIMULATOR_TEMPLATE="${fixture}/simulator-template.sh" \
  MOCK_SIM_MODE="${sim_mode}" \
    bash "${WRAPPER}" > "${fixture}/wrapper.log" 2>&1
  actual_rc=$?
  set -e

  [[ "${actual_rc}" -eq "${expected_rc}" ]] || {
    cat "${fixture}/wrapper.log" >&2
    echo "Case ${name}: expected rc=${expected_rc}, got rc=${actual_rc}" >&2
    exit 1
  }
  if [[ -n "${expected_summary}" ]]; then
    grep -qx "${expected_summary}" "${results}/certification_summary.txt"
  else
    [[ ! -f "${results}/certification_summary.txt" ]]
  fi
  git -C "${fake_act4}" diff --quiet -- config
}

run_case success pass 0 "TOTAL=1 PASS=1 FAIL=0"
run_case simulation-failure fail 1 "TOTAL=1 PASS=0 FAIL=1"
run_case simulator-process-failure process-failure 1 "TOTAL=1 PASS=0 FAIL=1"
run_case report-mismatch bad-report 1 "TOTAL=1 PASS=0 FAIL=1"
run_case rvcp-failure rvcp-failure 1 "TOTAL=1 PASS=0 FAIL=1"
run_case missing-rvcp missing-rvcp 1 "TOTAL=1 PASS=0 FAIL=1"
run_case zero-instruction-report zero-instr 1 "TOTAL=1 PASS=0 FAIL=1"
run_case bad-exit-cause bad-exit-cause 1 "TOTAL=1 PASS=0 FAIL=1"
run_case duplicate-report-key duplicate-report-key 1 "TOTAL=1 PASS=0 FAIL=1"
run_case manifest-mismatch manifest-mismatch 1 ""
run_case dirty-act4-input dirty-act4 1 ""

echo "ACT4 wrapper mock-integration tests passed"
