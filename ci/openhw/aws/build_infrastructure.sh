#!/bin/bash
# Copyright 2024 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
#
# Infrastructure Build Script
# Location: ci/openhw/aws/build_infrastructure.sh
#
# This script orchestrates the installation of necessary tools (Verilator, Spike, Toolchain).
# It wraps the existing legacy scripts in 'ci/' to ensure compatibility but adds
# checks suitable for CI/Cloud environments.

set -e
set -o pipefail

# Get the directory of this script to source env_setup correctly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env_setup.sh"

echo "[INFO] Starting Infrastructure Build..."

# --- 1. System Prerequisites ---
# Installs packages like make, autoconf, dtc, etc.
echo "[INFO] Installing System Prerequisites..."
if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y --no-install-recommends \
        build-essential \
        autoconf \
        automake \
        libtool \
        pkg-config \
        flex \
        bison \
        libfl-dev \
        help2man \
        device-tree-compiler \
        python3 \
        python3-pip
else
    echo "[WARN] apt-get not available. Skipping system prerequisites install."
fi

# --- 2. RISC-V Toolchain ---
# In a real CI, this is often cached. This script assumes if the directory
# exists and is non-empty, we might be good, or it delegates to the install script
# which usually handles logic.
echo "[INFO] Checking RISC-V Toolchain..."
if [ ! -d "$RISCV/bin" ]; then
    echo "[INFO] Toolchain not found. Installing..."
    # Note: ci/install-toolchain.sh often takes a long time.
    # In GitHub Actions, we rely on the 'cache' step restoring this.
    # If this runs, it means cache miss or fresh build.
    bash "$PROJECT_ROOT/ci/install-toolchain.sh"
else
    echo "[INFO] Toolchain directory exists at $RISCV. Assuming valid or restored from cache."
fi

# --- 3. Verilator ---
# Use the official regress install script to align with CVA6 flow.
echo "[INFO] Checking Verilator..."
export VERILATOR_INSTALL_DIR="$TOOLS_DIR/verilator"
if [ -z "$VERILATOR_BUILD_DIR" ]; then
    export VERILATOR_BUILD_DIR="$VERILATOR_INSTALL_DIR/build-v5.008"
fi
if [ ! -f "$VERILATOR_INSTALL_DIR/bin/verilator" ]; then
    echo "[INFO] Verilator not found. Installing..."
    source "$PROJECT_ROOT/verif/regress/install-verilator.sh"
else
     echo "[INFO] Verilator already installed at $VERILATOR_INSTALL_DIR."
fi

# --- 4. Spike (ISA Simulator) ---
echo "[INFO] Checking Spike..."
export SPIKE_INSTALL_DIR="$TOOLS_DIR/spike"
if [ -z "$SPIKE_SRC_DIR" ]; then
    export SPIKE_SRC_DIR="$PROJECT_ROOT/verif/core-v-verif/vendor/riscv/riscv-isa-sim"
fi
if [ ! -f "$SPIKE_INSTALL_DIR/bin/spike" ]; then
    echo "[INFO] Spike not found. Installing..."
    source "$PROJECT_ROOT/verif/regress/install-spike.sh"
else
    echo "[INFO] Spike already installed at $SPIKE_INSTALL_DIR."
fi

# --- 5. Python Requirements ---
echo "[INFO] Installing Python requirements..."
if [ -f "$PROJECT_ROOT/verif/sim/dv/requirements.txt" ]; then
    python3 -m pip install --upgrade pip
    python3 -m pip install -r "$PROJECT_ROOT/verif/sim/dv/requirements.txt"
else
    echo "[WARN] requirements.txt not found. Skipping Python dependencies."
fi

echo "[INFO] Infrastructure Build Complete."
