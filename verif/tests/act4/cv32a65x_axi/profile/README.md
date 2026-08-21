# `cv32a65x_axi` ACT profile assets

This directory contains the CVA6 testbench-facing files used when resolving the
ACT profile.  `link.ld` and `rvmodel_macros.h` intentionally match the files in
the pinned upstream `cv32a65x` profile.  Their upstream hashes are recorded in
`../generation-lock.json` and checked by the resolver.

## Why an overlay is required

The upstream profile is named `cv32a65x`, while the Master Candidate target is
`cv32a65x_axi`.  AXI versus OBI is a system-interface distinction and does not
change the architectural instruction behavior by itself.  The current target
configuration nevertheless differs from the pinned ACT profile in several
architecturally visible settings:

- the target enables `Zifencei` and `Zcmt`;
- `M` 2.0 requires the architectural `Zmmul` subset, so the overlay declares
  `Zmmul` 1.0 explicitly (matching the already-enabled Sail setting);
- the target has eight usable PMP entries;
- `PMPNapotEn` is false, so NA4/NAPOT modes are modeled as unsupported while
  TOR remains available;
- `PerfCounterEn` is false, so the inherited HPM enable bitmap is cleared.

The CVA6 PMP has an 8-byte minimum granularity, represented as
`PMP_GRANULARITY: 3` in UDB (log2 bytes) and `grain: 1` in Sail (the PMP G
field).  ACT/UDB exposes PMP banks in schema-supported counts (0, 16, or 64)
and separately records how many are usable.  The overlay therefore uses
`NUM_PMP_ENTRIES: 16` plus `NUM_USABLE_PMP_ENTRIES: 8`; Sail mirrors this as
`count: 16` and `usable_count: 8`.  This is an explicit mapping from CVA6's
eight implemented entries into ACT's architectural bank model and must be
reviewed with the CVA6 and ACT maintainers before privileged tests are enabled.

## Interrupt generator boundary

The ACT Sail reference model needs its simple interrupt generator at
`0x15000000` while producing expected signatures.  That device is added only to
the resolved `sail.json`, together with a 4 KiB Sail I/O memory region.  The
device itself uses only a small register window, but Sail 0.13.1 requires the
PMA region to end on a 4 KiB page boundary.  The resolver re-sorts all Sail
regions by base address after insertion, placing the
SIG after the low-address I/O devices and before RAM as required by Sail's
schema, while rejecting any overlap.

It is deliberately absent from `rvmodel_macros.h`: the CVA6 Verilator
testharness does not expose the Sail helper device at that address.  Normal Tier
CI consumes already self-checking tests and must not accidentally turn this
reference-model helper into a DUT MMIO contract.

## Initial coverage boundary

The UDB declaration includes the inherited `Sm` 1.12 extension, but
`include_priv_tests` is fixed to `false`.  The first corpus can validate the
unprivileged ISA path without claiming PMP, trap, or interrupt certification.
The target declares Zcmt and its JVT parameters, but the pinned ACT tree has no
Zcmt suite; this corpus therefore does not certify Zcmt.  Suite selection is
left to ACT's compatible-unprivileged selection so combination and misalignment
suites are not accidentally omitted, and the generated manifest/corpus must
record the actual selected tests.
Enabling privileged ACTs requires a reviewed profile update, DUT-side interrupt
macro implementations where applicable, a regenerated corpus, and an explicit
coverage review.

The provisional UDB `JVT_BASE_MASK` is `0x7fffffc0`, while the target's locked
`spike.yaml` records `jvt_write_mask: 0xffffffc0`.  The pinned ACT tree has no
Zcmt suite, so the current corpus cannot resolve this discrepancy by testing
it.  Treat the value as a maintainer-review gate; do not describe the JVT/Zcmt
profile as confirmed until CVA6 RTL owners and ACT/UDB maintainers agree on the
architectural interpretation.

## Known provenance limitation

The pinned inputs and container digest make an independent generation auditable
and repeatable in scope, but not necessarily byte-identical.  Two independent
I-only validation runs with the same pins selected the same 39 I ELFs and
exercised the same functionality, while some ELF hashes differed because GCC
embedded randomized temporary `cc*.o` names as `STT_FILE` symbols.  The frozen
full compatible-unprivileged corpus contains 127 ELFs.  Packaging is
deterministic for one fixed set of generated inputs; independent regeneration
is currently judged by pins, selected-test manifest, validation, and behavior
rather than identical ELF bytes.  This limitation belongs in release/review
evidence until the compiler artifact is normalized and a two-run
byte-reproducibility check passes.
