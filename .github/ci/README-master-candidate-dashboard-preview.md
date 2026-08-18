# Fork-only master_candidate dashboard preview

This preview adds a branch-filtered page at:

```text
https://alexchenic.github.io/cva6/master_candidate/
```

It is intentionally limited to `AlexChenIC/cva6`. It is not an upstream
OpenHW deployment or an acceptance result.

## Data scope

The page reads completed Tier 1 and Tier 2 workflow runs whose head branch is
exactly:

```text
jchen/master-candidate-openhw-tier-ci
```

The branch filter is passed to the GitHub workflow-runs API before job data is
collected. Master and unrelated development runs are therefore excluded from
the page.

## Page layout

The page follows the existing master Tier dashboard layout while showing only
the master_candidate Tier 1 and Tier 2 workflows. A separate public reference
lane summarizes the Thales GitLab VCS/UVM dashboard without linking to private
pipelines or jobs.

The preview deployment contains the complete current fork site:

- `/` - existing fork dashboard
- `/tier/` - existing Tier dashboard
- `/master_candidate/` - branch-filtered master_candidate preview

GitHub Pages deployments replace the complete site artifact, so the preview
workflow preserves the published root and `/tier/` pages and adds the
master_candidate folder to the same deployment artifact.

## Deliberate limitations

- The preview does not persist master_candidate data to a separate branch.
- Thales results are public reference evidence, not a pass/fail gate for the
  GitHub Actions jobs.
- It does not make failed Tier jobs non-blocking or display them as green.
- The workflow is attached to a personal preview branch and is not intended
  for upstream submission in its current form.
