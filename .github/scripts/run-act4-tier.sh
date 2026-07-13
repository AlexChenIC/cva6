#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

CVA6_REPO_DIR="${CVA6_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TIER_RESULTS_DIR="${TIER_RESULTS_DIR:-${CVA6_REPO_DIR}/ci-results}"
RUN_LOG="${TIER_RESULTS_DIR}/run.log"
FAILURE_SUMMARY="${TIER_RESULTS_DIR}/failure_summary.log"
EXIT_CODE_FILE="${TIER_RESULTS_DIR}/exit_code"
ACT4_WRAPPER="${ACT4_WRAPPER:-${CVA6_REPO_DIR}/verif/regress/wrapper-cv32a65x-act.sh}"
ACT4_SUMMARY_FILE="${ACT4_SUMMARY_FILE:-${CVA6_REPO_DIR}/verif/sim/simulation_results/act4/certification_summary.txt}"
ACT4_EXPECTED_TESTS="${ACT4_EXPECTED_TESTS:-124}"
COPIED_SUMMARY="${TIER_RESULTS_DIR}/act4-certification-summary.txt"

mkdir -p "${TIER_RESULTS_DIR}"
: > "${RUN_LOG}"
: > "${FAILURE_SUMMARY}"
echo "1" > "${EXIT_CODE_FILE}"

append_failure() {
  echo "$*" | tee -a "${FAILURE_SUMMARY}" >&2
}

if ! [[ "${ACT4_EXPECTED_TESTS}" =~ ^[1-9][0-9]*$ ]]; then
  append_failure "ERROR: ACT4_EXPECTED_TESTS must be a positive integer, got ${ACT4_EXPECTED_TESTS}."
  exit 1
fi

cd "${CVA6_REPO_DIR}" || exit 1

set +e
bash "${ACT4_WRAPPER}" > >(tee -a "${RUN_LOG}") 2>&1
rc=$?
set -e

if [[ "${rc}" -ne 0 ]]; then
  append_failure "ERROR: ACT4 wrapper exited with status ${rc}."
fi

if [[ -f "${ACT4_SUMMARY_FILE}" ]]; then
  cp "${ACT4_SUMMARY_FILE}" "${COPIED_SUMMARY}"
  summary_line="$(tail -n 1 "${ACT4_SUMMARY_FILE}")"
  summary_line_count="$(grep -Ec '^TOTAL=[0-9]+ PASS=[0-9]+ FAIL=[0-9]+$' "${ACT4_SUMMARY_FILE}" || true)"

  if [[ "${summary_line_count}" -eq 1 ]] \
    && [[ "${summary_line}" =~ ^TOTAL=([0-9]+)[[:space:]]PASS=([0-9]+)[[:space:]]FAIL=([0-9]+)$ ]]; then
    total="${BASH_REMATCH[1]}"
    pass="${BASH_REMATCH[2]}"
    fail_count="${BASH_REMATCH[3]}"
    if [[ "${total}" -ne "${ACT4_EXPECTED_TESTS}" \
      || "${pass}" -ne "${total}" \
      || "${fail_count}" -ne 0 ]]; then
      append_failure "ERROR: ACT4 summary is not fully passing: ${summary_line}"
      [[ "${rc}" -ne 0 ]] || rc=1
    fi
  else
    append_failure "ERROR: ACT4 summary must end with exactly one valid TOTAL/PASS/FAIL line."
    [[ "${rc}" -ne 0 ]] || rc=1
  fi
else
  append_failure "ERROR: ACT4 wrapper produced no certification summary."
  [[ "${rc}" -ne 0 ]] || rc=1
fi

echo "${rc}" > "${EXIT_CODE_FILE}"
exit "${rc}"
