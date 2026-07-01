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
    │   ├── crawl_site.py    # polite site crawl + rollup (links, dupes)
    │   ├── validate_sitemap.py
    │   ├── generate_schema.py / generate_llms.py
    │   ├── audit.py         # comprehensive page + crawl + sitemap
    │   ├── diff_scan.py     # diff two JSON reports (regression tracking)
    │   ├── crux.py          # `narwhal vitals` — real Core Web Vitals via CrUX (opt-in)
    │   ├── mcp_server.py    # `narwhal mcp` — MCP server exposing the auditors
    │   ├── cli.py           # unified `narwhal` entrypoint (scan/crawl/…)
    │   ├── audit_*.py       # one file per auditor (technical/content/schema/geo)
    │   └── lib/             # http, htmlx, report, robots, links, sitemap,
    │                        #   simhash, text, content_quality, config
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
- Add a passing-case and failing-case assertion in `tests/test_smoke.py`.
- If the check encodes non-obvious reasoning/thresholds, document the *why* in the
  matching `references/*.md`.

## Adding a new auditor

Create `audit_<name>.py` exposing `audit(doc, resp, report, ctx)`, register it in
`AUDITORS` in `scan.py`, and add a `references/<name>.md`.

## Pull requests

- Keep PRs focused. Reference the issue (`Closes #NN`).
- Run the test suite and scan a real URL before submitting.
- Match the surrounding code style (stdlib-first, small functions, docstrings that
  explain *why*).

## Reporting bugs / requesting features

Use the issue templates. For questions and open-ended ideas, open a Discussion.
