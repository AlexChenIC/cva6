<!-- Copyright 2026 OpenHW Foundation
SPDX-License-Identifier: Apache-2.0 -->

# Cook Stage 1 Reference

This branch is a learning reference, not a submitted PR or an upstream
acceptance decision.

## Frozen Inputs

- User PR #3480 checkpoint: `9255652fe53d44b6172f6c2bee5be35c624357c5`.
- Integrated upstream: `fb095566d6ce3a2a89d0a24d3c147863f058cfdb`.
- Historical reference consulted: `2b4365ab876703855ad846457dbebae79dca52fa`.
- The original PR branch and the historical reference are not updated.

## Scope

- AXI targets: `cv32a60x_axi`, `cv32a65x_sv32_axi`,
  `cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi`.
- Tier 1: five selected basic integer tests plus three selected integer
  tests per target. Selection is explicit; additions to upstream base lists
  do not silently expand this scope.
- RV32 preserves the original upstream p environment startup. RV64 uses an
  explicitly named `rv64ui-m-stage1-*` integer environment: original test
  bodies/assertions, no PMP/VM/F/D initialization or privilege transitions.
  Its header and adaptation provenance are uploaded. This is not original
  p environment coverage or a change to the hardware/model ISA.
- Manual Tier 2 pilot: the 60x lists plus div, rem and mulh.
- Live Spike is required, including on RV64. No automatic RV64/F/D disable,
  CSR warning downgrade, comparison masking, or additional core/RVFI RTL fix.
- No automatic nightly, dashboard deployment, OBI, full Thales regression
  equivalence, or full legacy `ci.yml` equivalence.

## Execution

Use the current README setup, including recursive submodules and
`cook.py git-dependencies`. The repository's dependency patches are part
of the upstream baseline; the CI records their hashes and submodule diffs.

Generate `compiler.yml` with `prepare_toolchains.py --tandem-enabled`.
This records requested intent, not proof that a comparison ran.

```sh
python3 .github/cook/run_stage1.py --scope probe --profile rv32-60x
python3 .github/cook/run_stage1.py --scope tier1 --profile rv32-60x
python3 .github/cook/run_stage1.py --scope tier1 --profile rv32-65x
python3 .github/cook/run_stage1.py --scope tier1 --profile rv64
python3 .github/cook/run_stage1.py --scope pilot --profile rv32-extra
```

The GitHub `cook-stage1.yml` workflow exposes these scopes. A probe is not
Tier 1 acceptance. Tier 1 always runs all three targets. The workflow has
no scheduled trigger; upstream candidate/main push and PR events use Tier 1.
Manual reference validation also enables `--check-reference-baseline`.
The no-extra-RTL condition is not a permanent ban on future processor PRs:
ordinary push/PR runs test the submitted RTL rather than requiring identity
to this frozen teaching baseline.

## Evidence And Failure Controls

Acceptance checks the public Cook compilation, single-run and testlist
recipes, their manifests/reports, normal successful tohost termination,
and the native `testharness.log.yaml`: SUCCESS, nonzero compared
instructions and zero mismatches. `spike-dasm` is not tandem checking.

The 60x Tier 1 job also runs intentional software-failure, timeout and
model/RTL instruction-divergence controls. These are infrastructure tests,
not Thales processor testcases. Their original failed logs/reports are
preserved under `ci-results/negative-controls`; successful rejection is
recorded separately. Unit tests cover missing native evidence and invalid
comparison results.

Artifacts include source/dependency identities, generated testlists and
configuration, commands, software ELFs, simulation logs, native comparison
reports and unified Cook reports. Build directories are not cached.

The GitHub `ci.yml` legacy flow remains scoped to old master. Its
candidate/main role is replaced only by this bounded Cook matrix; legacy
architecture-test coverage is not claimed.

Actual validation results and any startup/model limitations must be read
from the run's evidence and the accompanying handover, not inferred from
this scope document.

See `SPIKE_LIMITATIONS.md` for the preserved original RV64 failure and the
reason for the bounded software startup, rather than an RTL or model waiver.
