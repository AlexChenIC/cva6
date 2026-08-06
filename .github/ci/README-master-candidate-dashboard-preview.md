# Fork-only master_candidate dashboard preview

This preview adds a branch-filtered page at:

```text
https://alexchenic.github.io/cva6/master-candidate/
```

It is intentionally limited to `AlexChenIC/cva6`. It is not an upstream
OpenHW deployment or an acceptance result.

## Data scope

The page reads completed Tier 1 and Tier 2 workflow runs whose head branch is
exactly:

```text
jchen/master-candidate-tier-ci-master-adapter-v1
```

The branch filter is passed to the GitHub workflow-runs API before job data is
collected. Master and unrelated development runs are therefore excluded from
the page.

## Page layout

The page reuses the existing master Tier CI dashboard collector, parser,
generator, Jinja template, Bootstrap styling, and local OpenHW logo. The
master_candidate profile only changes labels and adds a visible branch/scope
notice.

The preview deployment contains the complete current fork site:

- `/` - existing fork dashboard
- `/tier/` - existing Tier dashboard
- `/master-candidate/` - branch-filtered master_candidate preview

GitHub Pages deployments replace the complete site artifact, so the preview
workflow regenerates all three paths instead of publishing only one folder.

## Deliberate limitations

- The preview does not persist master_candidate data to a separate branch.
- It does not automatically compare against the private Thales GitLab CI.
- It does not make known Tier 2 failures non-blocking or display them as green.
- The workflow is attached to a personal preview branch and is not intended
  for upstream submission in its current form.
