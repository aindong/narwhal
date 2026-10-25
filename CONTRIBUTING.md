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

The default gate covers `lib.links.http_check_state` and `lib.links.is_broken`:
the complete sitemap response-state module exercises the report/planner matrix
and MCP handoff, and existing direct link tests cover status 0 and all gated
codes. The combined scope kills 34/34 mutants. The response-state tests alone
missed two status-0 mutations in `is_broken`; including its existing direct
assertions kills both without changing scanner behavior.

Initially, 21 of 27 response-classifier mutants were killed.
Six survived because the matrix omitted HTTP 300, 400 and 600; boundary
assertions now kill all 27 without changing production behavior.

For behavior changes, select affected files and relevant offline tests in
[the mutation configuration](scripts/mutation/pyproject.toml), then run a quoted
Mutmut function pattern, for example:

```bash
.venv-mutation/bin/python scripts/mutation_test.py 'lib.links.x_http_check_state__mutmut_*'
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
baseline. The gate currently runs locally; automatic CI integration is pending
permission to publish the workflow. Other functions require a focused local
run. Keep the full test suite and the
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
