# Cook TestHarness Tier CI

The candidate workflow composes existing software compilation, atomic Verilator
hardware compilation, and the generic TestHarness testlist recipe. It does not
invoke cva6.py or the project Makefile. Verilator's generated C++ build still uses
GNU Make internally. Standalone Spike comparison is not UVM live tandem.

## Matrix and entry points

Tier 1 runs `base_rv32_p.yaml` on cv32a60x_axi and cv32a65x_axi for pull requests
targeting master_candidate, or on manual dispatch. Tier 2 runs the same rows plus
`base_pmp.yaml` on cv32a65x_axi. Tier 2 has no schedule on the non-default branch;
a separate default-branch dispatcher schedules it.

Manual dispatch accepts Verilator 5.050 (default) or 5.048. The optional Tier 2
`conformance` input adds individual recipe checks: RV32 no trace / VCD / FST,
ISS disabled/enabled, five PMP tests, and one RV64 compile-only configuration.
These checks are not an assertion of support for all configurations or ISA modes.

```bash
gh workflow run openhw-cva6-ci-tier1.yml --repo OWNER/cva6 --ref CANDIDATE_BRANCH
gh workflow run openhw-cva6-ci-tier2.yml --repo OWNER/cva6 --ref CANDIDATE_BRANCH \
  -f verilator_version=5.050 -f conformance=true
```

## Reproduction

Use Ubuntu 24.04, Python 3.11, a recursive checkout, GCC 13.2.0, the pinned
core-v-verif vendor Spike and Verilator. Set RISCV, SPIKE_INSTALL_DIR,
VERILATOR_INSTALL_DIR, CV_SW_PREFIX and NUM_JOBS. Install
`flows/requirements.txt` with `.github/requirements/cook-tier-ci-constraints.txt`.
The composite action documents the complete tool installation commands.

```bash
TIER_NAME='Tier 2' TIER_CONFIG=cv32a65x_axi TIER_TESTCASE=base-pmp \
TIER_TESTLIST=verif/tests/base_pmp.yaml \
TIER_COMPILER_MARCH=rv32imc_zicsr_zba_zbb_zbs_zbc_zifencei \
bash .github/scripts/run-tier-regression.sh
```

Use separate checkouts for concurrent jobs. Builds and simulations replace their
own target directories; they are not a multi-user shared build cache.

## Evidence contract

Each matrix job uploads a `tier1-rv32-<target>-<suite>` or `tier2-rv32-...` artifact.
`ci-results/evidence.json` uses schema version 1. It includes actual checked-out
source_revision, event head/base SHA, run id/attempt, simulator/reference model,
command argv/exit/timeout/log, environment versions/hashes, and the verified
testlist summary. A successful summary must match every expected compiled test,
target/options and consistent nonzero counts. Success cannot be inferred solely
from missing error lines, an old report, or a zero process exit.

For PRs the tested source can be GitHub's merge commit, not the PR head. Consumers
must preserve both values. An environment/setup failure may have no evidence JSON;
the GitHub job conclusion remains authoritative and must not be shown as PASS.
Logs/manifests and per-test results accompany the JSON. Artifacts expire after 14
days; a dashboard cannot assume old artifacts remain downloadable indefinitely.

All tools are confined to the disposable runner checkout; no private simulator
credentials or external company systems are used. Exact cache keys include the
Spike submodule commit; no fallback restore keys are used. The pinned Embecosm GCC
archive is downloaded over verified TLS. Its logged SHA256 is provenance, not an
independently published authenticity checksum.
