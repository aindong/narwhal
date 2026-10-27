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
input shape, not an inferred address. Sitemap and crawl probes share response
classification: supported error-free 2xx or failing 4xx/5xx (gated codes excluded).
Unverified sitemap sample actions retain the first five recorded target/status witnesses and the total. Null fields mean unrecorded or unsupported field types; witnesses are not rechecked and do not establish dead URLs.

Unsupported statuses, non-string falsey error fields and request errors stay
unverified. Gated/unsupported/no-response samples remain separate verification-only
actions; retained compatibility `broken_sample` rows alone do not prove a source
defect. Their length is not a count of confirmed HTTP failures. New sitemap
JSON also records `sample_response_coverage` for selected targets; supplied
counters do not override classification of the raw status/error observations.
Supported list records keep their existing source ownership and safety classes.
Explicit non-list `sample` or `broken_sample` containers require manual sitemap
validation verification. They are not expanded into individual probe records
and cannot alone justify source edits. Valid records in a companion list retain
their independent classification. Missing legacy keys and empty lists keep their
existing behavior; unsupported container values are not echoed into evidence.

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
Markdown shows each action's normalized plan scope and occurrence count beside
its rule. Counts retain the maximum supplied value or default to one; they are
not matched or distinct affected-page totals. These labels do not change JSON,
source ownership, safety classes or verification requirements.
Schema verification labels also retain explicit external scope instead of
describing it as unrecorded.
For audit homepage findings, page-route candidates follow the recorded
`homepage.final_url`, then `homepage.url`, falling back to the audit target for
legacy reports without those labels. The plan target and final audit rerun keep
the original site input. Discovery files and recurring-rule URL witnesses keep
their existing scope. A recorded destination is a route hint, not proof that the
repository owns it; malformed page labels still withhold structural automation.
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
Manifest bytes must decode as UTF-8 without replacement. Undecodable bytes
withhold all dependency evidence from that manifest, even when replacement
decoding could produce a JSON object. Valid UTF-8 text containing a literal
replacement character remains ordinary string data.
The manifest open is nonblocking where supported, and its descriptor must be a
regular file matching the admitted identity before any bytes are read. A path
replaced by a FIFO stays unverified instead of blocking framework detection.
This is not package-manager validation, installed-package inspection or version
resolution. Confirm the framework and source ownership before applying edits.

## Verification templates

`verification` contains ordered human instructions and command templates, not
an executable script or an exact replay of the original invocation. For an audit
baseline, source actions may first suggest a local page scan to `page-after.json`.
That scan verifies page-level changes only: it must not be diffed against an audit
overall score or treated as deployed site verification. The final template runs
`narwhal audit` after deployment, then diffs that audit against the audit baseline.
Scan baselines retain the page-scan/diff workflow. Diff `old_url`/`url` preserve
earlier/later target labels; review differing labels and confirm the intended
local-preview mapping. Labels alone neither prove identity nor block comparisons. Generated diff commands use
`--fail-on-regression --require-comparable`: measured regressions exit 1;
known incomparable or unknown legacy coverage exits 2. Comparability covers only
recorded checks; exit 0 does not certify unrecorded settings or site-wide coverage.
Review the comparison status and evidence before accepting a fix. Sitemap measurement-gap actions
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

Repeated rule IDs yield one action. The representative is the complete
worst-severity observation; equal-severity ties use sorted-key JSON lexical
order. Evidence, title, recommendation and confidence come from that same
observation. Occurrences use the maximum recorded count (not a sum or matched
instances), and any recorded site scope is retained. Audit homepage and
recurring observations use this same selection. Repeated actions include an
`observation_selection` receipt with the selection basis, normalized observation
count and occurrence-count policy. The count includes normalized findings/rollups,
not distinct pages or matched instances. Markdown discloses the reduction and
points back to the original report; singleton actions omit this receipt.

Repository coverage includes `file_inventory_walk_errors`: traversal failures
counted by `os.walk`, with up to five failed-directory witnesses in warnings.
A file inventory is capped only after an additional eligible file is observed
beyond the returned budget; merely reaching the budget is not an omission.
The cap bounds returned inventory entries; determining truncation can inspect
one additional eligible path's metadata without reading its contents.
Ignored files and empty directories do not count as omitted source. Later
traversal errors remain recorded even when the returned file count matches the
budget. Known traversal errors or a capped file inventory add
`incomplete_repository_inventory` to viewport automation blockers. Available
source candidates remain reviewable; zero recorded traversal errors does not
certify all source contents or ignored directories.

Existing route-convention files take priority for content, headings and image
alt changes across supported frameworks, and for plain-HTML head changes.
Template-framework head ordering and site-wide discovery candidates retain their
existing policy. Missing routes do not displace existing fallbacks; route paths
still pass the same containment/symlink guards. Plain-HTML URLs ending in `.html`/`.htm` also suggest the literal path, preserving
its case and encoded spelling; query/fragment components are excluded. Trailing
slashes retain directory-style conventions. Existing fallback patterns remain.
A route match is a convention, not proven source ownership; inspect the file
before editing.

Related source-action groups are review coordination, not verified edit owners.
For compatibility, `likely_shared_files` remains the union of existing candidate
paths. `candidate_file_basis` discloses that meaning; it is not an intersection
or proof of shared ownership. `candidate_file_overlaps` lists existing paths
named by at least two distinct member rule IDs, with those IDs. Missing proposed
files, duplicate entries within one action, and excluded manual actions do not
create existing-candidate overlap evidence. Markdown labels the union and
multiple-action candidates explicitly; absent legacy overlap data is unrecorded.

Markdown shows up to 600 characters of each selected `source_recommendation`
as reported guidance requiring review, using a literal text block separate from
planner-authored change and verification instructions. Supplied command-looking
text remains data. A truncation note points to the full unchanged JSON field;
empty or absent legacy fields produce no recommendation section. Rules with
contextual editorial/verification overrides keep their original recommendation
in JSON only; Markdown directs readers to the calibrated guidance instead of
reintroducing unsupported legacy advice. Evidence
previews retain the same bound and literal-block behavior.

Report URL labels, action titles, rule IDs and coverage warnings use literal
single-line Markdown previews, with whitespace collapsed for display. Imported
markup cannot become extra headings, links or HTML through those labels. The
original strings remain unchanged in plan JSON; this does not authenticate them
or make their contents execution instructions.

Native empty/generic anchor-text rules map to content-source review, with
route-aware candidates and no automatic-edit eligibility. New scanner evidence
retains up to five observed href/label pairs and the total source-anchor count;
duplicate hrefs remain separate observations. Destinations are not probed or
certified reachable. Labels still use visible text, image-alt and title fallbacks.
Generic phrases require review of surrounding context and destination purpose,
not keyword insertion or a promised ranking gain. Legacy reports retain their
recorded evidence; missing witnesses are not reconstructed. Witness JSON escapes
backticks reversibly for literal Markdown presentation.

Malformed HTTP href findings also retain up to five original href witnesses
and their occurrence total. Native `technical.links.invalid.url` and legacy
`technical.malformed.http.link.urls` map to content-source review. Correct only
confirmed syntax after establishing the intended destination; do not guess a
replacement URL or drop parameters. Source syntax rejection is not a failed
HTTP request or proof of a dead destination. Unassessed-base omissions remain
separate, and missing legacy witnesses are not reconstructed. The shared source
anchor formatter conservatively omits href values with credential-like `@` or
percent/full-width marker spellings, including markers outside the authority:
`href: null` and `href_omitted: credential_like_marker` disclose the omission.
Counts remain intact; this is not a general secret detector.

Planner-generated link-check and sitemap-sample witnesses use the same marker
rule: a matching target label becomes `url: null` with
`url_omitted: credential_like_marker`. In bounded link source lists, matching
labels become null in their original positions; `source_url_omissions` records
each one-based position and reason. `source_count` still counts all recorded
string source labels before the cap and omission. Omissions do not promote later
targets/sources into the retained slots, drop response observations or change
failure/uncertainty classification. Safe labels retain their literal spelling.
This applies to these generated witnesses, not arbitrary supplied finding text
or recommendations, and does not sanitize the original report.

New crawl/audit recurring JSON entries retain recorded rule IDs instead of
reconstructing identity from display titles. Distinct recorded rules with the
same category/severity/title remain separate entries with their own occurrence
counts. The runtime title-based `recurring` Counter is unchanged; internal
`recurring_rule_counts` supports serialization and is not emitted in JSON.
Disagreement between those snapshots or invalid rule counts fails JSON rendering
rather than attaching stale IDs. Regenerate the crawl before rendering changed
rollups. Legacy Counter-only inputs retain their title/count rendering without
invented IDs. Known legacy HTTP X-Robots-Tag title identities map to external
header ownership. Native/legacy header guidance preserves intentional restrictions,
requires page/crawler-scope and owner review, and calls for deployed-header
verification rather than HTML-meta edits. HTML robots-meta findings retain their
source-review behavior.

For these header actions, audit plans append up to five matching crawl target
labels and the total number of supported matching receipt rows. Matching uses
the recorded unprefixed directive, supported receipt version/basis, positive
header-field count and non-failed page observations. Named-crawler-only,
unsupported or missing receipts do not name targets; recurring counts alone
cannot establish affected URLs. Existing selected finding evidence is retained.
Labels are literal crawl labels, not verified response destinations or distinct
pages, and are not re-fetched. Missing/non-string labels and credential-like
marker spellings are explicitly omitted without dropping their receipt count.
Ownership remains manual/external, with no HTML edit candidates or edit groups.

## Compatibility

Additive fields may appear in a `1.x` plan. Consumers must ignore unknown fields.
A breaking rename, removal, or semantic change requires a new major
`schema_version`. Plans include source report and tool versions under
`provenance`, along with inventory coverage and warnings so agents can identify
partial evidence.
