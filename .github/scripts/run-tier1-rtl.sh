#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
: "${TIER_TARGET:?Set TIER_TARGET to a declared Tier 1 configuration}"
export CONFIG_DIR="$PWD/ci-results/cook-config"
export DASHBOARD_JOB_TITLE="Verilator TestHarness Tier 1 (RTL-only)"
export DASHBOARD_JOB_DESCRIPTION="Basic instruction tests and Hello World; no reference-model comparison"
export DASHBOARD_JOB_CATEGORY="testlist"
export CI_JOB_ID="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$TIER_TARGET"
export CI_JOB_URL="https://github.com/${GITHUB_REPOSITORY:-local}/actions/runs/${GITHUB_RUN_ID:-local}"
export CI_JOB_STAGE="Tier 1 RTL-only"
python3 .github/scripts/cook_tier1.py --target "$TIER_TARGET"
