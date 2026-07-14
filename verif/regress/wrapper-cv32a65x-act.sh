#!/usr/bin/env bash
# Copyright 2026 OpenHW Group
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

set -e
set -o pipefail

CVA6_REPO_DIR="${CVA6_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ACT4_PKG="${ACT4_PKG:-${CVA6_REPO_DIR}/external/act4}"
TARGET_RTL="${DV_TARGET:-cv32a65x}"
ACT4_EXPECTED_SHA="${ACT4_EXPECTED_SHA:-aec3ea396f254f37a7d0aba1179a7c7e2068a41a}"
ACT4_CONFIG_PATCH="${CVA6_REPO_DIR}/verif/regress/act4/cv32a65x-hpm.patch"
ACT4_EXPECTED_MANIFEST="${ACT4_EXPECTED_MANIFEST:-${CVA6_REPO_DIR}/verif/regress/act4/cv32a65x-aec3ea39-elf-manifest.txt}"
ACT4_CONFIG_FILE="${ACT4_PKG}/config/cores/cva6/cv32a65x/cv32a65x.yaml"
ACT4_TEST_CONFIG="config/cores/cva6/cv32a65x/test_config.yaml"
ACT4_ELF_ROOT="${ACT4_PKG}/work/cv32a65x/elfs"
RESULTS_DIR="${ACT4_RESULTS_DIR:-${CVA6_REPO_DIR}/verif/sim/simulation_results/act4}"
SUMMARY_FILE="${RESULTS_DIR}/certification_summary.txt"
SIMULATOR="${CVA6_REPO_DIR}/work-ver/Variane_testharness"
SPIKE_CONFIG="${CVA6_REPO_DIR}/config/gen_from_riscv_config/cv32a65x/spike/spike.yaml"
MAX_CYCLES="${ACT4_MAX_CYCLES:-10000000}"
ACT4_EXPECTED_TESTS="${ACT4_EXPECTED_TESTS:-124}"
ACT4_EXPECTED_GCC_VERSION="${ACT4_EXPECTED_GCC_VERSION:-15.2.0}"
ACT4_GCC_ALIAS_DIR="${ACT4_GCC_ALIAS_DIR:-${CVA6_REPO_DIR}/tools/act4-gcc/aliases}"
ACT4_SAIL_BIN_DIR="${ACT4_SAIL_BIN_DIR:-${CVA6_REPO_DIR}/tools/act4-sail/bin}"
ACT4_UDB_BIN_DIR="${ACT4_UDB_BIN_DIR:-${CVA6_REPO_DIR}/tools/act4-ruby-bin}"

detect_jobs() {
  if command -v nproc >/dev/null 2>&1; then
    nproc
  else
    sysctl -n hw.logicalcpu 2>/dev/null || echo 4
  fi
}

NUM_JOBS="${NUM_JOBS:-$(detect_jobs)}"
ACT4_CONFIG_BACKUP=""

restore_act4_config() {
  if [[ -n "${ACT4_CONFIG_BACKUP}" && -f "${ACT4_CONFIG_BACKUP}" ]]; then
    cp "${ACT4_CONFIG_BACKUP}" "${ACT4_CONFIG_FILE}"
    rm -f "${ACT4_CONFIG_BACKUP}"
  fi
}
trap restore_act4_config EXIT

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

report_is_passing() {
  ruby -ryaml -e '
    content = File.read(ARGV.fetch(0))
    document = Psych.parse(content)
    mapping = document&.root
    raise "report must be a YAML mapping" unless mapping.is_a?(Psych::Nodes::Mapping)

    keys = mapping.children.each_slice(2).map do |key_node, _value_node|
      raise "report keys must be scalars" unless key_node.is_a?(Psych::Nodes::Scalar)
      key_node.value
    end
    required = %w[exit_cause exit_code instr_count mismatches_count]
    required.each do |key|
      raise "missing or duplicate #{key}" unless keys.count(key) == 1
    end

    data = YAML.safe_load(
      content,
      permitted_classes: [],
      permitted_symbols: [],
      aliases: false
    )
    raise "report must be a mapping" unless data.is_a?(Hash)

    as_integer = lambda do |value|
      value.is_a?(Integer) ? value : Integer(value, 0)
    end
    raise "unexpected exit_cause" unless data.fetch("exit_cause") == "SUCCESS"
    raise "nonzero exit_code" unless as_integer.call(data.fetch("exit_code")) == 0
    raise "zero instr_count" unless as_integer.call(data.fetch("instr_count")).positive?
    raise "nonzero mismatches_count" unless as_integer.call(data.fetch("mismatches_count")) == 0
  ' "$1" >/dev/null 2>&1
}

[[ "${TARGET_RTL}" == "cv32a65x" ]] || fail "ACT4 integration only supports cv32a65x, got ${TARGET_RTL}"
[[ -n "${RISCV:-}" ]] || fail "RISCV must point to the CVA6 RISC-V toolchain"
[[ -d "${ACT4_PKG}/.git" || -f "${ACT4_PKG}/.git" ]] || fail "ACT4 submodule is not initialized"
[[ -f "${ACT4_CONFIG_PATCH}" ]] || fail "missing ACT4 config patch: ${ACT4_CONFIG_PATCH}"
[[ -f "${ACT4_EXPECTED_MANIFEST}" ]] || fail "missing ACT4 ELF manifest: ${ACT4_EXPECTED_MANIFEST}"
[[ -f "${SPIKE_CONFIG}" ]] || fail "missing Spike config: ${SPIKE_CONFIG}"
[[ "${ACT4_EXPECTED_TESTS}" =~ ^[1-9][0-9]*$ ]] || fail \
  "ACT4_EXPECTED_TESTS must be a positive integer, got ${ACT4_EXPECTED_TESTS}"

actual_act4_sha="$(git -C "${ACT4_PKG}" rev-parse HEAD)"
[[ "${actual_act4_sha}" == "${ACT4_EXPECTED_SHA}" ]] || fail \
  "ACT4 pin mismatch: expected ${ACT4_EXPECTED_SHA}, got ${actual_act4_sha}"
act4_status=()
while IFS= read -r -d '' status_entry; do
  case "${status_entry}" in
    "?? framework/src/act/data/vendor/bundle/"*) ;;
    *) act4_status+=("${status_entry}") ;;
  esac
done < <(git -C "${ACT4_PKG}" status --porcelain -z --untracked-files=all --ignore-submodules=none)
if [[ "${#act4_status[@]}" -ne 0 ]]; then
  printf '%s\n' "${act4_status[@]}" >&2
  fail "ACT4 submodule contains changes outside the locked Bundler install directory"
fi

if git -C "${ACT4_PKG}" apply --check "${ACT4_CONFIG_PATCH}"; then
  ACT4_CONFIG_BACKUP="$(mktemp)"
  cp "${ACT4_CONFIG_FILE}" "${ACT4_CONFIG_BACKUP}"
  git -C "${ACT4_PKG}" apply "${ACT4_CONFIG_PATCH}"
elif git -C "${ACT4_PKG}" apply --reverse --check "${ACT4_CONFIG_PATCH}"; then
  echo "ACT4 CV32A65x HPM configuration is already corrected"
else
  fail "ACT4 CV32A65x HPM patch does not apply cleanly"
fi

export CVA6_REPO_DIR ACT4_PKG
export DV_SIMULATORS="${DV_SIMULATORS:-veri-testharness,spike}"
export SPIKE_TANDEM="${SPIKE_TANDEM:-1}"

# Keep the developer entry point usable outside GitHub Actions.
# shellcheck source=/dev/null
source "${CVA6_REPO_DIR}/verif/sim/setup-env.sh"
if [[ "${DV_SIMULATORS}" == *"veri-testharness"* ]]; then
  # shellcheck source=/dev/null
  source "${CVA6_REPO_DIR}/verif/regress/install-verilator.sh"
fi
# shellcheck source=/dev/null
source "${CVA6_REPO_DIR}/verif/regress/install-spike.sh"

# setup-env.sh prepends the generic CVA6 GCC. Restore the ACT4-pinned tools.
if [[ -d "${ACT4_GCC_ALIAS_DIR}" ]]; then
  PATH="${ACT4_GCC_ALIAS_DIR}:${PATH}"
fi
if [[ -d "${ACT4_SAIL_BIN_DIR}" ]]; then
  PATH="${ACT4_SAIL_BIN_DIR}:${PATH}"
fi
if [[ -d "${ACT4_UDB_BIN_DIR}" ]]; then
  PATH="${ACT4_UDB_BIN_DIR}:${PATH}"
fi
export PATH

for command_name in git make ruby uv bundle udb riscv64-unknown-elf-gcc riscv64-unknown-elf-nm sail_riscv_sim; do
  command -v "${command_name}" >/dev/null 2>&1 || fail "required command not found: ${command_name}"
done

actual_gcc_version="$(riscv64-unknown-elf-gcc -dumpfullversion)"
[[ "${actual_gcc_version}" == "${ACT4_EXPECTED_GCC_VERSION}" ]] || fail \
  "ACT4 requires GCC ${ACT4_EXPECTED_GCC_VERSION}, got ${actual_gcc_version} from $(command -v riscv64-unknown-elf-gcc)"

echo "ACT4 pin: ${actual_act4_sha}"
echo "Generating ACT4 tests for ${TARGET_RTL} with ${NUM_JOBS} jobs"
make -C "${ACT4_PKG}" clean
make -C "${ACT4_PKG}" \
  CONFIG_FILES="${ACT4_TEST_CONFIG}" \
  EXTENSIONS="" \
  EXCLUDE_EXTENSIONS="InterruptsSm,Sm" \
  --jobs "${NUM_JOBS}"

[[ -d "${ACT4_ELF_ROOT}" ]] || fail "ACT4 generated no ELF directory: ${ACT4_ELF_ROOT}"
rm -rf "${RESULTS_DIR}"
mkdir -p "${RESULTS_DIR}"
GENERATED_MANIFEST="${RESULTS_DIR}/generated-elf-manifest.txt"
(
  cd "${ACT4_ELF_ROOT}"
  find -L . \( -type f -o -type l \) \( -iname '*.elf' -o -iname '*.elf32' \) -print \
    | sed 's#^\./##' \
    | LC_ALL=C sort
) > "${GENERATED_MANIFEST}"

expected_manifest_count="$(wc -l < "${ACT4_EXPECTED_MANIFEST}" | tr -d '[:space:]')"
[[ "${expected_manifest_count}" -eq "${ACT4_EXPECTED_TESTS}" ]] || fail \
  "ACT4 expected manifest contains ${expected_manifest_count} tests, expected ${ACT4_EXPECTED_TESTS}"
if ! diff -u "${ACT4_EXPECTED_MANIFEST}" "${GENERATED_MANIFEST}" > "${RESULTS_DIR}/elf-manifest.diff"; then
  cat "${RESULTS_DIR}/elf-manifest.diff" >&2
  fail "ACT4 generated ELF set does not match the pinned manifest"
fi
rm -f "${RESULTS_DIR}/elf-manifest.diff"

echo "Building CVA6 Verilator model for ${TARGET_RTL}"
make -C "${CVA6_REPO_DIR}" verilate target="${TARGET_RTL}" -j"${NUM_JOBS}"

[[ -x "${SIMULATOR}" ]] || fail "Verilator simulator was not built: ${SIMULATOR}"

mkdir -p "${RESULTS_DIR}"
printf "RESULT  TEST\n------  ----\n" > "${SUMMARY_FILE}"

total=0
pass=0
fail_count=0
first_fail_log=""

while IFS= read -r -d '' elf; do
  total=$((total + 1))
  relative_path="${elf#"${ACT4_ELF_ROOT}"/}"
  log_file="${RESULTS_DIR}/${relative_path%.*}.log"
  report_file="${log_file}.yaml"
  mkdir -p "$(dirname "${log_file}")"

  tohost_addr="$(riscv64-unknown-elf-nm -B "${elf}" | awk '$3 == "tohost" {print $1; exit}')"
  if [[ -z "${tohost_addr}" ]]; then
    echo "Missing tohost symbol: ${relative_path}" > "${log_file}"
    sim_rc=2
  else
    set +e
    "${SIMULATOR}" \
      "${elf}" \
      "+max-cycles=${MAX_CYCLES}" \
      +debug_disable=1 \
      +UVM_VERBOSITY=UVM_NONE \
      "++${elf}" \
      "+elf_file=${elf}" \
      "+core_name=${TARGET_RTL}" \
      "+config_file=${SPIKE_CONFIG}" \
      "+tohost_addr=0x${tohost_addr}" \
      "+signature=${elf}.signature_output" \
      +UVM_TESTNAME=uvmt_cva6_firmware_test_c \
      "+report_file=${report_file}" \
      > "${log_file}" 2>&1
    sim_rc=$?
    set -e
  fi

  # The standalone harness can finish through rvfi_tracer before Spike emits a
  # report. Validate a report when present, but bind the required verdicts to
  # the current ELF and ACT4 source name below.
  report_ok=1
  report_state="absent"
  if [[ -e "${report_file}" ]]; then
    report_state="invalid"
    report_ok=0
    if [[ -f "${report_file}" ]] && report_is_passing "${report_file}"; then
      report_state="passing"
      report_ok=1
    fi
  fi

  expected_test_file="$(basename "${elf%.*}").S"
  expected_rvcp_line="RVCP-SUMMARY: TEST PASSED - Test File \"${expected_test_file}\""
  tohost_success_count="$(awk -v prefix="${elf} *** SUCCESS *** (tohost = 0) after " \
    'index($0, prefix) == 1 && $0 ~ /[0-9]+ cycles$/ { count++ } END { print count + 0 }' \
    "${log_file}")"
  any_tohost_success_count="$(grep -Ec ' \*\*\* SUCCESS \*\*\* \(tohost = 0\) after [0-9]+ cycles$' \
    "${log_file}" || true)"
  tohost_fail_count="$(grep -Ec ' \*\*\* FAILED \*\*\* \(tohost = ' "${log_file}" || true)"
  rvcp_pass_count="$(grep -Fxc -- "${expected_rvcp_line}" "${log_file}" || true)"
  any_rvcp_pass_count="$(grep -Ec '^RVCP-SUMMARY: TEST PASSED - Test File "[^"]+"$' \
    "${log_file}" || true)"
  rvcp_fail_count="$(grep -Ec '^RVCP-SUMMARY: TEST (FAILED|SIGRUN) - Test File "[^"]+"$' \
    "${log_file}" || true)"
  termination_count="$(grep -Ec '^\*\*\* \[rvfi_tracer\] INFO: Simulation terminated after[[:space:]]+[0-9]+ cycles!$' \
    "${log_file}" || true)"
  simulation_fail_count="$(grep -Ec '^[[:space:]]*SIMULATION FAILED' "${log_file}" || true)"
  tandem_error_count="$(grep -Eic 'UVM_(ERROR|FATAL)([[:space:]]|@)|spike_tandem.*Mismatch' \
    "${log_file}" || true)"

  verdict_file="${log_file}.verdict"
  {
    printf 'sim_rc=%s\n' "${sim_rc}"
    printf 'expected_tohost_success=%s\n' "${tohost_success_count}"
    printf 'all_tohost_success=%s\n' "${any_tohost_success_count}"
    printf 'tohost_failure=%s\n' "${tohost_fail_count}"
    printf 'expected_rvcp_pass=%s\n' "${rvcp_pass_count}"
    printf 'all_rvcp_pass=%s\n' "${any_rvcp_pass_count}"
    printf 'rvcp_failure=%s\n' "${rvcp_fail_count}"
    printf 'normal_termination=%s\n' "${termination_count}"
    printf 'simulation_failure=%s\n' "${simulation_fail_count}"
    printf 'tandem_error=%s\n' "${tandem_error_count}"
    printf 'tandem_report=%s\n' "${report_state}"
  } > "${verdict_file}"

  if [[ "${sim_rc}" -eq 0 ]] \
    && [[ "${tohost_success_count}" -eq 1 ]] \
    && [[ "${any_tohost_success_count}" -eq 1 ]] \
    && [[ "${tohost_fail_count}" -eq 0 ]] \
    && [[ "${rvcp_pass_count}" -eq 1 ]] \
    && [[ "${any_rvcp_pass_count}" -eq 1 ]] \
    && [[ "${rvcp_fail_count}" -eq 0 ]] \
    && [[ "${termination_count}" -eq 1 ]] \
    && [[ "${simulation_fail_count}" -eq 0 ]] \
    && [[ "${tandem_error_count}" -eq 0 ]] \
    && [[ "${report_ok}" -eq 1 ]]; then
    printf "PASS    %s\n" "${relative_path}" | tee -a "${SUMMARY_FILE}"
    pass=$((pass + 1))
  else
    printf "FAIL    %s\n" "${relative_path}" | tee -a "${SUMMARY_FILE}"
    fail_count=$((fail_count + 1))
    if [[ -z "${first_fail_log}" ]]; then
      first_fail_log="${log_file}"
    fi
  fi
done < <(find -L "${ACT4_ELF_ROOT}" \( -type f -o -type l \) \( -iname '*.elf' -o -iname '*.elf32' \) -print0)

printf "\nTOTAL=%d PASS=%d FAIL=%d\n" "${total}" "${pass}" "${fail_count}" | tee -a "${SUMMARY_FILE}"
echo "Summary saved to: ${SUMMARY_FILE}"

[[ "${total}" -gt 0 ]] || fail "ACT4 generated zero runnable ELFs"
if [[ "${total}" -ne "${ACT4_EXPECTED_TESTS}" \
  || "${fail_count}" -ne 0 \
  || "${pass}" -ne "${total}" ]]; then
  if [[ -n "${first_fail_log}" ]]; then
    echo "First failing ACT4 log: ${first_fail_log}" >&2
    cat "${first_fail_log}.verdict" >&2
    tail -n 120 "${first_fail_log}" >&2
  fi
  exit 1
fi
