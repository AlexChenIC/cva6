# Cook Verilator TestHarness Tier 1 (RTL-only)

This candidate integrates the Cook software compilation, TestHarness compilation,
single-test execution and testlist execution recipes with hosted GitHub Actions.
Reviewers need neither a local Verilator installation nor a commercial license.
The first acceptance boundary is deliberately small and explicit.

## Declared Matrix

The single source of matrix configuration is `config/cook-tier1.json`, relative
to this document. Both targets run `verif/tests/base_rv32_p.yaml`:

| Target | Tests | Additional acceptance |
| --- | --- | --- |
| `cv32a60x_axi` | add, lw, sw, beq, jal | None |
| `cv32a65x_axi` | add, lw, sw, beq, jal | Hello World, direct and testlist |

Each instruction test has one iteration. This is **10 configuration/test
combinations**, plus one additional Hello World ELF executed twice. It is not a
claim of full ISA coverage or coverage of every CVA6 configuration.
The expected compiled names are declared independently of the testlist, so an
accidental disabled or removed test fails the CI contract.

All jobs use RTL compilation, `notrace`, and disabled ISS comparison.
Spike/FESVR libraries and optional `spike-dasm` remain tool dependencies, but no
standalone ISS comparison or live tandem checking is performed. Tier 2, nightly,
dashboards, RV64, VCD/FST and broad architectural regressions are out of scope.

## Run on a Fork

Open Actions, choose **Cook Verilator TestHarness Tier 1 (RTL-only)**, select the
candidate branch and run the workflow. With GitHub CLI:

```bash
gh workflow run openhw-cva6-ci-tier1.yml --repo OWNER/cva6 --ref CANDIDATE_BRANCH
```

The registered workflow path is retained for dispatch before opening a PR.
The workflow also supports pull requests targeting `master_candidate` and pushes
to `master_candidate` after integration. A fork dispatch proves the candidate
commit's execution, not the upstream PR event, permissions or branch protection.

The job sequence is:

1. Recipe and CI contract tests, then export the declared matrix.
2. Prepare tools and save successful installations in exact-key caches.
3. Run both configurations independently with `fail-fast: false`.
4. Require all preceding jobs to succeed in the stable acceptance job.

Ubuntu 24.04, Python 3.11, GCC 13.2.0 and Verilator 5.050 are used.
Cook dependencies are constrained in `requirements/cook-tier-ci-constraints.txt`.
Spike is built from the checked-out core-v-verif vendor sources.
The repository's riscv-tests installer supplies revision
`f92842f91644092960ac7946a61ec2895e543cec` and the existing CVA6 patches.
The driver checks that revision, applied patches and initialized submodules.
Tool metadata includes versions and binary hashes; evidence also records the
patched test-source diff hash.

Only tools are cached, never test ELFs or TestHarness builds.
The setup job permits 90 minutes for cold installation. Each regression job
permits 45 minutes, with two compiler workers and at most two concurrent targets.
Individual simulation timeouts remain enforced by the Run recipe.
Fork/branch cache isolation can make a new branch's first run slower.

## Execution and Evidence

For each target, the driver calls `sw-compile-testlist`,
`verilator-testharness-comp`, then `testharness-run-testlist`.
On `cv32a65x_axi`, it additionally compiles the UART Hello World program, runs it
with `verilator-testharness-run`, then repeats it through the testlist recipe.
This reuses the same freshly compiled hardware within that target's job.
No `cva6.py`, root Makefile simulation wrapper or monolithic recipe is invoked.

PASS requires every command to succeed without timeout, the exact expected
passing cases and counts, matching Run manifests and receipts, actual successful
TestHarness termination in each log, and agreement between the Cook report and
YAML summary. Hello World additionally requires `0: Hello World !` in both logs.
The direct-run evidence is preserved before the testlist replaces its directory.
No test failure is marked advisory or hidden with `continue-on-error`.

Download `cook-tier1-rtl-<target>` for:

- `ci-results/tier1-evidence.json`: source/event SHAs, matrix row, commands,
  exit codes, timeouts, test inputs, tool identities and checked batch results.
- `ci-results/step-*.log`: source installation, tool configuration and Cook logs.
- `ci-results/hello-single/`: independent direct Hello World evidence, when run.
- `build/<target>/compile/`: fresh ELF and software compilation inputs/outputs.
- `build/<target>/simulation/`: per-test logs, receipts, manifests and reports.
- TestHarness compilation log, command, version and manifest.

Artifacts are retained for 14 days and uploaded even after regression failure.
Tool installation failures are visible in Actions setup logs. The contract-test
artifact is separate. A failed or skipped prerequisite makes the acceptance job
fail; it cannot turn an incomplete matrix green.

## Local Reproduction

Use a clean Linux checkout with recursive submodules and the tool environment
described in [the smoke guide](COOK_TESTHARNESS_SMOKE.md). Then:

```bash
python3 -m pip install -c .github/requirements/cook-tier-ci-constraints.txt -r flows/requirements.txt
TIER_TARGET=cv32a60x_axi bash .github/scripts/run-tier1-rtl.sh
TIER_TARGET=cv32a65x_axi bash .github/scripts/run-tier1-rtl.sh
```

Archive `ci-results/` between local target invocations; hosted jobs have separate
workspaces. The driver creates a dedicated Cook configuration there. The
riscv-tests installer only clones when absent; a wrong existing revision or
missing patch causes rejection, never an automatic reset of local changes.

Lightweight checks need no RTL toolchain:

```bash
python3 -m unittest discover -s .github/tests -p 'test_*.py' -v
actionlint .github/workflows/openhw-cva6-ci-tier1.yml
```

Mocks test failure propagation and result contracts; only the hosted regression
jobs establish actual RTL execution. The file-list test requires recursive
submodules and skips locally if they are absent.

## Integration Boundary

This is a self-contained initial RTL-only Tier 1 baseline, not a replacement for
reference-model validation. Keep unrelated existing workflows unchanged until
maintainers agree on retirement and required-check settings. No Tier 2 schedule
or upstream repository setting is changed by this candidate.
