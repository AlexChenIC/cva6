# Candidate dashboard integration

The default-branch publisher builds the existing master page at `/` and a separate
Cook-native page at `/master_candidate/`. It does not replace master with the
candidate checkout, execute candidate code or query private Thales GitLab APIs.

## Preview and activation

The publisher runs after Tier jobs complete, every four hours at minute 17, and on
manual dispatch. Scheduled/workflow_run execution uses the default branch's workflow.
Manual previews from development branches only upload artifacts: deployment and data
persistence require the repository default branch. The `publish` input defaults to
false, and previews with a candidate_branch filter can never be published.

Merge the producer and publisher separately. Before enabling production, confirm
GitHub Pages uses Actions, its environment allows the default branch, candidate Tier
workflows are present, and maintainers accept the retention/filter policy. Nothing
starts scheduling merely because this file exists on a non-default branch.

```bash
gh workflow run openhw-cva6-tier-dashboard.yml --repo OWNER/cva6 \
  --ref DASHBOARD_DEVELOPMENT_BRANCH -f candidate_branch=COOK_CANDIDATE_BRANCH -f publish=false
```

Download `cva6-tier-dashboard-site` from that run to inspect both pages. Data is read
from GitHub's Actions API and public Thales HTML, then rendered as static HTML.
An already-open browser tab does not stream updates. Reload to obtain the latest
published snapshot. Schedule latency, API availability and Pages deployment add delay.

## Evidence and boundaries

- Candidate page tracks only Tier 1/2, not legacy ci.yml. Master keeps its existing lanes.
- Branch/base filters prevent similarly named master/candidate workflows mixing.
- Run attempts are re-read; a rerun replaces the previous outcome for the same ID.
- Job matrix/trends describe observed CI jobs, not code/functional coverage or total ISA tests.
- An empty latest matrix is not silently replaced by an older green matrix.
- GitHub checks and artifact completeness are displayed separately. Missing/expired
  artifacts do not turn a failed job green and are not invented as successful test counts.
- Latest-run artifacts are bounded (32 MiB ZIP, 1 MiB JSON), read without extraction,
  and checked for schema, repo, run, attempt, target, suite, source and count consistency.
- Actual tested SHA can be a PR merge commit. It is kept separately from the event head.
- Thales is only the latest publicly published pipeline summary, potentially on another
  branch/SHA. No testlist matrix, extra trend, private pipeline button or synthetic
  coverage comparison is shown. Parser failure is visible and can retain old reference
  data with a warning. HTML format changes may require updating this bounded parser.
- Execution Environment is below GitHub Run History. No fresh badges are added to cards.
- GitHub API/Thales collection is periodic, not a webhook subscription to Thales.

The candidate history is a bounded recent snapshot (up to 20 runs, search budget 500
runs per workflow), not an archival database. Very busy repositories may require a
larger collection budget. Artifact expiry and independent source ages remain visible.

## Privileges

Build jobs have contents/actions read, never execute downloaded artifact content,
and do not persist checkout credentials. Only separate default-branch deploy and
data persistence jobs have Pages or contents write. PR-controlled text is escaped
in HTML and JavaScript contexts. This does not cryptographically attest a successful
test: the result format and GitHub provenance make evidence inspectable, not immune
to intentionally fabricated test outputs in a malicious workflow.
