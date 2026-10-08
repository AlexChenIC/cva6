# Spike Live Tandem: Known Limits

This is a bounded Stage 1 candidate, not full Spike/Thales regression
acceptance. Core RTL, RVFI and target configuration files must remain
identical to the upstream revision recorded in stage1.yml.

## Strict Acceptance

Required profiles explicitly enable live tandem. Passing requires normal
execution, successful tohost termination, a valid native SUCCESS report,
nonzero compared instructions and zero mismatches. Missing reports,
timeouts, signals and injected instruction divergence are rejected.
There is no CSR warning downgrade, CSR masking, or RV64 auto-disable in
this TestHarness acceptance path.

## Software Scope

The instruction bodies and scalar assertions come from the pinned
riscv-tests sources. The required profiles substitute env/m/riscv_test.h
for the original p-mode startup. Tests remain in M-mode and do not
initialize PMP, VM, F/D state or transition privilege. Names contain
`m-stage1`; this is not unchanged p-mode, PMP/MMU or F/D coverage.
Narrow software march/ABI does not change the actual hardware/model ISA.

## Deferred Work

| Area | Evidence and limitation | Restoration requirement |
| --- | --- | --- |
| RV64 PMPADDR RVFI | Earlier candidate investigation found suspect width concatenation and PMP mode-bit observation in upstream cva6_rvfi. Expression-level reproductions and historical Thales logs support an observation issue, not a blanket Spike defect. | Separate owner-reviewed RVFI fix and strict original p-mode rerun. |
| mstatus.SD | Earlier directed csr_regfile testing showed FS Dirty / SD update inconsistency. This is RTL state logic, not necessarily a reference-model description error. | Separate RTL review and directed testing; no Stage 1 core patch. |
| Original p-mode startup | Shared startup writes PMPADDR/PMPCFG even for integer tests. Removing just a test body need not avoid the issue. | Keep strict diagnostic profiles; classify native PC/CSR differences before restoration. |
| Non-SV32 65x PMP WARL | Earlier cv32a65x_axi testing showed a NAPOT model/target mismatch. The required 65x SV32 target is not proof of a fix for this configuration. | Validate model WARL and target parameters against actual RTL with owners. |
| Zcmt / PMP lists | Historical public Thales evidence is not a current same-SHA acceptance result. Some Zcmt runs failed; identical root causes are unproven. | Obtain comparable logs/configuration before attempting model or design changes. |
| UVM RV64/F/D policy | Upstream Cook UVM compatibility policy may disable tandem or make its verdict nonblocking. | Do not use UVM green status as proof of active zero-mismatch checking. |

Exact run IDs, native mismatch evidence and independent artifact audits
will be recorded in the candidate's acceptance/handover report. A diagnostic
failure stays a failure and is not a mandatory-profile PASS.

If specific CSR differences are later waived, use a reviewed narrow rule,
retain original mismatches, and report waived and unwaived counts
separately. Missing reports or instruction divergence must never be waived.

## Deployment Limits

AXI only; no OBI, offline ISS, full legacy ci.yml equivalence, broad F/D/VM/
Hypervisor/PMP acceptance, automatic nightly, or deployed dashboard.
The manual Tier 2 pilot is finite. The per-job Cook HTML artifact is not
a deployed historical dashboard.
