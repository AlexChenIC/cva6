# DSim Notes (local)

Purpose: record the minimal DSim flow that was demonstrated.

Environment
- Activate DSim 2026 in the current shell: `set_dsim26`
- Fallback if set_dsim26 is not available:
  `source /home/junchao/2_System_Setup/AltairDSim/2026/shell_activate.bash`

set_dsim26 alias (from ~/.bashrc)
- Alias definition:
  `alias set_dsim26='export DSIM_LICENSE=/home/junchao/2_System_Setup/AltairDSim/2025.1/dsim-license.json; source /home/junchao/2_System_Setup/AltairDSim/2026/shell_activate.bash'`
- Default UVM_HOME:
  `export UVM_HOME="/home/junchao/2_System_Setup/AltairDSim/2026/uvm/1.2/"`

Notes for non-interactive shells
- Non-interactive shells do not load ~/.bashrc or expand aliases by default.
- Options:
  - `bash -lc 'set_dsim26 && <your dsim command>'`
  - Or: `source ~/.bashrc; shopt -s expand_aliases; set_dsim26`
  - Or: run the two alias commands directly (export DSIM_LICENSE + source shell_activate.bash).

Verified non-interactive activation (equivalent to set_dsim26)
`export DSIM_LICENSE=/home/junchao/2_System_Setup/AltairDSim/2025.1/dsim-license.json`
`source /home/junchao/2_System_Setup/AltairDSim/2026/shell_activate.bash`
`export UVM_HOME="/home/junchao/2_System_Setup/AltairDSim/2026/uvm/1.2/"`

Minimal license check
1) Go to the example folder
   `cd /home/junchao/1_OpenHW_Work/github/cva6/dsim_rtl/cva6/verif/sim/dsim_license_check`

2) Compile and generate the image
   `dsim -sv -sv2012 -work . -top minimal_dsim_check -genimage dsim_image -l dsim_compile.log minimal_dsim_check.sv`

3) Run the image
   `dsim -image dsim_image -work . -l dsim_run.log`

Expected output (license OK)
- Licensed for Altair DSim Cloud
- New lease granted
- Linking dsim_image.so
- DSim license check
- Simulation terminated by $finish at time 1000

Artifacts
- dsim_compile.log
- dsim_run.log
- dsim_image.so

Common DSim 2026 CLI (from `dsim -help`)
- General: `-help`, `-version`, `-l <log>`, `-repro dsim.env`, `-work <dir>`
- Compile: `-sv`, `-sv2012`, `-top <name>`, `-genimage <image>`, `+define+`, `+incdir+`, `-f <flist>`, `+acc`
- Run: `-image <image>`, `-sv_seed <n|random>`, `-iter-limit <n>`, `-waves <file>`, `-pli_lib <so>`, `-sv_lib <so>`
- Coverage/profile: `-code-cov ...`, `-cov-db <db>`, `-profile`, `-profile-start <t>`, `-profile-end <t>`

CVA6 DSim enablement (5 scripts)
- `Makefile`
  - Adds DSIM DPI headers: `DSIM_DPI_INCLUDE ?= $(shell dirname $(shell which dsim))/../include` and `CFLAGS += -I$(DSIM_DPI_INCLUDE)`
  - Defines DSIM build variables and compile flow: `DSIM_COMP_FLAGS ... -genimage $(DSIM_IMAGE_PATH) -top $(top_level)`
  - Builds DSIM filelist and ensures TB sources are included (dsim_flist target).
- `verif/sim/Makefile`
  - Defines DSIM run defaults and wave dump: `DSIM_RUN_FLAGS ?= -iter-limit 10000000`, `DSIM_DMP_FLAGS ?= -waves $(DSIM_DMP_FILE)`
  - `dsim-testharness` compiles with `-genimage dsim_image` and runs with `-image dsim_image` plus `$(DSIM_RUN_FLAGS)`.
- `verif/sim/cva6.yaml`
  - Adds ISS entry: `iss: dsim-testharness` and maps to `make dsim-testharness ...`.
- `verif/sim/cva6-simulator.yaml`
  - Defines DSim compile/run templates for generator: `-genimage image` and `-image image`, uses `DSIM_LIB_PATH` for UVM DPI.
- `verif/sim/setup-env.sh`
  - Sets DSIM binary path (default AltairDSim/2026) and derives `UVM_HOME`/`DSIM_LIB_PATH`.

CVA6 hello_world with DSim 2026
1) Activate DSim
   `export DSIM_LICENSE=/home/junchao/2_System_Setup/AltairDSim/2025.1/dsim-license.json`
   `source /home/junchao/2_System_Setup/AltairDSim/2026/shell_activate.bash`
   `export UVM_HOME="/home/junchao/2_System_Setup/AltairDSim/2026/uvm/1.2/"`
2) Set toolchain and simulator
   `export RISCV=/home/junchao/2_System_Setup/riscv_toolchain`
   `export DV_SIMULATORS=dsim-testharness`
3) Run hello_world (from repo root)
   `source verif/sim/setup-env.sh`
   `cd verif/sim`
   `CC_OPTS="-static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles -g ../tests/custom/common/syscalls.c ../tests/custom/common/crt.S -I../tests/custom/env -I../tests/custom/common -lgcc"`
   `python3 cva6.py --c_tests ../tests/custom/hello_world/hello_world.c --iss_yaml cva6.yaml --target cv32a65x --iss=$DV_SIMULATORS --linker=../../config/gen_from_riscv_config/cv32a65x/linker/link.ld --gcc_opts="$CC_OPTS"`

Minimal mask (iter-limit isolation)
- Define `DSIM_MINIMAL_TRACE` to disable the ITI/trace pipeline in `corev_apu/tb/ariane_testharness.sv`.
- Enable via compile opts:
  `python3 cva6.py ... --isscomp_opts="+define+DSIM_MINIMAL_TRACE"`

References (DSim options)
- `-genimage` / `-image`: https://help.metrics.ca/support/solutions/articles/154000141207-user-guide-dsim-compile-once-run-multiple-times
- `-waves`: https://help.metrics.ca/support/solutions/articles/154000141180-user-guide-dsim-dumping-opening-waveforms
- `-iter-limit`: https://help.metrics.ca/support/solutions/articles/154000141196-user-guide-dsim-common-options
