# ACT 4.0 profiles and generated tests

This directory is the CVA6-owned boundary around the upstream RISC-V
Architectural Certification Tests (ACT) repository.  The upstream checkout is
an input, not a vendored or writable dependency.

The first supported target is `cv32a65x_axi`.  Its profile is derived from the
upstream `config/cores/cva6/cv32a65x` profile at the exact commit recorded in
`cv32a65x_axi/generation-lock.json`.  CVA6-specific differences are kept in
`cv32a65x_axi/profile-overlay.json`; the upstream checkout must never be edited
to apply them.

The intended split is:

1. A regeneration job resolves the pinned upstream profile plus the local
   overlay, runs Sail, and produces self-checking assembly/ELF artifacts.
2. Normal Tier CI consumes a reviewed, frozen corpus.  It does not clone ACT or
   run Sail on every CVA6 change.
3. Regeneration is required when the ACT pin, profile/overlay, toolchain, or
   architectural contract changes.  Ordinary RTL bug fixes do not by
   themselves require regeneration.

The profile resolver verifies the upstream Git commit and every locked source
hash before producing files.  It also refuses to write its output anywhere
inside the upstream checkout.  A successful resolution emits a
`resolved-profile.json` manifest beside the generated profile files so the
corpus generator can record exactly what it consumed.

## Reproducibility boundary

The lock makes the generation environment and inputs pinned and reviewable,
and the corpus packager can produce a deterministic archive from one fixed set
of already-generated files.  It does **not** currently guarantee byte-identical
ELFs across two independent ACT regeneration runs.  GCC may give temporary
objects randomized `cc*.o` names that survive as `STT_FILE` symbols, changing
the ELF SHA without changing the selected tests or executable behavior.

Review evidence must therefore distinguish these claims:

- same ACT/CVA6/profile/container pins and the same selected test set: required;
- successful Sail/config validation and equivalent test behavior: required;
- deterministic packaging of the exact same generated input files: required;
- byte-identical ELF hashes across independent regeneration runs: not yet a
  supported guarantee.

If byte-for-byte regeneration becomes a project requirement, the build must
first normalize or eliminate the randomized compiler-local file symbols and add
an explicit two-run reproducibility test.  Until then, do not describe this
pipeline as fully reproducible at the ELF-byte level.

The target declaration includes the inherited `Sm` 1.12 profile, while the
initial generation scope deliberately sets `include_priv_tests: false`.
This is a coverage boundary, not a claim that privileged behavior is correct.
PMP and interrupt-related profile values must receive CVA6/ACT maintainer review
before privileged ACTs are enabled.

`cv32a65x_axi` declares Zcmt, but the pinned ACT tree contains no Zcmt suite.
Zcmt is therefore an explicit coverage gap rather than an implied pass.  ACT is
allowed to select all other compatible unprivileged tests so combination and
misalignment suites are not silently lost; the frozen-corpus manifest is the
authority for the exact set that actually ran.

See `cv32a65x_axi/profile/README.md` for the target mapping and known review
gates.

## Checked-in corpus

The initial `cv32a65x_axi` corpus is intentionally labelled
`basic-architectural-subset` and has `certification_claim: false`.  Its
`corpus-manifest.json` is the machine-readable authority.  At the pinned
generation baseline it contains 127 final self-checking ELFs:

| Suite | ELFs |
| --- | ---: |
| I | 39 |
| M | 8 |
| Zba | 3 |
| Zbb | 18 |
| Zbc | 3 |
| Zbs | 8 |
| Zca | 26 |
| Zcb and compatible combination suites | 11 |
| Zicsr | 6 |
| Zifencei | 1 |
| Zmmul | 4 |
| **Total** | **127** |

The Git-reviewed manifest is the trust root.  Against that manifest, the
resolved profile, archive, and every ELF are SHA-256 integrity-verified before
extraction.  The runtime rejects a missing, additional, linked, special,
empty, oversized, or modified archive member before it starts the TestHarness.

The generated ELFs incorporate ACT test and environment code whose upstream
files use Apache-2.0 and BSD-3-Clause licenses.  The exact ACT repository and
commit are retained in the resolved profile.  Before this binary corpus is
submitted upstream, the CVA6 maintainers should confirm the preferred placement
of the corresponding ACT copyright and redistribution notices alongside the
archive; freezing binaries does not change or remove those obligations.

## Routine Cook/Tier execution

Routine CI does not need the ACT checkout or Sail.  It needs a CVA6
TestHarness built for the exact target; the TestHarness still links FESVR from
the project's pinned Spike installation even though no live Spike reference
model participates in the ACT verdict.

```bash
source verif/sim/setup-env.sh
env -u SPIKE_TANDEM make -j"${NUM_JOBS:-8}" \
  verilate target=cv32a65x_axi

env -u SPIKE_TANDEM ./cook.py act4-run \
  --target cv32a65x_axi \
  --corpus-directory verif/tests/act4/cv32a65x_axi/corpus \
  --simulator work-ver/Variane_testharness \
  --cycle-timeout 10000000 \
  --wall-timeout-seconds 300
```

A test passes only when the simulator returns zero and its log contains
exactly one `*** SUCCESS *** (tohost = 0)` line bound to the absolute path of
the current ELF.  A present `RVCP-SUMMARY` must likewise be the single exact
PASS record for the current source.  Timeout, nonzero return, missing/duplicate
success, another ELF's success, `*** FAILED ***`, `UVM_ERROR`, or `UVM_FATAL`
all fail the Cook command.

The Tier wrapper exposes the same path as `TIER_MODE=act4-prebuilt`; the first
integration is a dedicated Tier 1 job for `cv32a65x_axi`, rather than a live
Spike tandem test or a normal Cook-compiled testlist.

## Low-frequency regeneration

Regeneration is a deliberate maintainer operation.  Never point it at a
floating `act4` branch and never let it modify the upstream checkout.  The
canonical local entry point reads and verifies `generation-lock.json`, exports
the exact ACT Git object, pins both image digest and platform, and performs no
Git write operation:

```bash
ACT4_SOURCE=/path/to/read-only/riscv-arch-test \
ACT4_DOCKER_CONTEXT=colima-act4-cva6 \
ACT4_REPLACE=1 \
  .github/scripts/generate-act4-corpus.sh
```

`ACT4_REPLACE=1` is deliberately required when a corpus already exists.  Use
`ACT4_KEEP_WORK=1` when reviewers need the complete intermediate work tree;
the normal evidence directory retains the generation log and resolved profile.
The implementation performs the following steps and must not silently
substitute newer tools:

1. Obtain the canonical ACT repository outside this CVA6 checkout and detach
   it at the locked 40-character commit.  Require a clean work tree.
2. Resolve the locked upstream files plus the CVA6 overlay into a disposable
   output directory:

   ```bash
   python3 -m flows.act4.profile \
     --act4-root "${ACT4_SOURCE}" \
     --output-dir "${ACT4_RESOLVED_PROFILE}"
   ```

3. Export the locked ACT commit with `git archive` into a clean scratch tree.
   This prevents ignored `.venv` files or unrelated local edits from entering
   the generator input.  Directly copying a developer checkout is not an
   accepted release-generation path.
4. Run the locked container by digest, mounting the ACT scratch tree and
   resolved profile read-only:

   ```bash
   docker run --rm --cpus=12 --memory=20g \
     --platform linux/arm64 \
     --mount "type=bind,src=${ACT4_SCRATCH},dst=/src,readonly" \
     --mount "type=bind,src=${ACT4_RESOLVED_PROFILE},dst=/profile,readonly" \
     --mount "type=bind,src=${ACT4_OUTPUT},dst=/out" \
     ghcr.io/riscv/act4-build@sha256:3167a1e637af1ee068b3c2d14ef890689628490f469e5ac1b8238b1ecaa61a6d \
     bash -c '
       set -eu
       cp -a /src/. /act4/
       cd /act4
       mise install
       CONFIG_FILES=/profile/test_config.yaml \
       WORKDIR=/out FAST=True make elfs --jobs 12
     '
   ```

5. Review the selected suites and all generator logs, then package only final
   ELFs.  `.sig.elf` intermediates are rejected:

   ```bash
   ./cook.py act4-package \
     --target cv32a65x_axi \
     --elf-directory "${ACT4_OUTPUT}/cv32a65x_axi/elfs" \
     --resolved-profile "${ACT4_RESOLVED_PROFILE}/resolved-profile.json" \
     --act-commit ffb1fffc78b264c6c0a0676532d89eaa2e8d8918 \
     --cva6-commit e7c272c93dc0db08d030f1ebe7412af8d78dae6b \
     --image-digest sha256:3167a1e637af1ee068b3c2d14ef890689628490f469e5ac1b8238b1ecaa61a6d \
     --output-directory verif/tests/act4/cv32a65x_axi/corpus \
     --replace
   ```

`--replace` is intentionally explicit.  A changed corpus must be reviewed as a
generated artifact update: compare the manifest, suite counts, profile and
tool pins, then rerun the complete frozen corpus and the negative safety tests.
The packager performs no Git operation.

## Current validation evidence and remaining gates

The local integration has validated the UDB and Sail configuration, generated
the corpus with the pinned ACT image, and exercised the standalone
`cv32a65x_axi` Verilator TestHarness.  This is engineering evidence for the
basic unprivileged regression path; it is not an architectural certification.

Before the scope can expand, CVA6 and ACT maintainers must review at least the
PMP bank mapping, privileged specification version and CSR behavior,
RVMODEL/Trick-Box interrupt services, and the absence of a Zcmt ACT suite.
Adding privileged/interrupt tests or another Core Configuration requires a new
reviewed profile and corpus rather than renaming or reusing this one.
