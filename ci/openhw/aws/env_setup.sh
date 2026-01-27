#!/bin/bash
# Copyright 2024 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
#
# Environment Setup Script for CVA6 CI
# Location: ci/openhw/aws/env_setup.sh
#
# This script sets up the base environment variables required for the toolchain
# and simulators. It is designed to be sourced by other scripts.
#
# It distinguishes between:
# 1. GitHub Actions (Runner)
# 2. Future AWS Self-Hosted / Local environments

# --- 1. Root Directory Detection ---
# If GITHUB_WORKSPACE is set (GitHub Actions), use it. Otherwise use script location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "$GITHUB_WORKSPACE" ]; then
    export PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    echo "[INFO] Running Locally or on Self-Hosted. Root: $PROJECT_ROOT"
else
    export PROJECT_ROOT="$GITHUB_WORKSPACE"
    echo "[INFO] Running on GitHub Actions. Root: $PROJECT_ROOT"
fi

# --- 2. Toolchain Paths ---
# Define standard paths for tools relative to the project root
# This allows for easy relocation or mapping in Docker containers later.
export TOOLS_DIR="$PROJECT_ROOT/tools"
if [ -z "$RISCV" ]; then
    export RISCV="$TOOLS_DIR/riscv-toolchain"
fi
if [ -z "$VERILATOR_ROOT" ]; then
    export VERILATOR_ROOT="$TOOLS_DIR/verilator"
fi
if [ -z "$SPIKE_ROOT" ]; then
    export SPIKE_ROOT="$TOOLS_DIR/spike"
fi
if [ -z "$VERILATOR_INSTALL_DIR" ]; then
    export VERILATOR_INSTALL_DIR="$VERILATOR_ROOT"
fi
if [ -z "$SPIKE_INSTALL_DIR" ]; then
    export SPIKE_INSTALL_DIR="$SPIKE_ROOT"
fi
if [ -z "$SPIKE_SRC_DIR" ]; then
    export SPIKE_SRC_DIR="$PROJECT_ROOT/verif/core-v-verif/vendor/riscv/riscv-isa-sim"
fi

# Add binaries to PATH
export PATH="$RISCV/bin:$VERILATOR_ROOT/bin:$SPIKE_ROOT/bin:$PATH"

# --- 3. Simulator specific configuration ---
# Detect which simulator to use (default to verilator)
SIMULATOR="${SIMULATOR:-verilator}"

# Commercial EDA Tool Paths
# These can be overridden by environment variables set by external license scripts
# or by the self-hosted runner configuration.

# Siemens Questa (Modelsim)
if [ -z "$QUESTASIM_HOME" ]; then
    # Default path - override in self-hosted runner or external script
    export QUESTASIM_HOME="${QUESTASIM_HOME:-/opt/siemens/questasim}"
fi
if [ -z "$QUESTA_HOME" ]; then
    export QUESTA_HOME="$QUESTASIM_HOME"
fi
if [ -z "$MTI_HOME" ]; then
    export MTI_HOME="$QUESTASIM_HOME"
fi

# Synopsys VCS
if [ -z "$VCS_HOME" ]; then
    export VCS_HOME="${VCS_HOME:-/opt/synopsys/vcs}"
fi

# UVM Library (usually bundled with Questa/VCS)
if [ -z "$UVM_HOME" ]; then
    if [ "$SIMULATOR" == "questa" ] || [ "$SIMULATOR" == "questa-uvm" ]; then
        export UVM_HOME="$QUESTASIM_HOME/verilog_src/uvm-1.2"
    elif [ "$SIMULATOR" == "vcs" ] || [ "$SIMULATOR" == "vcs-uvm" ]; then
        export UVM_HOME="$VCS_HOME/etc/uvm-1.2"
    fi
fi

# License Configuration
# IMPORTANT: License servers/files should be configured externally, NOT in this repo.
# Self-hosted runners should set these via:
#   1. Environment variables in the runner configuration
#   2. An external script sourced before CI runs (e.g., /opt/eda/license_setup.sh)
#   3. FlexLM environment variables (LM_LICENSE_FILE, SNPSLMD_LICENSE_FILE, etc.)
#
# Example external setup (NOT stored in repo):
# export LM_LICENSE_FILE="port@license_server"
# export SNPSLMD_LICENSE_FILE="port@license_server"
# export MGLS_LICENSE_FILE="port@license_server"
#
# If an external license setup script exists, source it:
EXTERNAL_LICENSE_SCRIPT="${EXTERNAL_LICENSE_SCRIPT:-/opt/eda/license_setup.sh}"
if [ -f "$EXTERNAL_LICENSE_SCRIPT" ]; then
    echo "[INFO] Sourcing external license configuration: $EXTERNAL_LICENSE_SCRIPT"
    source "$EXTERNAL_LICENSE_SCRIPT"
fi

# Add commercial tools to PATH if they exist
if [ -d "$QUESTASIM_HOME/bin" ]; then
    export PATH="$QUESTASIM_HOME/bin:$PATH"
fi
if [ -d "$VCS_HOME/bin" ]; then
    export PATH="$VCS_HOME/bin:$PATH"
fi

# --- 4. System Dependencies (Apt) ---
# Only run this if explicitly requested or if we detect we are in a bare environment
# that needs prereqs. For GitHub Actions, we usually run this in a separate step or
# rely on the 'install-prereq.sh'
export CVA6_CI_ENV_SET=1

echo "[INFO] Environment Setup Complete."
echo "       RISCV: $RISCV"
echo "       VERILATOR_ROOT: $VERILATOR_ROOT"
echo "       SPIKE_ROOT: $SPIKE_ROOT"
