# master_candidate Tier CI cook.py adapter

This initial Tier CI implementation ports the public Tier CI structure from the
`master` branch to `master_candidate`. It keeps the established setup action,
runner contract, workflow names, truthful job conclusions, and artifact layout.

The execution path is adapted for the `master_candidate` flow:

1. `cook.py sw-compile-testlist` compiles the selected repository testlist.
2. `cook.py verilator-testharness-run-testlist` runs the compiled ELF files with
   the public Verilator TestHarness and Spike tandem backend.
3. `.github/scripts/run-tier-regression.sh` retains the same `ci-results`
   contract used by the Tier CI on `master`.

The new run recipe is intentionally a transition adapter. `cook.py` owns the
target/testlist selection and software compilation, while the recipe passes the
resulting ELF files to the existing `cva6.py` Verilator TestHarness/Spike
backend. Replacing that mature public execution backend is outside this initial
port.

## Initial scope

Tier 1 provides a fast base sanity signal:

| Target | Testlist | Enabled tests |
| --- | --- | ---: |
| `cv32a60x_axi` | `base_rv32_p` | 5 |
| `cv32a65x_axi` | `base_rv32_p` | 5 |

Tier 2 contains Tier 1 and adds the currently supported extension coverage:

| Target | Testlist | Enabled tests |
| --- | --- | ---: |
| `cv32a60x_axi` | `base_rv32_p` | 5 |
| `cv32a60x_axi` | `base_zcmt` | 4 |
| `cv32a65x_axi` | `base_rv32_p` | 5 |
| `cv32a65x_axi` | `base_zcmt` | 4 |
| `cv32a65x_axi` | `base_pmp` | 5 |

The public compiler ISA is explicit in each matrix entry. In particular,
`cv32a60x_axi` omits `zifencei` because its RTL configuration has
`RVZifencei=0`, even though the current generated `isa.yml` still lists that
extension. `cv32a65x_axi` keeps `zifencei` because its RTL configuration enables
it. Zcmt jobs use LLVM 18 because the cached public GCC toolchain does not
assemble the required Zcmt instructions.

## Comparison boundary

The GitHub workflows do not parse `.gitlab-ci.yml` and do not compare GitHub
job conclusions with Thales GitLab results. The two systems can still be
compared manually because they share the repository revision, `config/target`
inputs, testlist sources, and Spike reference model. Simulator, testbench, and
compiler identities remain explicit in the uploaded metadata.

## Failure and artifact policy

All matrix jobs run with `fail-fast: false`, but a failed test remains a failed
GitHub job and makes the workflow red. Artifacts are uploaded with `if: always()`
and include `ci-results`, cook reports, compilation outputs, simulation logs,
and generated public-backend configuration files.

Dashboard integration and additional targets are deliberately outside this
initial adapter. They can be added after this execution contract is accepted.
