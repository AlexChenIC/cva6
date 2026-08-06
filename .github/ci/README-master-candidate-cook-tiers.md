# master_candidate cook.py Tier CI

This CI provides public GitHub-hosted validation for an initial RV32 AXI subset
of `master_candidate`. It reuses the target and testlist contract from the
Thales GitLab CI while running an open-source backend. Tier 1 is the known-green
fast baseline. Tier 2 runs the complete scoped testlist matrix and reports every
regression failure as a real failed check.

## Initial scope

| Tier | Target | Testlists | Enabled target/test pairs |
| --- | --- | --- | ---: |
| Tier 1 | `cv32a60x_axi` | `base_rv32_p` | 5 |
| Tier 1 | `cv32a65x_axi` | `base_rv32_p` | 5 |
| Tier 2 | `cv32a60x_axi` | `base_rv32_p` | 5 |
| Tier 2 | `cv32a65x_axi` | `base_rv32_p` | 5 |
| Tier 2 | `cv32a60x_axi` | `base_zcmt` | 4 |
| Tier 2 | `cv32a65x_axi` | `base_zcmt` | 4 |
| Tier 2 | `cv32a65x_axi` | `base_pmp` | 5 |

Tier 1 is the 10-test fast subset. Tier 2 is a strict superset and
contains all 23 enabled target/test pairs present in `.testlist_matrix_target`
for these two targets. Every executed regression uses the same result semantics:
a failing testcase makes its matrix job and workflow fail. `fail-fast: false`
keeps the other matrix jobs running, the recipe finishes the selected testlist,
and `if: always()` preserves summaries and artifacts after failure. Disabled
entries (`iterations: 0`) are not counted.

Merge policy is intentionally separate from test truth. Tier 1 is the candidate
for a repository required check. Tier 2 is intended as complete branch-update
evidence and should remain outside branch protection until its current target
and Spike contract failures are resolved. A red Tier 2 therefore reports the
real regression state without automatically blocking a pull request.

The versioned plan in `master_candidate_cook_tiers.yml` is the single source
for both workflow matrices. `cook-tier-plan.py` rejects duplicate entries,
unknown target/testlist pairs, incorrect AXI hierarchy, test-count drift,
Tier 1 entries missing from Tier 2, and Tier 2 testlist coverage below the
current Thales matrix for the scoped targets.

## Comparison boundary

The public and Thales flows share:

- `cook.py sw-compile-testlist` as the software build entry point;
- target names and files under `config/target/`;
- testlist names, source tests, and enabled iteration policy;
- Spike as the tandem reference model.

They do not use the same RTL backend or identical compiler binaries. The
public flow uses Verilator TestHarness; Thales uses VCS/UVM. GitHub-hosted
GCC 13.2 is used for base and PMP tests with a recorded Zcmt-free `-march`.
LLVM 18 and LLD are used for the Zcmt lists. Artifacts record these differences,
so a pass means comparable public coverage, not full binary or pipeline parity.

## Trigger policy

- Tier 1 runs for pull requests targeting `master_candidate` and by manual
  dispatch.
- Tier 2 runs after direct updates to `master_candidate` and by manual
  dispatch. Because Tier 2 contains the full Tier 1 baseline, the two workflows
  do not duplicate tool setup on the same branch update.

GitHub scheduled workflows execute from the repository default branch. A daily
`master_candidate` schedule therefore requires a later, separately reviewed
dispatcher on `master`; it is intentionally outside this first package.

## Local checks

With `PyYAML` installed:

```bash
python3 .github/scripts/cook-tier-plan.py validate
python3 .github/scripts/cook-tier-plan.py matrix --tier tier1
python3 .github/scripts/cook-tier-plan.py matrix --tier tier2
python3 .github/tests/test_master_candidate_cook_tier.py -v
```

The dynamic simulation jobs use
`flows/recipes/verilator_testharness_run_testlist.py`. This adapter consumes
ELFs produced by cook.py, passes the canonical target `spike.yaml` to both
public backends, enables Spike tandem, and writes downloadable reports.

## Extension rule

Add a target or testlist to the Thales matrix and canonical `config/target`
inputs first. Then extend `master_candidate_cook_tiers.yml`, update expected
counts, run the local checks, and prevalidate on a fork. Never remove, skip, or
convert a failing regression into a successful check merely to make the
workflow green. Track known target/reference-model failures in issues and the
CI report while preserving their real failed status and complete artifacts.
