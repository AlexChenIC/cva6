# Cook Tier 1: live TestHarness candidate

This candidate extends the merged two-Hello smoke, using the existing atomic
Cook recipes. It is a first-stage RV32/RV64 CI, not full Thales regression,
all historical cache configurations, Tier 2, or offline ISS comparison.
Fork validation does not establish upstream PR-event or required-check setup.

## Invocation chain

`cook-tier1-live.yml` -> tool setup -> `prepare_toolchains.py` ->
`prepare_testlists.py` -> `sw-compile-testlist` /
`verilator-testharness-comp` -> `verilator-testharness-run` ->
`testharness-run-testlist` -> evidence checks -> artifacts -> acceptance job.

Only pinned test-source installation helpers are reused from the old flow.
The regression does not invoke `cva6.py`, old shell regression entry points,
an independent Spike run, or CSV trace comparison. `spike-dasm` remains optional
trace post-processing, not reference-model checking.

## Coverage migration

The machine-readable selection is `tier1.yml`. Generated lists and source hashes
are retained in `ci-results/testlists/`; shared legacy lists are not edited.

| Profile | Current target | Selected legacy cases |
| --- | --- | --- |
| RV32 | `cv32a65x_axi` | add/lw/sw/beq/jal + original Hello; 104 enabled arch entries |
| RV64 | `cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi` | VM add/ld/sd/beq/jal + original Hello; 193 enabled arch entries |
| RTL-only smoke | `cv32a65x_axi` | original and UART Hello, independently and as a testlist |

The nominal live batch selection is 309 invocations. RV64 arch has 192 distinct
test definitions: the source repeats `rv64i_m-lb-align01`. Both invocations are
retained; the second gets `-repeat2` so its ELF and results cannot overwrite the
first. Existing disabled entries remain disabled and do not count as passes.

RV32 uses the current M-mode, no-MMU, HPDCache-WT AXI target. RV64 uses the current
M/S/U, Sv39/MMU, eight-entry PMP, HPDCache-WT AXI target. This is a mapping with
differences, not four renamed equivalents of the historical RV64 targets:

| Historical target | First-stage disposition |
| --- | --- |
| `cv64a6_imafdc_sv39_hpdcache` | Absent target; mapped-with-differences to current WT/PMP/MMU target |
| `cv64a6_imafdc_sv39_hpdcache_wb` | Incomplete target; WB variant deferred |
| `cv64a6_imafdc_sv39_wb` | Absent target; original WB coverage deferred |
| `cv64a6_imafdc_sv39` | Absent target; original cache coverage deferred |

Compiler ISA/ABI are explicit in `tier1.yml`. They preserve the legacy test
families; they do not claim every extension implemented by the current target
(for example RV32 Zcmt or RV64 Zbkb) is tested. Original assembly and p/v runtimes
are reused, with the current target linker and GCC runtime library where needed.

## Live versus RTL-only

`--tandem-enabled` is explicit on Comp, Run and Testlist. It compiles the existing
Spike wrapper and RVFI scoreboard, using RTL-derived Spike configuration.
Live build/run directories have a `_tandem` suffix; manifests must match the
requested mode. No flag retains the existing RTL-only default and paths.
`--iss-enabled` is still rejected: it does not alias live checking.

Verilator 5.050's generated live comparator has large packed RVFI/CSR temporaries.
The live executable requests a 256 MiB soft stack limit before simulation and
fails clearly if the host's hard limit prevents this. RTL-only builds do not
change stack limits. This is host runtime capacity, not a comparison waiver.

A live PASS requires all of:
1. Normal simulator exit, no timeout, successful tohost marker, no failure marker.
2. A native `rvfi_compare` report with SUCCESS/exit 0, positive instruction
   comparison count, zero mismatches and no mismatch description.
3. Matching Run manifest, receipt, planned test order, counts and Cook report.

Missing/invalid reports, zero comparisons, failed disassembly when a trace exists,
and abnormal termination fail. Rejected rebuilds/reruns invalidate previous success
manifests/receipts. Software compilation and ELF post-processing check exit codes.

## Local reproduction on prepared Linux

Use recursive submodules, GCC, Verilator 5.050 and the pinned vendor Spike libraries.
Set `RISCV`, `SPIKE_INSTALL_DIR`, `VERILATOR_INSTALL_DIR`, `CV_SW_PREFIX`
and `NUM_JOBS` as in the reusable setup action. Install `flows/requirements.txt`
with `.github/cook/constraints.txt`. Prepare the pinned riscv-tests and
riscv-arch-test sources using the two installation helpers in the workflow.

```sh
export CONFIG_DIR="$PWD/ci-results/cook-config"
python3 .github/cook/prepare_toolchains.py --output-dir "$CONFIG_DIR" --tandem-enabled
python3 .github/cook/prepare_testlists.py --profile rv32
python3 cook.py verilator-testharness-comp -t cv32a65x_axi --tandem-enabled
python3 cook.py sw-compile-testlist -t cv32a65x_axi -c github_actions_gcc -l ci-results/testlists/rv32-basic.yaml
python3 cook.py verilator-testharness-run -t cv32a65x_axi -n rv32ui-p-add_0 --tandem-enabled
python3 cook.py testharness-run-testlist -s verilator -t cv32a65x_axi -l ci-results/testlists/rv32-basic.yaml --tandem-enabled
```

The CI controller `run_tier1.py --profile rv32 --suite full` requires a fresh target
build directory and performs the complete positive and negative validation.
Run each profile in an independent checkout, as hosted jobs do.

## Evidence and expected errors

Three main artifacts contain RTL-only smoke, RV32 live, and RV64 live evidence.
Native reports live beside per-test logs/results; `execution.yml` records process
exit/timeout; `simulation.command.json` records the actual simulator argv.
Software ELFs, compilation commands/manifests and generated lists are uploaded,
including available evidence when a job fails. DUT/software are never cached.

Python contract tests are orchestration tests, not ISA cases. Native negative
checks separately compile an infinite loop, reject an insufficient hard stack
limit, send SIGTERM to the simulator, enforce a Cook timeout, and load different
genuine test ELFs into RTL and Spike. Each must
fail simulation and pass its failure-detection assertion. Their expected errors
are confined to `ci-results/native-negative` and the `ci-loop` output, not waived
for any positive regression test.

The acceptance job fails on failed, cancelled or skipped required jobs. This
candidate isolates its fork push from legacy `ci.yml` but does not retire upstream
CI or change repository required checks. The eventual master_candidate cutover
and rollback require a separate maintainer/Alex decision after candidate review.
