#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -eo pipefail

# This wrapper only prepares environment/test sources. Cook owns compile/run.
export RESULTS_DIR="${RESULTS_DIR:-ci-results}"
mkdir -p "$RESULTS_DIR"
printf '1\n' > "$RESULTS_DIR/exit_code"
trap 'rc=$?; printf "%s\n" "$rc" > "$RESULTS_DIR/exit_code"; exit "$rc"' EXIT
: "${RISCV:?RISCV is required}"
source verif/sim/setup-env.sh
case "${TIER_INSTALL_SCRIPT:-}" in
  '') ;;
  install-riscv-tests) source verif/regress/install-riscv-tests.sh ;;
  *) echo 'Unsupported test source installer' >&2; exit 1 ;;
esac
export CONFIG_DIR="${COOK_CONFIG_DIR:-${RUNNER_TEMP:-/tmp}/cva6-cook-config}"
python3 .github/scripts/prepare-cook-toolchains.py --output-dir "$CONFIG_DIR"
python3 .github/scripts/cook_tier.py
