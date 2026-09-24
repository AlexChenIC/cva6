#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
export CONFIG_DIR="$PWD/ci-results/cook-config"
export DASHBOARD_JOB_TITLE="Verilator TestHarness Hello World (RTL-only)"
export DASHBOARD_JOB_DESCRIPTION="Single-test and testlist smoke; no reference-model comparison"
export DASHBOARD_JOB_CATEGORY="testlist"
export CI_JOB_ID="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-hello-world"
export CI_JOB_URL="https://github.com/${GITHUB_REPOSITORY:-local}/actions/runs/${GITHUB_RUN_ID:-local}"
export CI_JOB_STAGE="TestHarness smoke"
python3 .github/scripts/prepare-cook-toolchains.py --output-dir "$CONFIG_DIR"
python3 .github/scripts/cook_testharness_smoke.py
