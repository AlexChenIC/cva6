# master_candidate cook.py Tier CI

This CI provides public GitHub-hosted validation for an initial RV32 AXI subset
of `master_candidate`. It reuses the target and testlist contract from the
Thales GitLab CI while running an open-source backend. The required baseline is
known green; extended lists remain visible diagnostics until their target and
Spike contracts are aligned.

## Initial scope

| Tier | Target | Testlists | Acceptance | Enabled target/test pairs |
| --- | --- | --- | --- | ---: |
| Tier 1 | `cv32a60x_axi` | `base_rv32_p` | required | 5 |
| Tier 1 | `cv32a65x_axi` | `base_rv32_p` | required | 5 |
| Tier 2 | `cv32a60x_axi` | `base_rv32_p` | required | 5 |
| Tier 2 | `cv32a65x_axi` | `base_rv32_p` | required | 5 |
| Tier 2 | `cv32a60x_axi` | `base_zcmt` | diagnostic | 4 |
| Tier 2 | `cv32a65x_axi` | `base_zcmt` | diagnostic | 4 |
| Tier 2 | `cv32a65x_axi` | `base_pmp` | diagnostic | 5 |

Tier 1 is the 10-test required fast subset. Tier 2 is a strict superset and
contains all 23 enabled target/test pairs present in `.testlist_matrix_target`
for these two targets. Its 10 baseline pairs are required; the remaining 13
extension/PMP pairs run as explicitly labelled diagnostics. A diagnostic job
still runs the complete testlist, records the real regression outcome in the
job summary, and uploads its logs. A known diagnostic regression failure does
not turn the job red, but missing or inconsistent evidence still does. Required
entries always block on failure. Disabled entries (`iterations: 0`) are not
counted.

The versioned plan in `master_candidate_cook_tiers.yml` is the single source
for both workflow matrices. `cook-tier-plan.py` rejects duplicate entries,
unknown target/testlist pairs, incorrect AXI hierarchy, test-count drift,
Tier 1 entries missing from Tier 2, and Tier 2 testlist coverage below the
current Thales matrix for the scoped targets. It also rejects an unlabelled
diagnostic entry or any difference between the Tier 1 and Tier 2 required sets.

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
counts, run the local checks, and prevalidate on a fork. A diagnostic label must
carry a concrete reason and retain complete failure evidence. Promote it to
required as soon as the canonical target/reference-model contract is aligned;
never remove or silently skip a failing test merely to make the workflow green.
