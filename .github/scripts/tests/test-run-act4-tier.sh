#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

CVA6_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ADAPTER="${CVA6_REPO_DIR}/.github/scripts/run-act4-tier.sh"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEST_ROOT}"' EXIT

assert_file_equals() {
  local expected="$1"
  local path="$2"
  local actual
  actual="$(cat "${path}")"
  [[ "${actual}" == "${expected}" ]] || {
    echo "Expected ${path} to contain '${expected}', got '${actual}'" >&2
    exit 1
  }
}

run_case() {
  local name="$1"
  local wrapper_rc="$2"
  local summary_text="$3"
  local expected_rc="$4"
  local case_dir="${TEST_ROOT}/${name}"
  local wrapper="${case_dir}/wrapper.sh"
  local summary="${case_dir}/summary.txt"
  local results="${case_dir}/results"

  mkdir -p "${case_dir}"
  printf '#!/usr/bin/env bash\n' > "${wrapper}"
  if [[ -n "${summary_text}" ]]; then
    printf 'printf "%%s\\n" %q > %q\n' "${summary_text}" "${summary}" >> "${wrapper}"
  fi
  printf 'exit %s\n' "${wrapper_rc}" >> "${wrapper}"
  chmod +x "${wrapper}"

  set +e
  CVA6_REPO_DIR="${CVA6_REPO_DIR}" \
  TIER_RESULTS_DIR="${results}" \
  ACT4_WRAPPER="${wrapper}" \
  ACT4_SUMMARY_FILE="${summary}" \
    bash "${ADAPTER}" >/dev/null 2>&1
  actual_rc=$?
  set -e

  [[ "${actual_rc}" -eq "${expected_rc}" ]] || {
    echo "Case ${name}: expected rc=${expected_rc}, got rc=${actual_rc}" >&2
    exit 1
  }
  assert_file_equals "${expected_rc}" "${results}/exit_code"
}

run_case success 0 "TOTAL=124 PASS=124 FAIL=0" 0
run_case wrapper-failure 7 "TOTAL=124 PASS=124 FAIL=0" 7
run_case reported-failure 0 "TOTAL=124 PASS=123 FAIL=1" 1
run_case incomplete-suite 0 "TOTAL=123 PASS=123 FAIL=0" 1
run_case zero-tests 0 "TOTAL=0 PASS=0 FAIL=0" 1
run_case malformed-summary 0 "ACT4 finished" 1
run_case missing-summary 0 "" 1
run_case duplicate-summary 0 $'TOTAL=124 PASS=124 FAIL=0\nTOTAL=124 PASS=124 FAIL=0' 1
run_case trailing-garbage 0 $'TOTAL=124 PASS=124 FAIL=0\nACT4 finished' 1

echo "ACT4 Tier result-contract tests passed"
