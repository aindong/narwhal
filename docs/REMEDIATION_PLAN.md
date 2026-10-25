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

For an explicitly saved CLI plan, `-o` checks the output file against the OS
identity of the baseline report captured while reading it. Direct, relative,
symlink and hard-link aliases of that baseline are refused with exit 2 before
truncation, including a baseline renamed after reading. Distinct regular artifact
paths retain normal replacement behavior; use a dedicated artifact path, since
this guard does not protect every other existing file. Encoding/write errors are
controlled, and named pipes are not used as outputs. The shared writer also
protects diff snapshots. It does not lock filesystem names or concurrent writers,
and separate artifact writes remain non-atomic. Stdout and the MCP planner remain
read-only with no saved baseline or file-output behavior.
CLI report paths use the same home expansion for loading and recorded
verification provenance, so a quoted `~/report.json` does not become a different
literal path beneath the current directory.

## Action semantics

Every non-passing finding becomes one action linked by stable `rule_id`. Older
reports without IDs receive deterministic compatibility IDs derived from their
category and title, with a coverage warning.

Action `evidence` stays a string in contract 1.0. Markdown shows up to 600
characters in a literal text fence beside the change, with an explicit truncation
notice; JSON keeps the full action evidence. Evidence is reported input, not
reverification or permission to edit. Empty evidence creates no receipt.

Synthesized sitemap validation actions retain the first five reported failing
HTTP status/URL witnesses and the total observation count. The original report
retains remaining witnesses; a null witness URL means unrecorded or unsupported
input shape, not an inferred address. Gated/no-response samples remain separate
verification-only actions. Source ownership and safety classifications do not
change.

Comprehensive-audit `crawl.links` observations produce manual `links` actions:
`technical.links.http.failures` for reported failing 4xx/5xx responses without
request errors (gated codes excluded; unsupported error shapes stay unverified), and `technical.links.coverage.unverified`
for uncertain responses, capped checks or unrecorded/inconsistent coverage.
New `crawl.links.unverified` records retain checked uncertain targets, including
gating, unsupported responses and request errors. The planner consumes a
count-consistent record set without double-counting no-response rows retained in
the legacy `broken` list. Absent legacy identities are not inferred. Errored
HTTP responses are unverified even if retained in that compatibility list. The
arrays may overlap; use the coverage counters rather than adding their lengths.
Missing/disabled checks and complete successful or zero-target checks do not
invent findings. Empty plans do not certify site-wide link health.

Witnesses retain up to five targets and three recorded source URLs per target,
with counts and nulls for unavailable fields; the original report retains the
rest. Raw request-error text is not copied. These actions assign no source files,
join no source-edit groups and authorize no automatic link removal. Confirm
HEAD/GET support, intended access/anchor behavior and actual ownership before an
edit. Malformed consumed record/counter shapes raise bounded input errors; valid
legacy observations remain reviewable without certifying their coverage.

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

Source-edit groups exclude manual/external and ownerless actions, including
verification-only tasks. Those actions remain in the plan's action list and
manual section; grouping cannot promote them into template edits or borrow
another action's source owner. Remaining groups coordinate related candidates,
not authorization to edit or proof that every member has the same owner.

Source candidates, including suggested files that do not exist yet, must be
literal relative paths contained in the repository at planning time. Candidates
with parent/current-directory segments, backslashes, drive/stream separators or
control characters are omitted, as are paths through any symlink component.
URL path names are not decoded or rewritten into presumed filesystem aliases;
hidden names such as `.well-known` retain their spelling. Omissions produce a
warning, while other safe shared/conventional owners remain review candidates.
Actions with no candidates are manual, including structural declarations that
would otherwise be safely automatable. Containment is a read-only planning
check, not a filesystem lock: verify paths and ownership again before any edit.

Framework detection treats package declarations as evidence only when
`package.json` is a supported JSON object and the relevant `dependencies` or
`devDependencies` entry is a non-empty string. Malformed/unreadable/oversized
manifests and unsupported sections or values produce bounded warnings without
echoing manifest contents. Valid sibling declarations and independent config
files still contribute; unavailable dependency evidence does not stop planning.
This is not package-manager validation, installed-package inspection or version
resolution. Confirm the framework and source ownership before applying edits.

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

Command strings use **POSIX shell** quoting, not universal terminal syntax;
adapt them for PowerShell/cmd. URLs and report paths are quoted as literal
arguments, including dollar signs, command-substitution syntax and apostrophes.
An explicit `--` separates options from data so a leading dash cannot become an
option. Replace placeholders and insert original CLI options **before** `--`.
Instruction text is not shell code, and the planner never executes a template.

For in-memory/Python or parsed-object MCP inputs, no baseline file is created.
Every diff-producing action first asks the caller to preserve the original report
JSON, keeping all fields, at a fresh `before.json` before edits/reruns. If using
an existing saved report, update the diff baseline and choose distinct fresh
verification output paths; never substitute a new scan or overwrite an
existing file. Markdown surfaces the same prerequisite outside executable code.
File-backed plans do not get this memory-only instruction. Manual measurement
checks and empty plans do not acquire an unrelated audit/diff workflow. The shared
audit section appears only when an action actually requests an audit rerun;
manual hosting/source remediation can still require verification after deployment.

Known baseline basename collisions select alternate output names: `after.json`
uses `after-2.json`, and an audit baseline named `page-after.json` uses
`page-after-2.json` for its local page check. Commands, diff targets and Markdown
use those same selections. Basename comparison is conservatively case-insensitive
and recognizes either path separator without filesystem reads. This is not
filesystem identity verification: choose fresh regular output paths and check
symlink/hardlink aliases before running a template. Do not overwrite the baseline.

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
