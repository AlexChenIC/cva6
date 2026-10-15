<!-- Copyright 2026 OpenHW Foundation
SPDX-License-Identifier: Apache-2.0 -->

# Stage 1 Live Spike Boundaries

This reference uses upstream vendor Spike and target `spike.yaml` unchanged.
It adds no CSR comparison waiver and never automatically disables RV64 tandem.
Existing upstream WARL, override and injection parameters still apply; passing
integer tests is not complete CSR/PMP/MMU/F/D verification.

## Original RV64 Startup: Reproduced, Not Fixed

- Run: https://github.com/AlexChenIC/cva6/actions/runs/38677530207
- Source: `1095a311c45ea097c4ab5e7fba7303734f85d36a`.
- Upstream processor/target baseline: `fb095566`, no extra changes.
- Target: `cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi`.
- All eight software builds and the TestHarness build succeeded. The first
  independent `rv64ui-p-add_0` run failed strict comparison. The other seven
  tests were not executed, not seven additional observed failures.
- Native exit: SUCCESS / 0; 509 compared instructions, 12 CSR matches,
  one mismatch. Cook exited 1 and CI failed despite normal tohost termination.
- PC `0x800000a4`: `csrrw zero, pmpaddr0, t0` during environment startup.
- Log: CSR `0x3b0`, REF `0x1ffffffffffffe`, CORE `0x29ffffffffffffe`.
  The delta is `10 << 54`, consistent with `CONNECT_RVFI_FULL` concatenating
  the numeric padding width rather than zeros. This supports an RVFI
  observation issue; it is not evidence that every mismatch is a Spike bug.
- Artifact: `cook-stage1-tier1-rv64`, including native YAML, log, command,
  model snapshot, software ELF and failing Cook report.

## Bounded Alternative Approved For Stage 1

Only RV64 switches to `.github/cook/env/m/riscv_test.h`. Selected upstream
integer instruction bodies/assertions are unchanged; generated names are
`rv64ui-m-stage1-*`. The environment runs in M mode without PMP, VM, F/D
initialization or privilege transitions. `-mno-relax` avoids assuming a
global-pointer setup that this minimal assembly environment does not perform.
The materialized testlists record original names/options and the header hash.

RV32 retains its original upstream environment. The riscv-tests environment
name `p` is not a RISC-V privilege level named P. Original RV64 p startup,
broader privileged tests, floating point and architecture compliance remain
outside this bounded acceptance. Restoring them requires separate diagnosis
and owner-reviewed fixes; no processor/RVFI patch is included here.
