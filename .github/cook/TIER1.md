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

## Supported first-stage scope

The machine-readable selection is `tier1.yml`. Generated lists and source hashes
are retained in `ci-results/testlists/`; shared Thales lists are not edited.

| Profile | Current target | Complete source testlist |
| --- | --- | --- |
| RV32 | `cv32a60x_axi` | `verif/tests/base_rv32_p.yaml`: add/lw/sw/beq/jal |
| RV64 | `cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi` | `verif/tests/base_rv64_p.yaml`: add/lw/sw/beq/jal |
| RTL-only smoke | `cv32a65x_axi` | original and UART Hello, independently and as a testlist |

The supported batch scope is ten invocations, plus one independent add run per
profile. These are the complete two Thales base lists, not an ISA compliance suite.
The materializer preserves sources, runtime, compiler options and iterations,
adds explicit ISA/ABI, and rejects unexpected list changes instead of dropping cases.

RV32 is the existing no-PMP/no-MMU AXI configuration; no RTL configuration is
modified to get a pass. RV64 retains the existing eight-entry PMP/MMU AXI target,
whose hardware and some live VM cases were already exercised. First-stage tests
use the Thales p-mode runtime, not the previous VM runtime: presence of MMU/PMP
hardware does not establish dedicated MMU/PMP coverage. Both targets/list mappings
exist in the baseline `.gitlab-ci.yml`. Historical dashboard OK/KO is only context,
not proof that this Verilator flow passes.

This scope is not four renamed equivalents of the historical RV64 targets:

| Historical target | First-stage disposition |
| --- | --- |
| `cv64a6_imafdc_sv39_hpdcache` | Absent target; no equivalent full-coverage claim |
| `cv64a6_imafdc_sv39_hpdcache_wb` | Incomplete target; WB variant deferred |
| `cv64a6_imafdc_sv39_wb` | Absent target; original WB coverage deferred |
| `cv64a6_imafdc_sv39` | Absent target; original cache coverage deferred |

Compiler ISA/ABI are explicit in `tier1.yml`; they are conservative subsets
of the target ISA, not full extension coverage (e.g. Zcmt/Zbkb are not claimed).
The existing p runtime, source pin and target linker are used. Private Thales
toolchains and VCS/UVM execution are not claimed to be identical.

## Preserved diagnostics, not accepted coverage

`workflow_dispatch` with `profile_set=diagnostic` retains the old RV32
`cv32a65x_axi` PMP failure and RV64 VM/Hello failures, including the original
309 nominal batch invocations and arch source installation. Failures still make
that workflow fail; it is explicitly named as diagnostic, not Tier 1 acceptance.
There is no continue-on-error or CSR filter. Source definitions, disabled entries
and the explicit RV64 duplicate `lb-align01-repeat2` are preserved.

At revision 4aa9455e1, run 37003390683 found RV32 PMPCFG0 mismatch and RV64
VM ld exit 32, VM sd timeout, and live Hello RD ADDR mismatch. RV64 VM add/beq/jal
passed. The new scope does not claim to fix these problems. Zcmt, dedicated PMP,
AMO, VM, arch and OBI coverage remain deferred; de-scoping requires maintainer
agreement before any old CI task can be retired.

## Live versus RTL-only

`--tandem-enabled` is explicit on Comp, Run and Testlist. It compiles the existing
Spike wrapper and RVFI scoreboard. As in the Cook VCS Run recipe, an existing
`config/target/<target>/spike.yaml` supplies the target model parameters. Run
copies it byte-for-byte to its output, records the source/SHA-256, and passes
`+config_file` to the native wrapper. Without a target file, configuration is
RTL-derived and that choice is recorded. ISA, privilege mode and TestHarness
boot address are still supplied by the native RTL wrapper.
The RV32 no-PMP target needs its existing YAML distinction between accessible
PMP CSRs and zero writable PMP regions; this is not a comparison mask or RTL edit.
Invalid target files fail instead of silently falling back. RTL-only ignores
Spike parameter files. Native negative checks use the same configuration policy.
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
with `.github/cook/constraints.txt`. Prepare pinned riscv-tests using the workflow
installation helper; riscv-arch-test is needed only in diagnostic mode.

```sh
export CONFIG_DIR="$PWD/ci-results/cook-config"
python3 .github/cook/prepare_toolchains.py --output-dir "$CONFIG_DIR" --tandem-enabled
python3 .github/cook/prepare_testlists.py --profile rv32
python3 cook.py verilator-testharness-comp -t cv32a60x_axi --tandem-enabled
python3 cook.py sw-compile-testlist -t cv32a60x_axi -c github_actions_gcc -l ci-results/testlists/rv32-basic.yaml
python3 cook.py verilator-testharness-run -t cv32a60x_axi -n rv32ui-p-add_0 --tandem-enabled
python3 cook.py testharness-run-testlist -s verilator -t cv32a60x_axi -l ci-results/testlists/rv32-basic.yaml --tandem-enabled
```

The CI controller `run_tier1.py --profile rv32` requires a fresh target
build directory and performs the complete positive and negative validation.
Run each profile in an independent checkout, as hosted jobs do.
Use `--diagnostic` only for the preserved diagnostic selection.
For same-SHA cold/warm validation, dispatch supported mode with `cold_tools=true`
(all three tool caches bypassed, including smoke), then false. Neither run caches
the DUT or software ELF. A green warm run does not replace cold verification.

## Evidence and expected errors

Three main artifacts contain RTL-only smoke, RV32 live, and RV64 live evidence.
Live artifact names end in `-supported` or `-diagnostic` to separate their scope.
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

The real CSR module readback test is also AI-added diagnostic coverage, not a
Thales ISA test. No-PMP configurations check zero readback; PMP configurations
check OFF/TOR/NAPOT/locking; FP configurations exercise immediate FS/SD readback.
The existing one-line SD next-state RTL fix remains a separately reviewable commit.

The acceptance job fails on failed, cancelled or skipped required jobs. This
candidate isolates its fork push from legacy `ci.yml` but does not retire upstream
CI or change repository required checks. The eventual master_candidate cutover
and rollback require a separate maintainer/Alex decision after candidate review.
