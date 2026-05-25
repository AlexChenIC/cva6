#!/usr/bin/env bash
# Intentional workflow validation helper for ci/demo-tier1-failure-detection only.

mkdir -p verif/sim/out_false_positive_pass_demo
cat > verif/sim/out_false_positive_pass_demo/iss_regr.log <<'EOF'
[PASSED]: intentional pass detector demo
1 PASSED, 0 FAILED
EOF

exit 0
