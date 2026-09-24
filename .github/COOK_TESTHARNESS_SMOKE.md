# Cook Verilator TestHarness Smoke

This self-contained first stage composes three atomic recipes:
`verilator-testharness-comp`, `verilator-testharness-run`, and
`testharness-run-testlist --simulator verilator`. It does not invoke
`cva6.py` or the legacy monolithic TestHarness recipe.

## Scope

- One target: `cv32a65x_axi`.
- One small program: `verif/tests/custom/hello_world/testharness_hello_world.c`.
  It prints through the existing TestHarness mock UART, then returns through
  the existing startup/exit code. The original HTIF-based Hello World is unchanged.
- One compiled ELF: `hello-world_0`, executed once directly and once through
  a single-entry testlist.
- RTL-only, `notrace`, ISS disabled. No Spike comparison or live tandem.
- Spike/FESVR libraries and optional `spike-dasm` trace post-processing remain
  dependencies; they do not imply reference-model checking.
- The GCC-compatible ISA subset is explicit in the testlist. This does not
  validate Zcmt, other targets, VCD/FST, Tier 2, or full CI replacement.

## Hosted Verification

The workflow `Cook Verilator TestHarness smoke` prepares its own Linux tools.
Reviewers do not need Verilator on their machines. Open the run for the exact
candidate commit, inspect the job summary, and download
`cook-testharness-smoke-cv32a65x_axi`.

The registered workflow path remains
`.github/workflows/openhw-cva6-ci-tier1.yml` for manual dispatch on a fork.
Its content is now a single smoke job, not the previous Tier matrix.
It can also run on pull requests targeting `master_candidate`.
The old Tier 2 workflow from the integration branch is intentionally absent
from this first-stage candidate. Unrelated upstream workflows are unchanged.

The job uses Ubuntu 24.04, Python 3.11, GCC 13.2.0 and Verilator 5.050.
Cook Python dependencies are constrained in
`.github/requirements/cook-tier-ci-constraints.txt`; Spike comes from the
checked-out core-v-verif vendor tree. The setup action installs tools on cache
misses. Tool caches do not contain compiled test ELFs or TestHarness binaries.
The job is limited to two build workers and 90 minutes.

## Local Reproduction

Use a clean Linux checkout with recursive submodules. Prepare the same tool
versions using the setup action as a reference, or provide compatible existing
installations. No commercial simulator or license is needed.

Set `RISCV` to the RISC-V GCC installation, `CV_SW_PREFIX` to
`riscv32-unknown-elf-`, `SPIKE_INSTALL_DIR` to the vendor Spike installation,
and `VERILATOR_INSTALL_DIR` to the Verilator installation.
Add the tool binaries to `PATH` and the Spike/RISC-V libraries to
`LD_LIBRARY_PATH`. Use a Python virtual environment with:

```bash
python3 -m pip install -c .github/requirements/cook-tier-ci-constraints.txt -r flows/requirements.txt
bash .github/scripts/run-testharness-smoke.sh
```

The wrapper generates a Cook compiler configuration under
`ci-results/cook-config`, without editing personal files in `flows/config`.
The driver executes these separate steps:

```bash
export CONFIG_DIR="$PWD/ci-results/cook-config"
python3 cook.py sw-compile-testlist -t cv32a65x_axi -c github_actions_gcc -l verif/tests/testlist_verilator_testharness_smoke.yaml
python3 cook.py verilator-testharness-comp -t cv32a65x_axi --trace-mode notrace
python3 cook.py verilator-testharness-run -t cv32a65x_axi -n hello-world_0 --trace-mode notrace --no-iss-enabled
python3 cook.py testharness-run-testlist --simulator verilator -t cv32a65x_axi -l verif/tests/testlist_verilator_testharness_smoke.yaml --trace-mode notrace --no-iss-enabled
```

The same `sw-compile-testlist` and `sw-compile` implementations used by other
Cook flows produce the software. No new compiler implementation is introduced.
Each run recipe replaces its own output directory, so the driver preserves the
direct-run evidence before invoking the testlist.

## Acceptance and Evidence

A successful command exit is necessary but not sufficient. The driver also
requires a successful TestHarness termination, the expected
`0: Hello World !` output, matching per-test metadata, exactly one passing
batch case, and agreement between the Cook report and YAML summary.
The run receipt records the outcome; the run manifest records compilation
and trace modes. Both are checked against their recipe-defined contracts.
Timeouts, missing prerequisites, simulation failures, failed trace
post-processing, missing output or inconsistent reports fail the job.

The artifact contains:

- `ci-results/evidence.json`: source SHA, workflow event SHAs, tool versions
  and binary hashes, command arguments, exit codes, timeouts and results.
- `ci-results/step-*.log`: logs for the four Cook commands.
- `ci-results/single-test/`: the direct-run log, receipt and manifest.
- `ci-results/testlist-report.yml` and `testlist-summary.yml`: batch results.
- `build/cv32a65x_axi/compile/hello-world_0/`: the compiled software.
- `build/cv32a65x_axi/simulation/`: the batch-run logs and receipts.
- TestHarness compilation logs, command, version and manifest.

Source metadata and available outputs are uploaded even on job failure.
Tool installation failures are also visible in the Actions step logs.
A PASS proves this smoke flow only; it does not establish ISA equivalence,
full regression coverage or permission to retire existing reference checks.

## Lightweight Regression Tests

Run the five test files individually, as the workflow does:

```bash
python3 .github/tests/test_logged_process.py -v
python3 .github/tests/test_verilator_testharness_comp.py -v
python3 .github/tests/test_verilator_testharness_run.py -v
python3 .github/tests/test_testharness_run_testlist.py -v
python3 .github/tests/test_cook_testharness_smoke.py -v
```

These use mocks and small process fixtures, not RTL simulation. The compilation
file-list existence check needs initialized submodules; it skips when the local
checkout lacks them. Hosted verification checks out submodules recursively.
