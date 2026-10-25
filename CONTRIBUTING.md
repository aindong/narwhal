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
The fixture uses a non-default 6 MB HTML budget and requires all generated
page scans to retain it.
Malformed execution-scope and HTTP-status fixtures must withhold automation
while keeping planning read-only.
Reversing the reports must fail the regression gate. This is local,
page-level workflow evidence, not real-site SEO gains or deployment proof.
A subsequent HTTP 206 preview must leave the diff incomparable (gate exit 2),
with no score delta/resolved fixes and a read-only, manual verification plan.
The same fixture then audits a healthy homepage and an inner page missing its
title. Its recurring rule must carry the inner URL witness and plan only that
page's inventoried source. An explicit title edit removes the recurring finding
and improves the comparable overall audit score. Audit diff finding lists still
describe homepage changes; inner resolution is checked directly in crawl rows.
The separate crawl-rule diff must report the missing-title rule as no longer
observed in the matching sample, through both CLI and optional MCP.
With the optional MCP SDK installed, add `--mcp` to exercise the installed stdio
server for both plans and all three diffs. Both SDK CI jobs run this mode and
require MCP diff output to match the CLI. Local scans use the CLI's explicit
`--allow-private`; the MCP scan tool continues to require public URLs.

The installed `service_opt_in_smoke.py` check runs isolated from repository
imports, with account collectors mocked and sockets blocked. It verifies that
configured credentials do not enable default audit/brief service calls and
that explicit brief CLI/Python/MCP opt-in remains available; it does not test
live OAuth/API availability. Packaging and both MCP SDK CI jobs run this check.

Plan contract tests compare generated plans with the checked-in remediation-plan
schema. Full JSON Schema validation runs in both MCP SDK CI environments using
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
owner checks across the supported frameworks:

```bash
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/planner.toml \
  'plan.x__route_candidates__mutmut_*' 'plan.x_likely_files__mutmut_*'
```

Profile paths are relative to your invoking directory; paths inside the profile
refer to the temporary staging layout described below. Selecting a profile does
not infer function targets: pass their quoted patterns explicitly. The planner
profile is an optional diagnostic, not a default CI gate. Record fresh killed/total
counts and unresolved outcomes with each PR; past counts do not score new source
or tests. Unresolved results keep the gate nonzero. Its schema-file
test is omitted because references are not staged; full suites/MCP CI retain it.

The optional [service profile](scripts/mutation/services.toml) checks brief
entry points, account opt-in, and shared scoring-rule ownership across pages.
Install the optional SDK in that environment
so registered-tool schema/dispatch checks run too:

```bash
.venv-mutation/bin/python -m pip install "mcp==1.29.0"
.venv-mutation/bin/python scripts/mutation_test.py --config scripts/mutation/services.toml \
  'brief.x_run__mutmut_*' 'brief.x_main__mutmut_*' 'mcp_server.x__brief__mutmut_*'
```

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
