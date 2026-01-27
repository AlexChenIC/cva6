#!/bin/bash
# Copyright 2024 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
#
# Verification Execution Script
# Location: ci/openhw/aws/run_verification.sh
#
# This script is the unified entry point for running regressions.
# It abstracts the specific shell command needed to run tests, allowing
# different simulators (Verilator, Questa, DSim) to be plugged in easily.

set -e
set -o pipefail

# --- Arguments ---
TARGET_CONFIG=${1:-cv32a65x}           # Default config
TEST_SCRIPT=${2:-smoke-tests-cv32a65x.sh} # Default test script
SIMULATOR=${3:-verilator}              # Default simulator

# --- Setup ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env_setup.sh"

normalize_simulator() {
    local sim="$1"
    case "$sim" in
        verilator|veri-testharness)
            SIMULATOR_LABEL="verilator"
            DV_SIMULATORS="veri-testharness,spike"
            ;;
        veri-testharness-pk)
            SIMULATOR_LABEL="verilator-pk"
            DV_SIMULATORS="veri-testharness-pk"
            ;;
        questa|questa-testharness)
            SIMULATOR_LABEL="questa-testharness"
            DV_SIMULATORS="questa-testharness,spike"
            ;;
        questa-uvm)
            SIMULATOR_LABEL="questa-uvm"
            DV_SIMULATORS="questa-uvm,spike"
            ;;
        vcs-testharness)
            SIMULATOR_LABEL="vcs-testharness"
            DV_SIMULATORS="vcs-testharness,spike"
            ;;
        vcs-uvm)
            SIMULATOR_LABEL="vcs-uvm"
            DV_SIMULATORS="vcs-uvm,spike"
            ;;
        *,*)
            SIMULATOR_LABEL="custom"
            DV_SIMULATORS="$sim"
            ;;
        *)
            SIMULATOR_LABEL="custom"
            DV_SIMULATORS="$sim"
            ;;
    esac
}

normalize_simulator "$SIMULATOR"

echo "[INFO] ----------------------------------------------------------------"
echo "[INFO] Verification Run Configuration"
echo "[INFO] Target:    $TARGET_CONFIG"
echo "[INFO] Test:      $TEST_SCRIPT"
echo "[INFO] Simulator: $SIMULATOR_LABEL ($DV_SIMULATORS)"
echo "[INFO] ----------------------------------------------------------------"

# --- Environment Preparation for Simulation ---
# Source the standard simulation setup from verif/sim
# This sets up python paths, checks variables, etc.
if [ -f "$PROJECT_ROOT/verif/sim/setup-env.sh" ]; then
    source "$PROJECT_ROOT/verif/sim/setup-env.sh"
else
    echo "[ERROR] verif/sim/setup-env.sh not found!"
    exit 1
fi

# --- Simulator Logic ---
export DV_SIMULATORS
if echo "$DV_SIMULATORS" | grep -q "spike" && [ -z "$SPIKE_TANDEM" ]; then
    export SPIKE_TANDEM=1
fi

if [[ "$SIMULATOR_LABEL" == "questa-"* ]]; then
    if ! command -v vsim >/dev/null 2>&1; then
        echo "[ERROR] Questa 'vsim' not found in PATH. Ensure QUESTASIM_HOME is set and PATH updated."
        exit 1
    fi
    if [ ! -d "$QUESTASIM_HOME" ]; then
        echo "[ERROR] QUESTASIM_HOME not found: $QUESTASIM_HOME"
        exit 1
    fi
    if [ "$SIMULATOR_LABEL" == "questa-uvm" ] && [ ! -d "$QUESTASIM_HOME/verilog_src/uvm-1.2" ]; then
        echo "[ERROR] Questa UVM library not found under $QUESTASIM_HOME/verilog_src/uvm-1.2"
        exit 1
    fi
    if [ -n "$CVA6_CI_REQUIRE_LICENSE" ]; then
        if [ -z "$LM_LICENSE_FILE" ] && [ -z "$SALT_LICENSE_SERVER" ] && [ -z "$MGLS_LICENSE_FILE" ]; then
            echo "[ERROR] No license env found. Set LM_LICENSE_FILE, SALT_LICENSE_SERVER, or MGLS_LICENSE_FILE."
            exit 1
        fi
    fi
fi

export DV_TARGET="$TARGET_CONFIG"

# --- Execution ---
TEST_SCRIPT_PATH="$PROJECT_ROOT/verif/regress/$TEST_SCRIPT"

if [ ! -f "$TEST_SCRIPT_PATH" ]; then
    echo "[ERROR] Test script not found: $TEST_SCRIPT_PATH"
    exit 1
fi

echo "[INFO] Launching Test Script..."
bash "$TEST_SCRIPT_PATH"

exit_code=$?
if [ $exit_code -eq 0 ]; then
    echo "[INFO] Verification PASSED."
else
    echo "[ERROR] Verification FAILED with code $exit_code."
fi

exit $exit_code
