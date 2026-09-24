# Cook-native RTL-only Tier CI

These workflows compose the Verilator TestHarness compilation recipe, existing
Cook software compilation, and the TestHarness testlist runner. The testlist
calls the single-test Run recipe directly. CI does not delegate simulation to
`cva6.py` or the legacy CVA6 Makefile. Verilator's generated C++ build still uses
GNU Make internally.

## Initial scope

| Tier | Cook target | Testlist | Enabled cases per row |
| --- | --- | --- | --- |
| 1 and 2 | `cv32a60x_axi` | `verif/tests/base_rv32_p.yaml` | 5 |
| 1 and 2 | `cv32a65x_axi` | `verif/tests/base_rv32_p.yaml` | 5 |
| 2 | `cv32a65x_axi` | `verif/tests/base_pmp.yaml` | 5 |

The base list contains `rv32ui-p-add`, `lw`, `sw`, `beq` and `jal`: arithmetic,
load/store and control-flow smoke tests, not full RV32 instruction coverage.
The enabled PMP tests are `decreasing_entries_test`, `exact_csrr_test`,
`granularity_test`, `locked_outside_tor_test` and `lsu_tor_test`. Disabled entries
stay disabled. Their PASS results do not establish complete PMP coverage.

Both targets have `hier: axi`, XLEN=32 and no MMU. The current target packages
configure zero PMP entries for cv32a60x_axi and eight for cv32a65x_axi, so PMP
tests only run on the latter. OBI targets with similar names are not substitutes.
These are core/TestHarness regressions, not DCLS system integration tests.

Tier 1 contains 10 test executions across two jobs. Tier 2 contains 15 across
three jobs, including the Tier 1 rows. They deliberately share the baseline;
these are not 25 distinct tests when both workflows run.

Tier 1 supports pull requests to `master_candidate` and manual dispatch.
Tier 2 is manual-only in this contribution. Default-branch nightly dispatch,
dashboard integration, RV64, additional backends, live tandem, standalone ISS,
coverage/gate modes and expanded waveform conformance are separate work.

## What PASS means

This is **RTL-only, without reference-model comparison**. Each test must satisfy
the Run recipe's process exit, timeout, explicit tohost success and failure-marker
checks. A missing raw trace skips disassembly; when present, trace post-processing
must succeed. Neither a fixed PC nor trace-content matching is a success gate.
See `flows/README.md` for the exact Run contract.

Spike/FESVR libraries and the `spike-dasm` utility remain build/post-processing
dependencies. Installing those tools does not enable ISS or live tandem. Commands
explicitly pass `--no-iss-enabled`; reports record `iss_enabled: false` and
`reference_model: null`. This is not equivalent to prior tandem-based CI.

## Environment and execution

The initial CI profile is Ubuntu 24.04, Python 3.11, Verilator 5.050 and the
public Embecosm GCC 13.2.0 RV32 toolchain, plus the pinned core-v-verif vendor
Spike. A recursive checkout and installed riscv-tests sources are required for
the base list. The composite action records tool versions and uses exact caches.
Its dependencies stay inside the disposable runner and require no company login.
The downloaded GCC archive's printed SHA256 records provenance; it is not a
checksum comparison with an independently authenticated release manifest.

The target ISA configuration contains extensions not available in this compiler
profile, including Zcmt. The explicit per-row `march` is a compatible software
build subset, not a modification of the RTL configuration or an ISA coverage claim.

Lightweight tests run before tool installation. At most two matrix jobs run in
parallel; `NUM_JOBS=2` bounds compilation parallelism. Setup and regression jobs
have 60-minute limits, checks have 10 minutes, and matrix failures do not cancel
unrelated rows. Each runner has its own checkout/build directory.

Manual dispatch, after the workflows are registered in the destination repo:

```bash
gh workflow run openhw-cva6-ci-tier1.yml --repo OWNER/cva6 --ref CANDIDATE_BRANCH
gh workflow run openhw-cva6-ci-tier2.yml --repo OWNER/cva6 --ref CANDIDATE_BRANCH
```

Linux reproduction after provisioning the documented tools and Cook dependencies:

```bash
# Run from the repository root, using the configured Cook Python environment.
export RISCV=/path/to/riscv-toolchain
export CV_SW_PREFIX=riscv32-unknown-elf-
export SPIKE_INSTALL_DIR=/path/to/vendor-spike
export VERILATOR_INSTALL_DIR=/path/to/verilator-5.050
export NUM_JOBS=2
export COOK_CONFIG_DIR="$PWD/ci-config"
TIER_NAME='Tier 1' TIER_CONFIG=cv32a60x_axi TIER_TESTCASE=base-rv32-p \
TIER_TESTLIST=verif/tests/base_rv32_p.yaml TIER_INSTALL_SCRIPT=install-riscv-tests \
TIER_COMPILER_MARCH=rv32imc_zicsr_zba_zbb_zbs_zbc \
bash .github/scripts/run-tier-regression.sh
```

The wrapper prepares test sources and compiler.yml; Cook owns software build,
hardware build and test execution. Do not share mutable build/output/config
directories between simultaneous local users or jobs.

## Reports and future extensions

Each regression uploads `ci-results/`, simulation results, and compilation
logs/manifests even on failure. `evidence.json` contains the actual checkout SHA,
PR head/base when available, tool metadata, commands/exit codes and checked
testlist results. GitHub may test a PR merge commit rather than the head SHA;
both identities must remain distinguishable. Missing evidence on setup failure
is not a PASS. Artifact retention is 14 days.

The summary must match the selected target, testlist, RTL/no-ISS options and
every expected iteration. Counts must be consistent and nonzero, all cases
must pass, and each compilation/run step must return successfully. Old results
or zero exit alone cannot replace those checks.

To add a target or suite, first validate the standalone Cook commands and the
required hardware features. Add a matrix `include` row with `config`, `testcase`,
`testlist`, `install_script` and `march`. A Tier 1 row must also appear unchanged
in Tier 2. Existing suites do not need changes to recipes or the CI driver.
Use the existing YAML `iterations` convention. Extra source installers must be
explicitly added to the wrapper's allowlist; do not execute arbitrary YAML text.
RV64 requires a suitable toolchain/ABI profile and validation, not just an extra
row in the current RV32 matrix. Run the matrix/CI tests after changing rows:

```bash
python .github/tests/test_cook_tier_matrix.py -v
python .github/tests/test_cook_tier.py -v
```

The initial matrix is defined in the two workflow YAML files so reviewers can
read it directly. No dynamic matrix generator, new recipe framework or dashboard
dependency is introduced for this first version.
