# Contributing to Narwhal

Thanks for your interest in improving Narwhal — the local-first SEO & GEO/LLMO
scanning toolkit. This guide covers how to get set up and the conventions that
keep the project consistent.

## Getting started

```bash
git clone https://github.com/aindong/narwhal
cd narwhal

# Optional extras (the tools auto-detect them; nothing here is required)
pip install -r skills/seo-scan/requirements.txt

# Run the tests
python -m unittest discover -s skills/seo-scan/tests -v

# Try a scan
python skills/seo-scan/scripts/scan.py https://example.com
```

After installing a built wheel in your test environment, run the installed CLI
action-cycle smoke check from the repository root:

```bash
python skills/seo-scan/tests/action_cycle_smoke.py
```

Packaging CI runs this separately from the offline unit suite. It serves a
disposable loopback fixture, verifies the read-only plan and likely source owner,
applies one explicit fixture edit, and executes the plan's generated scan/diff
commands as argument lists, substituting the local preview and restoring the
baseline configuration. Paths contain spaces to exercise template quoting;
verification captures a separate generated local baseline before the edit,
preserves both baselines, and resolves only that issue in the paired local diff.
The original-target template is also exercised against this intentional local
fixture; it does not establish deployment proof.
Before scanning, isolated installed schema calls must preserve distinct offers
and reject duplicate JSON keys without emitting either raw or wrapped artifacts.
The fixture uses a non-default 6 MB HTML budget and requires all generated
page scans to retain it.
Malformed scope, HTTP-status and response-completeness fixtures must withhold automation
while keeping planning read-only.
Unsupported recorded target/page URL labels also withhold structural candidates;
this offline syntax policy does not establish reachability or source ownership.
Installed CLI/MCP smoke cases cover empty/file/bad-port labels, a malformed final
label and failed page evidence with a claimed site scope. They retain source
owners and report bytes; the native empty-string final-URL fallback stays eligible.
Contradictory `not_selected` receipts must also block strict CLI proof and leave
MCP comparisons unverified.
Contradictory root/settings actual-rendering flags must also withhold automation
and improvement claims; requested rendering and actual fallback remain distinct.
Explicitly failed or malformed acquisition evidence must withhold score deltas
and fix claims in both CLI and MCP comparisons, even with a claimed completed scope.
Reversing the reports must fail the regression gate. This is local,
page-level workflow evidence, not real-site SEO gains or deployment proof.
A subsequent HTTP 206 preview must leave the diff incomparable (gate exit 2),
with no score delta/resolved fixes and a read-only, manual verification plan.
The same fixture then audits a healthy homepage and an inner page missing its
title. Its recurring rule must carry the inner URL witness and plan only that
page's inventoried source. An explicit title edit removes the recurring finding
and improves the comparable overall audit score. Audit diff finding lists still
describe homepage changes; inner resolution is checked directly in crawl rows.
Explicitly malformed crawl page lists and contradictory recorded page counts must
block score/fix claims in installed CLI and MCP diffs, including regression-only gates.
The separate crawl-rule diff must report the missing-title rule as no longer
observed in the matching sample, through both CLI and optional MCP.
Planner witness checks also require native finding text to survive appended
page/header URL notes. A missing-H1 fixture keeps its observed HTML owner while
generic HTTP `noindex`/`nofollow` actions remain manual hosting work with
deployment-required verification. Named-crawler-only and absent headers cannot
invent generic restrictions. Planning preserves source and baseline bytes.
Per-rule Markdown context and exported HTML must retain the plan's scope and
occurrence count. Counts use the maximum supplied value or default to one; they
do not establish totals of distinct affected pages.
Copies of native sitemap receipts with unsupported sample containers must request
manual verification without inventing probe rows or source-edit actions. The
uncorrupted native control and all source/report bytes must remain unchanged.
Combined malformed counts, counters and containers must retain each verification
reason and guidance through same-rule selection.
An explicitly supplied competing finding must retain its selected severity and
observation while recorded verification guidance takes precedence over repair advice.
The fixture also reviews a schema action, generates WebSite JSON-LD from its real
name/URL, and curates the MCP starter's inapplicable search-action placeholder.
It applies that inspected artifact, runs the generated schema-only local scan/diff
templates with fresh snapshots, requires one observed WebSite node and exactly the
schema non-observation resolved, and rejects the reverse regression. Prior reports
and unrelated source bytes remain unchanged. This is supported-extractor/local
workflow evidence, not full schema validation, eligibility or ranking proof.
Replanning that verified schema report must leave no actions, groups or conflicts;
successful observations are not remaining work, and the input report stays intact.
An actual JSON-LD parse error is also rescanned, then paired with stale saved
absence advice. Planning must withhold that absence action, retain the syntax
repair for source review and leave extraction verification ownerless. Even
identical uncertain reports must fail comparability in CLI and MCP diffs.
Explicit unsupported structured-data containers and review flags also withhold
absence advice and score/fix claims. Missing legacy fields and unselected schema
checks retain their handling; independently observed property repairs stay reviewable.
Known truncated or ranged source coverage also withholds schema-type absence
advice, even when the retained prefix parsed without extractor errors. Native
schema and standalone merchant checks retain observed node/property findings.
The installed fixture places existing WebSite markup beyond a real HTML byte
cap, requires a manual verification plan and then observes that markup by raising
only the budget. That pair remains incomparable and cannot count as a source fix.
Null and future llms.txt receipts in saved audits likewise withhold stale
missing-file repairs, keep verification ownerless and fail CLI/MCP comparability.
The positive llms.txt fixture removes the root file, observes HTTP 404, reviews
the deployment-required source candidate and generates a starter with the CLI.
It checks both entry-point titles against source and both URL destinations before
curating the artifact, then explicitly applies it to the disposable site.
Matching GEO-only scans must observe a root text candidate, resolve only the
missing-file finding and reject the reverse regression. Replanning leaves no
llms.txt work, and source/report bytes stay intact except the intended artifact.
This verifies a local endpoint only; production root verification remains pending
deployment. It does not prove full proposal validity, engine adoption or ranking gains.
Sitemap source-problem summaries use nonnegative integer counts. Zero-filled
summaries do not imply defects; malformed counts require manual verification.
Independent positive counts and recorded failing HTTP samples retain their
source-review actions even when other counters are unverified.
Explicit malformed notes/counters and contradictory sitemap attempt/outcome totals
must remain manual verification gaps even without error prose. Plausible partial
legacy receipts remain unknown; missing fields alone do not establish failures.
The inner page also lacks a viewport declaration. Its native recurring finding
must become an automation candidate only for that page's observed source.
Temporarily removing the fixture source must withhold automation and leave an
ownerless manual action despite the healthy homepage. After restoring the source,
a separate explicit viewport edit must remove that recurring rule in a comparable
audit diff; the earlier title edit alone must leave it present.
With the optional MCP SDK installed, add `--mcp` to exercise the installed stdio
server for schema field admission, planning and comparisons. All three SDK CI
jobs run this mode and require MCP diff output to match the CLI. Local scans use
the CLI's explicit `--allow-private`; the MCP scan tool requires public URLs.
One persistent installed session must reject ambiguous schema/diff JSON and
invalid planner paths/reports, then accept a corrected request after each error.
Diagnostics remain bounded, invalid repository paths do not disclose the server
workspace, and corrected plans retain the native page's observed source owner.

The installed `service_opt_in_smoke.py` check runs isolated from repository
imports, with account collectors mocked and sockets blocked. It verifies that
configured credentials do not enable default audit/brief service calls and
that explicit brief CLI/Python/MCP opt-in remains available; it does not test
live OAuth/API availability. Packaging and all MCP SDK CI jobs run this check.

Plan contract tests compare generated plans with the checked-in remediation-plan
schema. Full JSON Schema validation runs in all MCP SDK CI environments using
their existing dependencies; stdlib-only runs retain field/enum contract checks.

## Project layout

```
narwhal/
├── .claude-plugin/          # plugin.json + marketplace.json (plugin name: narwhal)
├── commands/narwhal.md      # /narwhal <action> <site> — dispatch + audit orchestration
├── agents/                  # 10 specialist subagents (narwhal-*.md) for the deep audit
└── skills/seo-scan/
    ├── SKILL.md             # auto-triggering Claude Code skill
    ├── scripts/
    │   ├── scan.py          # single-page orchestrator
    │   ├── compare.py       # side-by-side competitor gap analysis
    │   ├── crawl_site.py    # polite site crawl + rollup (links, dupes)
    │   ├── validate_sitemap.py
    │   ├── generate_schema.py / generate_llms.py
    │   ├── audit.py         # comprehensive page + crawl + sitemap
    │   ├── diff_scan.py     # diff two JSON reports (regression tracking)
    │   ├── render_report.py # `narwhal render` — Markdown -> branded HTML/PDF report
    │   ├── crux.py          # `narwhal vitals` — real Core Web Vitals via CrUX (opt-in)
    │   ├── psi.py           # `narwhal vitals --lab` — PageSpeed Insights (Lighthouse) lab data
    │   ├── mcp_server.py    # `narwhal mcp` — MCP server exposing the auditors
    │   ├── cli.py           # unified `narwhal` entrypoint (scan/crawl/…)
    │   ├── audit_*.py       # one file per auditor (technical/content/schema/geo)
    │   └── lib/             # http, htmlx, report, robots, links, sitemap,
    │                        #   simhash, text, content_quality, config, env
    ├── references/          # deep-dive guidance per auditor
    └── tests/               # offline unittest suite (no network, no deps)
```

See [docs/STATUS.md](docs/STATUS.md) for the architecture (deterministic scripts +
multi-agent orchestration) and the release process.

## Design principles (please preserve these)

1. **Local-first.** No external services on the default path. APIs are opt-in and
   clearly gated behind config/credentials.
2. **Zero required dependencies.** Everything must run on the Python standard
   library. Optional libs (`requests`, `bs4`/`lxml`, `trafilatura`, `playwright`)
   are auto-detected — never a hard import at module top level of a code path that
   must work without them.
3. **SSRF-safe.** All fetching goes through `lib/http.py`, which blocks
   private/loopback hosts unless `--allow-private` is set. Don't bypass it.
4. **Fix-first, honest output.** Findings lead with the action to take. Never
   fabricate a metric the tool can't measure (e.g. real Core Web Vitals field
   data) — say what needs an external source instead.

## Adding a new check

- Put it in the relevant `audit_*.py` and emit findings via `report.add(category,
  severity, title, detail, recommendation, evidence=…)`.
- Severities: `critical`, `high`, `medium`, `low`, `good`. Use `good` for passing
  checks so users see what's already right.
- Add passing and failing assertions in the relevant area module under `tests/`.
- When report structure changes intentionally, regenerate and review the full
  Markdown/JSON/HTML snapshots with:
  `python skills/seo-scan/tests/update_golden_reports.py`.
- If the check encodes non-obvious reasoning/thresholds, document the *why* in the
  matching `references/*.md`.

## Adding a new auditor

Create `audit_<name>.py` exposing `audit(doc, resp, report, ctx)`, register it in
`AUDITORS` in `scan.py`, and add a `references/<name>.md`.

## Mutation testing

After normal tests pass, mutation-test changed behavior before review and merge.
Mutation testing deliberately changes production code and checks whether tests
detect it. It exposes weak assertions; it does not prove all tests are correct.
Tools are development-only: use Python 3.12 on Linux or macOS. Scanner runtime
dependencies and Python 3.8 support are unchanged.

```bash
python3.12 -m venv .venv-mutation
.venv-mutation/bin/python -m pip install -r requirements-mutation.txt
.venv-mutation/bin/python scripts/mutation_test.py
```

Add `--report results.json` to retain selected mutant names and their raw exit
codes, targets, Mutmut version and killed/total summary. `status: passed` requires
every selected result to be an explicit pytest failure (exit 1); survivors,
errors and incomplete results remain failures. A requested report starts as
`not_completed`, so a failed baseline cannot leave a stale passing receipt.
The report is overwritten on each parsed invocation; its parent directory must
exist. Paths or filesystem links referring to the selected mutation configuration
are rejected before writing. Without `--report`, console output and gate behavior
are unchanged.

CI retains the three mandatory gate receipts in the `mutation-results` artifact,
including available receipts when a gate fails. A later skipped gate has no
receipt. Check the workflow's commit and conclusion alongside the artifact;
receipts describe selected mutations, not proof that all behavior is correct.
Artifacts follow the repository's retention settings.

The default gate covers `lib.links.http_check_state`, `lib.links.is_broken`,
`lib.urlpaths.remove_dot_segments` and both integer validators in `lib.budgets`:
the complete sitemap response-state module exercises the report/planner matrix
and MCP handoff, and existing direct link tests cover status 0 and all gated
codes. Relative-path tests cover terminal dot segments, repeated separators and
the empty-path root fallback. Transport preflight tests reject invalid byte
budgets before DNS/browser/transport access while preserving zero HTML retention
and valid range prefixes. The combined scope kills 69/69 mutants (34 for the
classifiers, 23 for the path helper and 12 for the budget validators).
Initially, relative-path tests killed
19/23 helper mutants; four terminal-segment/root-fallback mutations survived
until boundary assertions were added. The response-state tests alone
missed two status-0 mutations in `is_broken`; including its existing direct
assertions kills both without changing scanner behavior.

Initially, 21 of 27 response-classifier mutants were killed.
Six survived because the matrix omitted HTTP 300, 400 and 600; boundary
assertions now kill all 27 without changing production behavior.

For behavior changes, select affected files and relevant offline tests in a
focused TOML profile. Pass it with `--config PATH` rather than replacing
[the default CI configuration](scripts/mutation/pyproject.toml). Without that
option, the existing default profile and targets remain unchanged. For example:

```bash
.venv-mutation/bin/python scripts/mutation_test.py 'lib.links.x_http_check_state__mutmut_*'
```

The committed [planner profile](scripts/mutation/planner.toml) reproduces source
owner checks across the supported frameworks and related-action group boundaries:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/planner.toml \
  'plan.x__route_candidates__mutmut_*' 'plan.x_likely_files__mutmut_*'
```

With the same profile, target `plan.x__groups__mutmut_*` to check manual-action
exclusion, existing-candidate unions and per-file overlap evidence.
The profile also exercises successful-finding exclusion and repeated-observation
counts, scope and selection receipts. Successful siblings/rollups must neither
create remediation nor inflate a remaining finding's count or selection history.
Crawl-only work must also survive a preceding successful rollup or an absence
rollup skipped for schema uncertainty. Ordering controls retain the independent
action's evidence/counts and keep verification separate from schema repair advice.
Schema extraction guards are exercised through `test_page_schema_review.py`,
including stale absence advice, independent syntax/property repairs and separate
homepage/crawl uncertainty. These guards must survive the planner handoff.
Existing image-weight, llms.txt, sitemap discovery/parsing and merchant-comparison
tests also run in this profile so their verification-only evidence reaches planning.
Target `plan.x_normalize_report__mutmut_*` to exercise these normalization handoffs;
report its fresh results and survivors separately from the default CI gate.
Planner context tests also retain numeric zero scores, scan/audit provenance and
literal legacy target fallbacks in matching-kind verification commands. Malformed
tool-version metadata must fail before inventory or output writes.
The selected score follows report kind even when additive fields from another
kind are present. Missing/null scores stay unknown, and missing audit overall
scores must not borrow homepage measurements. The installed action cycle checks
native reports alongside deliberately altered saved copies through CLI/MCP;
an invalid page score cannot be hidden by an extra overall score.

Profile paths are relative to your invoking directory; paths inside the profile
refer to the temporary staging layout described below. Selecting a profile does
not infer function targets: pass their quoted patterns explicitly. The planner
profile is an optional diagnostic, not a default CI gate. Record fresh killed/total
counts and unresolved outcomes with each PR; past counts do not score new source
or tests. Unresolved results keep the gate nonzero. Its schema-file
test is omitted because references are not staged; full suites/MCP CI retain it.

The [llms.txt profile](scripts/mutation/llms.toml) checks the shared saved-receipt
boundary and requested-GEO scope handling, with planner and diff controls:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/llms.toml \
  'lib.llms_resource.x_problem__mutmut_*' 'lib.report.x_recorded_llms_problem__mutmut_*'
```

The same profile includes generator metadata, budgets, redirects and literal
artifact checks. Target `generate_llms.x_build__mutmut_*` and
`generate_llms.x_render_llms_txt__mutmut_*` to diagnose those functions.

The [extraction profile](scripts/mutation/extraction.toml) checks structured-data
receipt interpretation, including malformed containers/flags, legacy coverage,
selected auditor scope and planner/diff consumers:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/extraction.toml \
  'lib.report.x_recorded_schema_extraction_problem__mutmut_*'
```

For native schema/merchant absence checks, also select `audit_schema.x_audit__mutmut_*`,
`audit_schema.x__cross_checks__mutmut_*` and `lib.ecommerce.x_audit__mutmut_*`.

The optional [merchant profile](scripts/mutation/merchant.toml) checks known
Product/Offer comparison skips, selected scope, read-only planning, crawl/audit
propagation and real price-correction controls:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/merchant.toml \
  'lib.report.x_recorded_merchant_comparison_problem__mutmut_*' \
  'crawl_site.x_crawl__mutmut_*' 'crawl_site.x_merchant_comparison_note__mutmut_*' \
  'crawl_site.x_render_markdown__mutmut_*' 'audit.x__schema_score_note__mutmut_*' \
  'diff_scan.x__comparison__mutmut_*' 'plan.x_normalize_report__mutmut_*'
```

Mutmut does not generate mutants for the dataclass report methods; the focused
tests and installed cycle check their Markdown/HTML qualifiers directly.
This broad diagnostic is separate from the mandatory gates. Report its completed
killed/total counts and survivors; do not count incomplete runs as passes.
The installed action-cycle smoke also requires ambiguous or ignored-warning
reports to yield manual verification and strict incomparable diffs, while a real
consensus price correction resolves the mismatch and its reverse fails regression.
For merchant observation/price-method handoffs, use the same profile with
`lib.report.x_recorded_merchant_comparison_basis__mutmut_*`,
`diff_scan.x__comparison__mutmut_*`, `diff_scan.x__crawl_settings__mutmut_*` and
`crawl_site.x_crawl__mutmut_*`. Coverage includes removed observations,
exact-vs-range changes, native crawl receipts, unsupported saved receipts and
positive exact/range/missing-price repairs. Known current crawl evidence paired
with unrecorded legacy evidence cannot certify unchanged observation coverage;
two legacy reports retain their existing handling without inferring that coverage.
Known price checks becoming unrecorded withhold claims; adding a genuinely missing
schema price remains eligible. Duplicate sampled URLs retain missing receipts and
methods alongside known evidence instead of discarding those observations.

The optional [output profile](scripts/mutation/output.toml) exercises snapshot
preservation and nonblocking regular-file output through diff/planner tests:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/output.toml \
  'lib.report_output.x_write_output__mutmut_*'
```

POSIX FIFO checks allow up to 30 seconds for interpreter/module startup, then
keep the five-second deadline for CLI execution and output handling. Both phases
terminate and reap a timed-out child. Controlled startup delays and a genuinely
blocking FIFO writer verify that slow imports cannot consume the I/O budget and
that blocking output still fails. These tests do not replace installed CLI checks.
The helper uses Python's validated bytecode cache so large generated Mutmut
modules do not recompile on every FIFO check. Cache-reuse and checked-hash source
invalidation controls run alongside the unchanged startup/I/O deadline checks.
Regular-file controls also run in the parent process so Mutmut records writer
coverage before selecting the subprocess rejection cases. The profile includes
empty/binary output preservation and descriptor cleanup when stream setup fails.

The [scope profile](scripts/mutation/scope.toml) gates shared execution receipts
and their report/diff/planner consumers. The existing mutation CI job runs it
alongside the default corpus:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/scope.toml \
  'lib.report.x_recorded_scan_scope__mutmut_*'
```

The same CI job requires every crawl-count validator mutant to be killed using
the [diff profile](scripts/mutation/diff.toml):

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/diff.toml \
  'diff_scan.x__crawl_count_problem__mutmut_*'
```

Other diff-profile targets remain optional diagnostics; passing the count gate
does not certify the broader comparison corpus.
Explanation tests require nonempty text reasons for unverified/rejected
comparisons and no spurious scope warning for matching execution. They exercise
JSON, Markdown and MCP parity alongside the strict and legacy comparison gates.
For reason-rendering changes, target `diff_scan.x_render_markdown__mutmut_*`
with the diff profile in the extras-enabled Python 3.12 environment. Label tests
exercise built-in/CommonMark/branded rendering while retaining raw JSON evidence.

For crawl-setting changes, target `diff_scan.x__crawl_settings__mutmut_*` and
`diff_scan.x__comparison__mutmut_*` with that profile. Every sampled row retains
known or unrecorded settings and auditor scopes, including duplicate URLs.
Mixed evidence withholds fix claims; actual rendering fallbacks and pairs of
legacy reports retain their existing handling without certifying missing data.

For acquisition-evidence changes, use the same profile with
`'lib.report.x_recorded_execution_problem__mutmut_*'` and record the scoped
results and any surviving variants; its text diagnostics are not the scope CI gate.

The optional [service profile](scripts/mutation/services.toml) checks brief
entry points, account opt-in, and shared scoring-rule ownership across pages.
Install the optional SDK in that environment
so registered-tool schema/dispatch checks run too:

```bash
.venv-mutation/bin/python -m pip install "mcp==1.29.0"
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/services.toml \
  'brief.x_run__mutmut_*' 'brief.x_main__mutmut_*' 'mcp_server.x__brief__mutmut_*'
```

The optional [render profile](scripts/mutation/render.toml) checks Markdown
input admission and source/output preservation:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/render.toml \
  'render_report.x__read_markdown__mutmut_*'
```

The optional [schema generator profile](scripts/mutation/schema.toml) checks
JSON field admission, caller isolation and safe script embedding:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/schema.toml \
  'generate_schema.x_build__mutmut_*' 'generate_schema.x__coerce__mutmut_*'
```

This profile uses offline tests; the stdio recovery test additionally runs when
the optional MCP SDK is installed. Record survivors separately from the mandatory
CI gates, as with the other optional profiles.
With the SDK installed, also target `mcp_server.x_build_server__mutmut_*` to
check tool registration and recoverable schema/diff/planner admission diagnostics.
Use `mcp==2.3.0` for that target: older SDKs expose ordinary `ValueError` messages
too, so they cannot demonstrate the newer SDK's masking regression.
The same profile's `mcp_server.x__plan__mutmut_*` target checks the planner's
relative-repository boundary and sanitized path diagnostics.

Pass multiple quoted patterns to gate several functions in one fresh run. Every
requested pattern must match at least one mutant; a valid target cannot mask an
empty/misspelled second target. Overlapping patterns count each mutant once.

Configuration paths use `src/` for scanner scripts and retain
`skills/seo-scan/tests/` for tests and fixtures.
Each run stages fresh temporary copies, ensuring tests import mutated source,
leaving the working tree unchanged and avoiding stale cached results.
Repository-relative test/fixture paths remain usable, including the MCP planner's
relative repository argument. Scanner imports still resolve to mutated `src/`,
not a duplicate source copy beside the tests. Tests requiring other root-level
assets still need explicit staging support: the runner copies scanner source and
tests, not the whole repository. A failing baseline stops the run.

Review each surviving diff printed by the gate. Strengthen assertions for
observable behavior and rerun. Do not change correct behavior to improve the
score. Equivalent mutants require explicit, narrowly justified review before
any exclusion; do not lower thresholds or blanket-ignore files. Only recorded
pytest test-failure exits pass. The runner reads the pinned tool's metadata:
pytest internal errors fail even though Mutmut labels them killed. Empty,
untested, skipped, timed-out, suspicious, interrupted and unknown outcomes fail.

Include selected functions/tests, killed/total counts, exclusions and remaining
limits in the PR. Expand the committed scope when an area has a stable, fast
baseline. GitHub Actions runs the default gate on pull requests and pushes to
main; other functions require a focused local run. Keep the full test suite and the
review → fix → review → green CI → merge flow.

## Pull requests

Keep normal improvements under `Unreleased` in the changelog. Passing tests,
green CI and a merged PR do not trigger a release: batch related changes until
the owner explicitly requests publishing. Do not bump versions per improvement.

Release versions come from `skills/seo-scan/scripts/_version.py`. After changing
it, run `python scripts/sync_version.py` and regenerate the report snapshots.
Use `python scripts/sync_version.py --check` to validate plugin manifests without
editing files; CI rejects any drift.

- Keep PRs focused. Reference the issue (`Closes #NN`).
- Run the test suite and scan a real URL before submitting.
- Match the surrounding code style (stdlib-first, small functions, docstrings that
  explain *why*).

## Reporting bugs / requesting features

Use the issue templates. For questions and open-ended ideas, open a Discussion.
