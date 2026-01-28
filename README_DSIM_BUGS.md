# DSim CVA6 Bug Log

Purpose
- Track DSim-specific failures and strictness findings for CVA6 runs.
- Record fixes, mitigations, and open items for team discussion.

Baseline environment
- DSim 2026 activation:
  - `export DSIM_LICENSE=/home/junchao/2_System_Setup/AltairDSim/2025.1/dsim-license.json`
  - `source /home/junchao/2_System_Setup/AltairDSim/2026/shell_activate.bash`
  - `export UVM_HOME="/home/junchao/2_System_Setup/AltairDSim/2026/uvm/1.2/"`
- CVA6 repo: `/home/junchao/1_OpenHW_Work/github/cva6/dsim_rtl/cva6`
- Example log: `verif/sim/out_2026-01-28/dsim-testharness_sim/hello_world.cv32a65x.log.iss`

Issue log (DSim CVA6 hello_world)

1) IterLimit at time 1750 (zero-delay loop)
- Symptom: DSim aborts with `=F:[IterLimit] ... exceeded; aborting at 1750.`
- Evidence: observed in earlier run without `DSIM_MINIMAL_TRACE` (log overwritten in current output).
- Mitigation: define `DSIM_MINIMAL_TRACE` to bypass ITI/trace pipeline.
  - Location: `corev_apu/tb/ariane_testharness.sv`
  - Enable: `--isscomp_opts="+define+DSIM_MINIMAL_TRACE"`
- Status: mitigated; root cause still unknown.

2) Post-run spike-dasm cannot open trace file
- Symptom: `/bin/sh: 1: cannot open ./trace_rvfi_hart_00.dasm: No such file`
- Evidence: `verif/sim/out_2026-01-28/dsim-testharness_sim/hello_world.cv32a65x.log.iss:655-659`
- Cause: `spike-dasm` runs from repo root while `trace_rvfi_hart_00.dasm` is in `dsim_work`.
- Fix options:
  - Run `spike-dasm` in `$(DSIM_WORK_PATH)` (cd before command)
  - Or use absolute path to `$(DSIM_WORK_PATH)/trace_rvfi_hart_00.dasm`
- Status: open.

3) DSim strictness warnings (non-compliant SV)
- Evidence: `verif/sim/out_2026-01-28/dsim-testharness_sim/hello_world.cv32a65x.log.iss:63-103`
- Examples and candidates:
  - Index out of bounds
    - `core/cvxif_example/instr_decoder.sv:68`
    - `core/csr_regfile.sv:2010`
    - `core/issue_read_operands.sv:627`
    - `core/pmp/src/pmp.sv:37`
  - SlicePartOOB
    - `core/load_store_unit.sv:339`
  - ExprStmtNotVoid
    - `corev_apu/tb/rvfi_tracer.sv:52`
  - PortWidthMismatch
    - `corev_apu/tb/ariane_testharness.sv:325,644-645`
  - ReadingOutputModport
    - `corev_apu/axi_mem_if/src/axi2mem.sv:209`
    - `corev_apu/src/axi_riscv_atomics/src/axi_riscv_atomics_wrap.sv:61,74,80...`
- Recommended fix patterns:
  - Guard indices, widen vectors, or clamp slice bounds
  - Match port widths or add explicit casts/resize logic
  - Avoid reading output modports (use internal signal or proper modport direction)
- Status: open, needs targeted cleanup.

4) UVM absolute path warning (cloud portability)
- Symptom: `=W:[UVMSetup] Absolute path ... will not work in DSim Cloud`
- Evidence: `verif/sim/out_2026-01-28/dsim-testharness_sim/hello_world.cv32a65x.log.iss:30-34`
- Fix: use relative UVM path and ensure mdc sync for cloud runs.
- Status: informational.

Setup pitfalls (observed previously, not in current log)
- License failure if DSIM_LICENSE/LM_LICENSE_FILE is not set.
- Typical error: `Error Code: 15` + `Invalid config file` (falls back to `6200@localhost`).
- Fix: export `DSIM_LICENSE` and source `shell_activate.bash` (see Baseline environment).

Strictness reminders
- DSim is stricter than Verilator/Questa; warnings above must be treated as actionable.
- Every new DSim warning should be logged here with:
  - Symptom
  - Evidence (log path + line)
  - Root cause hypothesis
  - Fix/mitigation
  - Status

Template (copy for new entries)
- Issue ID/Title:
- Symptom:
- Evidence (log path + line):
- Root cause hypothesis:
- Fix / mitigation:
- Status:
