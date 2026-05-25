#!/usr/bin/env bash
# Intentional workflow validation helper for ci/demo-tier1-failure-detection only.

mkdir -p verif/sim/out_false_positive_demo
cat > verif/sim/out_false_positive_demo/iss_regr.log <<'EOF'
[FAILED]: intentional false-positive detector demo mismatch
1 PASSED, 1 FAILED
EOF

echo "ERROR return code: demo failure emitted while the script exits zero"
exit 0
