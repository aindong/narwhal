# Remediation plan contract

`narwhal plan REPORT.json --repo PATH` converts scan or comprehensive-audit JSON
into a deterministic, read-only source plan. The current contract version is
`1.0`; its machine-readable JSON Schema is
[`remediation-plan.schema.json`](../skills/seo-scan/references/remediation-plan.schema.json).

The planner never edits files. It inventories at most 5,000 non-symlink files,
skips dependency/build/VCS directories, and will not follow a symlink outside the
repository. It emits at most 1,000 deduplicated actions, severity-first, with an
explicit coverage warning if capped. MCP is stricter: callers pass a parsed report object, and `repo` must
be a relative descendant of the server working directory.

## Action semantics

Every non-passing finding becomes one action linked by stable `rule_id`. Older
reports without IDs receive deterministic compatibility IDs derived from their
category and title, with a coverage warning.

Safety values mean:

- `safely_automatable`: structural change with no editorial or owner-intent value.
- `review_required`: source edit whose wording, entity data, locale, index policy,
  or factual content must be reviewed.
- `manual_external`: hosting/CDN/TLS/response work, or an owner Narwhal could not
  safely identify.
- `deploy_verification`: repository artifact can be prepared locally, but its
  production behavior is only proven after deployment.

`likely_files` are ranked candidates, not authorization to edit. `exists` and
`confidence` distinguish observed owners from framework-convention suggestions.
`groups` identify findings best fixed in one shared template. `conflicts` stop
automation where canonical/index/crawler intent must be decided first.

## Verification templates

`verification` contains ordered human instructions and command templates, not
an executable script or an exact replay of the original invocation. For an audit
baseline, source actions may first suggest a local page scan to `page-after.json`.
That scan verifies page-level changes only: it must not be diffed against an audit
overall score or treated as deployed site verification. The final template runs
`narwhal audit` after deployment, then diffs that audit against the audit baseline.
Scan baselines retain the page-scan/diff workflow. Sitemap measurement-gap actions
remain manual verification tasks rather than source edits.
Markdown audit plans expose the shared audit rerun and settings reminder before
the action list; per-action JSON retains the complete ordered instructions.

Restore the original configuration, rendering, access settings and crawl/link/
sitemap limits before running an audit template. Reports do not record the full
invocation, so the planner does not invent those options or grant private-host
access to deployed targets. Matching report kinds avoids a known mismatch; it
does not certify equal execution coverage, settings, samples or environments.
The diff's existing incomparability checks remain in force.

## Compatibility

Additive fields may appear in a `1.x` plan. Consumers must ignore unknown fields.
A breaking rename, removal, or semantic change requires a new major
`schema_version`. Plans include source report and tool versions under
`provenance`, along with inventory coverage and warnings so agents can identify
partial evidence.
