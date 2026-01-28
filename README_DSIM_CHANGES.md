# DSim CVA6 Change Log (Detailed)

Purpose
- Provide a precise, line-accurate record of modifications made to enable and debug DSim runs.
- Make changes easy to review, share, and extend by humans or AI.

Scope
- Records only repo modifications related to DSim enablement and DSim-specific debug/mitigations.
- DSim is stricter than Verilator/Questa; SV non-compliance is tracked as first-class work.

How to extend this file
1) Add a new entry under "Change Entries" using the template at the bottom.
2) Reference exact file paths and line numbers from current repo state.
3) Include rationale, verification evidence, and follow-ups.

Change Index
- CHG-001: Add minimal DSim license check SV (2026-01-28)
- CHG-002: Add DSIM_MINIMAL_TRACE mask for ITI/trace pipeline (2026-01-28)
- CHG-003: Expand README_DSIM with DSim usage and CVA6 flow (2026-01-28)
- CHG-004: Create DSim bug log README (2026-01-28)

Change Entries

CHG-001: Minimal DSim license check SV
- Files and lines:
  - `verif/sim/dsim_license_check/minimal_dsim_check.sv:1-7`
- What changed:
  - Added a self-contained SV module that prints a message and exits.
- Why:
  - Provide a fast, deterministic way to verify DSim activation and license.
- How to use:
  - Compile/run per `README_DSIM.md:28-36`.
- Verification evidence:
  - DSim prints "DSim license check" and exits at time 1000 in minimal run.

CHG-002: DSIM_MINIMAL_TRACE mask (ITI/trace pipeline)
- Files and lines:
  - `corev_apu/tb/ariane_testharness.sv:680-793`
- What changed:
  - Wrapped ITI + trace pipeline (cva6_iti, rv_tracer, encapsulator, fifo, slicer) with `ifndef DSIM_MINIMAL_TRACE`.
- Why:
  - Isolate zero-delay loop suspected to trigger DSim IterLimit during hello_world.
- How to enable:
  - Add compile define: `--isscomp_opts="+define+DSIM_MINIMAL_TRACE"`.
- Verification evidence:
  - With the mask enabled, hello_world completes and terminates by $finish (see `README_DSIM_BUGS.md:17-32`).

CHG-003: README_DSIM usage expansion
- Files and lines:
  - `README_DSIM.md:5-93`
- What changed:
  - Documented DSim activation, non-interactive shell behavior, minimal license check, DSim CLI essentials.
  - Added CVA6 hello_world invocation with dsim-testharness and a minimal trace mask section.
- Why:
  - Ensure future sessions can reproduce DSim runs without rediscovery.
- Verification evidence:
  - Commands match actual working runs (DSim 2026 activation + cva6.py flow).

CHG-004: DSim bug log README
- Files and lines:
  - `README_DSIM_BUGS.md:1-84`
- What changed:
  - Created a structured bug log for DSim-specific failures and strictness warnings.
- Why:
  - Provide a shared, discussion-ready basis for team debugging and cleanup.
- Verification evidence:
  - Includes concrete log references and file locations from `hello_world.cv32a65x.log.iss`.

Strictness work tracking (SV non-compliance)
- Source of truth: `README_DSIM_BUGS.md:34-55`
- Action: treat DSim warnings as actionable and log each fix here (future entries).

Template for new entries

CHG-XXX: <short title>
- Date: YYYY-MM-DD
- Files and lines:
  - <path>:<line>
- What changed:
  - <concise change description>
- Why:
  - <rationale>
- How to use / enable:
  - <command or steps>
- Verification evidence:
  - <log path + observed output>
- Follow-ups:
  - <open items>
