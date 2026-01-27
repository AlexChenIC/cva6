#!/bin/bash
# Copyright 2024 OpenHW Group
# SPDX-License-Identifier: Apache-2.0
#
# Test Suite Dispatcher
# Location: ci/openhw/aws/run_test_suite.sh
#
# This script maps high-level test suite names (e.g., "arch", "benchmarks")
# to the specific regression scripts located in verif/regress/.
# It simplifies the CI configuration by encapsulating the mapping logic here.

set -e
set -o pipefail

# --- Arguments ---
SUITE_NAME=${1}
TARGET_CONFIG=${2:-cv32a65x}
SIMULATOR=${3:-verilator}

# --- Setup ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure run_verification exists
RUN_VERIF_SCRIPT="$SCRIPT_DIR/run_verification.sh"
if [ ! -f "$RUN_VERIF_SCRIPT" ]; then
    echo "[ERROR] run_verification.sh not found at $RUN_VERIF_SCRIPT"
    exit 1
fi

echo "[INFO] Suite Dispatcher: Requesting '$SUITE_NAME' on '$TARGET_CONFIG'"

# --- Suite Mapping Logic ---
# Maps a simple name to the actual script in verif/regress/
# Returns the script name to be passed to run_verification.sh

case "$SUITE_NAME" in
    "smoke")
        # Select smoke test based on bit-width (inferred from config name)
        if [[ "$TARGET_CONFIG" == *"cv64"* ]]; then
            TEST_SCRIPT="smoke-tests-cv64a6_imafdc_sv39.sh"
        else
            TEST_SCRIPT="smoke-tests-cv32a65x.sh"
        fi
        ;;
    
    "arch")
        # RISC-V Architecture Tests
        TEST_SCRIPT="dv-riscv-arch-test.sh"
        ;;
    
    "compliance")
        # Older Compliance Tests
        TEST_SCRIPT="dv-riscv-compliance.sh"
        ;;

    "benchmarks")
        # Standard benchmarks (Coremark/Dhrystone)
        # Note: Some configs might not support all benchmarks, defaulting to benchmark.sh wrapper
        TEST_SCRIPT="benchmark.sh"
        ;;
    
    "coremark")
        TEST_SCRIPT="coremark.sh"
        ;;

    "dhrystone")
        TEST_SCRIPT="dhrystone.sh"
        ;;

    "full")
        # Full regression suite based on bit-width
        if [[ "$TARGET_CONFIG" == *"cv64"* ]]; then
            TEST_SCRIPT="cv64a6_imafdc_tests.sh"
        else
            TEST_SCRIPT="cv32a6_tests.sh"
        fi
        ;;
    
    "pmp")
        TEST_SCRIPT="pmp_cv32a65x_tests.sh"
        ;;

    "mmu")
        TEST_SCRIPT="dv-riscv-mmu-sv32-test.sh"
        ;;

    *)
        echo "[ERROR] Unknown suite name: $SUITE_NAME"
        echo "Available suites: smoke, arch, compliance, benchmarks, coremark, dhrystone, full, pmp, mmu"
        exit 1
        ;;
esac

echo "[INFO] Mapped '$SUITE_NAME' -> '$TEST_SCRIPT'"

# --- Execute ---
# Delegate to the run_verification.sh script
bash "$RUN_VERIF_SCRIPT" "$TARGET_CONFIG" "$TEST_SCRIPT" "$SIMULATOR"
