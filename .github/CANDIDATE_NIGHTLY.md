# Candidate Tier 2 nightly

This dispatcher belongs on the repository's default branch. It does not replace
the existing master Tier 2 schedule. It dispatches the same repository's
`openhw-cva6-ci-tier2.yml` on master_candidate at 23:17 UTC daily (07:17 China time).
GitHub schedules can be delayed; this is not an exact-time service.

Activation requires the Cook-native Tier workflow on the candidate branch, this
dispatcher merged into the default branch, Actions enabled, and repository variable
`CVA6_CANDIDATE_NIGHTLY_ENABLED=true`. Forks remain inactive unless explicitly enabled.
`CVA6_CANDIDATE_BRANCH` optionally selects a different same-repository candidate.
No PAT, external repository token, default branch write, or private CI access is needed.

Manual dispatch defaults to a read-only preflight. Select the workflow branch and
target_branch explicitly; set dry_run=false only to run the regression. Alternatively:

```bash
GH_TOKEN=... python3 .github/scripts/dispatch-candidate-tier2.py \
  --repo OWNER/cva6 --ref CANDIDATE_BRANCH
```

Add `--execute` to actually dispatch. The command verifies the branch and Cook-native
files, then checks same-branch, same-SHA workflow_dispatch runs on the UTC day. Any
existing attempt, including failure, prevents automatic retry loops. A legitimate
manual rerun can be requested directly through Tier 2 or GitHub's rerun control.
Do not blindly retry a failed POST: the server may have accepted it; inspect runs.

Concurrency serializes dispatcher runs. Branch movement during preflight is rejected;
a final API race between ref resolution and dispatch is still possible because the
Actions API dispatches a branch/tag, not an immutable commit. Always verify the actual
run headSha before treating it as evidence. The dispatcher is not a global exactly-once
guarantee against simultaneous manual dispatch outside this workflow.
