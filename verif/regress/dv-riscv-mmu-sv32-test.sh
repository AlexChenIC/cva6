# Copyright 2021 Thales DIS design services SAS
#
# Licensed under the Solderpad Hardware Licence, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# SPDX-License-Identifier: Apache-2.0 WITH SHL-2.0
# You may obtain a copy of the License at https://solderpad.org/licenses/
#
# Original Author: Jean-Roch COULON - Thales

# where are the tools
if ! [ -n "$RISCV" ]; then
  echo "Error: RISCV variable undefined"
  return
fi

# install the required tools
source ./verif/regress/install-verilator.sh
source ./verif/regress/install-spike.sh
source verif/regress/install-riscv-arch-test.sh

source ./verif/sim/setup-env.sh

if ! [ -n "$DV_TARGET" ]; then
  DV_TARGET=cv32a6_imac_sv32
fi

if ! [ -n "$DV_SIMULATORS" ]; then
  DV_SIMULATORS=veri-testharness,spike
fi

pmp_tests=(
  rv32_vm_pmp_check_level_0_s
  rv32_vm_pmp_check_level_0_u
  rv32_vm_pmp_check_level_1_s
  rv32_vm_pmp_check_level_1_u
  rv32_vm_pte_pmp_check_level_1_u
  rv32_vm_pte_pmp_check_level_1_s
  rv32_vm_pte_pmp_check_level_0_u
  rv32_vm_pte_pmp_check_level_0_s
)

errors=0
for test_name in "${pmp_tests[@]}"; do
  echo "::group::PMP diagnostic: ${test_name}"
  cd verif/sim
  python3 cva6.py --testlist=../tests/testlist_riscv-mmu-sv32-arch-test-$DV_TARGET.yaml --test "$test_name" --target "$DV_TARGET" --iss_yaml=cva6.yaml --iss="$DV_SIMULATORS" $DV_OPTS --linker=../tests/riscv-arch-test/riscv-target/spike/link.ld
  status=$?
  cd -
  if ((status != 0)); then
    errors=$((errors + 1))
  fi
  echo "::endgroup::"
done

echo "PMP diagnostic summary: ${errors} failure(s) across ${#pmp_tests[@]} tests"
exit "$errors"
