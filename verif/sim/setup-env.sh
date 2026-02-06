# CVA6 project root
if [ -n "$BASH_VERSION" ]; then
  SCRIPT_PATH="$BASH_SOURCE[0]"
elif [ -n "$ZSH_VERSION" ]; then
  SCRIPT_PATH="${(%):-%N}"
else
  echo "Error: Non recognized shell."
  return
fi
export ROOT_PROJECT=$(readlink -f $(dirname "${SCRIPT_PATH}")/../..)

export RTL_PATH="$ROOT_PROJECT/"
export TB_PATH="$ROOT_PROJECT/verif/tb/core"
export TESTS_PATH="$ROOT_PROJECT/verif/tests"

# RISCV-DV & COREV-DV
export RISCV_DV_ROOT="$ROOT_PROJECT/verif/sim/dv"
export CVA6_DV_ROOT="$ROOT_PROJECT/verif/env/corev-dv"

if [ -z "$RISCV" ]; then
  echo "Error: RISCV variable undefined."
  return
fi
# Set RISCV toolchain-related variables
export LIBRARY_PATH="$RISCV/lib"
export LD_LIBRARY_PATH="$RISCV/lib:$LD_LIBRARY_PATH"
export C_INCLUDE_PATH="$RISCV/include"
export CPLUS_INCLUDE_PATH="$RISCV/include"

# Auto-detect RISC-V tool name prefix if not explicitly given.
if [ -z "$CV_SW_PREFIX" ]; then
    export CV_SW_PREFIX="$(ls -1 $RISCV/bin/riscv* | head -n 1 | rev | cut -d '/' -f 1 | cut -d '-' -f 2- | rev)-"
fi
# Default to auto-detected CC name if not explicitly given.
if [ -z "$RISCV_CC" ]; then
    export RISCV_CC="$RISCV/bin/${CV_SW_PREFIX}gcc"
fi
# Default to auto-detected OBJCOPY name if not explicitly given.
if [ -z "$RISCV_OBJCOPY" ]; then
    export RISCV_OBJCOPY="$RISCV/bin/${CV_SW_PREFIX}objcopy"
fi

# Set verilator and spike related variables
if [ -z "$VERILATOR_INSTALL_DIR" ]; then
    export VERILATOR_INSTALL_DIR="$ROOT_PROJECT"/tools/verilator
fi

if [ -z "$SPIKE_SRC_DIR" -o "$SPIKE_INSTALL_DIR" = "__local__" ]; then
  export SPIKE_SRC_DIR="$ROOT_PROJECT"/verif/core-v-verif/vendor/riscv/riscv-isa-sim
fi

if [ -z "$SPIKE_INSTALL_DIR" -o "$SPIKE_INSTALL_DIR" = "__local__" ]; then
    export SPIKE_INSTALL_DIR="$ROOT_PROJECT"/tools/spike
fi

export SPIKE_PATH="$SPIKE_INSTALL_DIR"/bin

# Proxy Kernel install (optional)
if [ -z "$PK_INSTALL_DIR" ]; then
  export PK_INSTALL_DIR="$ROOT_PROJECT/tools/pk"
fi
if [ ! -x "$PK_INSTALL_DIR/riscv-none-elf/bin/pk" ]; then
  echo "Warning: pk not found at $PK_INSTALL_DIR/riscv-none-elf/bin/pk"
  echo "         If you need proxy kernel flow, run verif/regress/install-pk.sh first."
fi
export PATH="$PK_INSTALL_DIR/bin:$PATH"

# DSIM setup (prefer DSIM_HOME if provided, otherwise fallback to default install)
DSIM_INSTALL_DEFAULT="$HOME/2_System_Setup/AltairDSim/2026"
if [ -z "$DSIM_HOME" ]; then
  if [ -x "$DSIM_INSTALL_DEFAULT/bin/dsim" ]; then
    export DSIM_HOME="$DSIM_INSTALL_DEFAULT"
  fi
fi

if [ -n "$DSIM_HOME" ]; then
  export DSIM="$DSIM_HOME/bin/dsim"
  export LLVM_HOME="$DSIM_HOME/llvm_small"
  export STD_LIBS="$DSIM_HOME/std_pkgs/lib"
  export RADFLEX_PATH="$DSIM_HOME/radflex"
  export LD_LIBRARY_PATH="$DSIM_HOME/llvm_small/lib:$DSIM_HOME/lib:$LD_LIBRARY_PATH"
  # DSIM cloud license - must be explicitly set
  if [ -z "$DSIM_LICENSE" ]; then
    # First try license in DSIM_HOME, then fallback to default location
    if [ -f "$DSIM_HOME/dsim-license.json" ]; then
      export DSIM_LICENSE="$DSIM_HOME/dsim-license.json"
    elif [ -f "$HOME/2_System_Setup/AltairDSim/2026/dsim-license.json" ]; then
      export DSIM_LICENSE="$HOME/2_System_Setup/AltairDSim/2026/dsim-license.json"
    fi
  fi
elif [ -z "$DSIM" ]; then
  if command -v dsim >/dev/null 2>&1; then
    export DSIM="$(command -v dsim)"
    export DSIM_HOME="$(cd "$(dirname "$DSIM")/.." && pwd)"
  else
    echo "Error: DSIM not found. Please set DSIM_HOME to your DSIM installation directory."
    return
  fi
fi

if [ -z "$UVM_HOME" ] && [ -n "$DSIM_HOME" ]; then
  if [ -d "$DSIM_HOME/uvm/1.2" ]; then
    export UVM_HOME="$DSIM_HOME/uvm/1.2"
  fi
fi

if [ -z "$DSIM_LIB_PATH" ] && [ -n "$UVM_HOME" ]; then
  export DSIM_LIB_PATH="$UVM_HOME/src/dpi"
fi

export PATH="$(dirname "$DSIM"):$VERILATOR_INSTALL_DIR/bin:$RISCV/bin:$PATH"
