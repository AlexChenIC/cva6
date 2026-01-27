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
SIMULATOR=${3:-vcs}                    # Default simulator (though we focus on verilator)

# --- Setup ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/env_setup.sh"

echo "[INFO] ----------------------------------------------------------------"
echo "[INFO] Verification Run Configuration"
echo "[INFO] Target:    $TARGET_CONFIG"
echo "[INFO] Test:      $TEST_SCRIPT"
echo "[INFO] Simulator: $SIMULATOR"
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
# Here we can expand for DSim/Questa later
export DV_SIMULATORS="$SIMULATOR"
if [ "$SIMULATOR" == "verilator" ]; then
    # Usually we run with spike tandem for verilator
    export DV_SIMULATORS="veri-testharness,spike"
    export SPIKE_TANDEM=1
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
