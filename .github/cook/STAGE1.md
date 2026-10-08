# Bounded Cook Stage 1

The candidate aligns with upstream Cook RecipeReport and uses only the
public software compile, TestHarness compile, single-run and testlist
recipes. Core RTL/RVFI and target files match the recorded upstream SHA.

Required Tier 1 targets are cv32a60x_axi, cv32a65x_sv32_axi and
cv64a6_imafdc_sv39_hpdcache_pmp_mmu_axi. Each uses two finite integer lists
with an explicitly adapted M-mode startup and strict native live tandem.
An independent single-run repeats the first test; it adds no coverage.
The manual 60x pilot adds the finite multiply/divide list.

Workflow dispatch accepts selection=profiles, pilots or diagnostics.
Required profiles always run all three targets. The optional profile
input can limit diagnostics/pilots only. cold_tools bypasses tool caches;
hardware and software are rebuilt from scratch regardless of that flag.

Local reproduction on a Linux host with compatible GCC, Verilator 5.050,
and the pinned vendor Spike installation:

```sh
export CONFIG_DIR="$PWD/ci-results/cook-config"
python3 .github/cook/prepare_toolchains.py --output-dir "$CONFIG_DIR" --tandem-enabled
python3 .github/cook/run_stage1.py --selection profiles --profile rv32-60x
python3 cook.py merge-reports -t cv32a60x_axi --quiet
python3 cook.py report-html --quiet
```

Prepare the pinned riscv-tests source using
verif/regress/install-riscv-tests.sh first. Each invocation needs a fresh
target build directory. Use the other profile names from stage1.yml to
reproduce their jobs.

Download each live artifact and check raw native results, Cook reports,
manifests, source/model snapshots, ELF identity and negative-control logs.
Negative controls are infrastructure verification, not architectural
testcases: expected stack rejection, SIGTERM, timeout and wrong-Spike-ELF
divergence must all be observed. An intentionally failed program also
must exit the public Cook Run CLI with code 1 and failing report/receipt.
After checking it, the unchanged failing Run directory is archived under
ci-results/native-negative/software-fail/run, outside the functional
report merge. Its failed report remains available in the artifact.
Errors in those logs are intentional;
unobserved rejection is a CI failure.

Hello remains a separate RTL-only regression of the merged smoke recipes;
it is not counted as live coverage. Nightly/dashboard deployment is outside
Stage 1. See SPIKE_KNOWN_LIMITATIONS.md before quoting results.
