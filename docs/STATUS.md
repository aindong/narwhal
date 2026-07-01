# Project status & handoff

_Last updated: 2026-07-01 · version **1.4.0**_

A snapshot of where Narwhal stands and how to continue it. For the item-by-item
plan see [ROADMAP.md](ROADMAP.md); for release history see
[../CHANGELOG.md](../CHANGELOG.md).

## What Narwhal is
A local-first SEO + GEO/LLMO scanning toolkit shipped as a Claude Code plugin
(also runnable via `uvx` / cloned repo / any agent via `AGENTS.md`). Two layers:

- **Deterministic scripts** (`skills/seo-scan/scripts/`) — fast, reproducible,
  zero-dependency **measurement**. These are the source of truth and are fully
  tested.
- **Multi-agent orchestration** (`agents/` + `commands/narwhal.md`) — specialist
  subagents that run the scripts as tools and add **reasoning** on top; `/narwhal
  audit` fans them out in parallel and synthesizes one report.

Design principles (keep these): local-first, zero required deps, SSRF-safe,
fix-first & honest output. See [../CONTRIBUTING.md](../CONTRIBUTING.md).

## Current state (done)
- **All P0 + P1 roadmap items** shipped (#1–#12, closed).
- **Beyond the roadmap:** `/narwhal <action> <site>` command, plugin renamed to
  `narwhal`, audit-style report, comprehensive `audit`, **multi-agent deep audit**
  (10 specialists), filler/AI-writing content scorer, link-check perf fix.
- **#13 shipped:** **HTML + PDF report export** — self-contained styled HTML
  (`--format html`: score gauge, per-area breakdown, severity cards) on `scan` and
  `audit`; PDF via WeasyPrint with graceful HTML fallback (`--format pdf`). Sample
  in `docs/samples/`.
- **Tests:** 72, green in CI across Python 3.8–3.12 + Windows.
- **Released:** v1.0.0 → v1.4.0. Plugin installs as `narwhal@narwhal`.

## Layout
```
narwhal/
├── .claude-plugin/        plugin.json + marketplace.json (name: narwhal)
├── commands/narwhal.md    /narwhal <action> <site> (dispatch + audit orchestration)
├── agents/                10 specialist subagents (narwhal-*.md)
├── skills/seo-scan/
│   ├── SKILL.md           auto-triggering skill
│   ├── scripts/           scan, crawl_site, validate_sitemap, generate_schema,
│   │                      generate_llms, audit, cli + lib/ (http, htmlx, report,
│   │                      robots, links, sitemap, simhash, text, content_quality,
│   │                      config)
│   ├── references/        deep-dive guidance per auditor
│   └── tests/             offline unittest suite (no network, no deps)
├── docs/                  ROADMAP, CONFIG, STATUS (this), index, samples/
├── narwhal.example.toml   config template
└── pyproject.toml         uvx/pip packaging (narwhal-seo)
```

## What's next (open issues — all P2)
- **#14** Scan diffing / regression tracking (SQLite snapshots) — recommended next.
- **#15** Optional PageSpeed/CrUX for real Core Web Vitals (opt-in; the
  `narwhal-performance` agent already flags hygiene and points here).
- **#16** Harden the Playwright `--render` path + tests.
- **#17** MCP server wrapper for the auditors.
- **#18** Dark-mode logo + README `<picture>` auto-swap.

### Also worth doing (not yet ticketed)
- **Tune the multi-agent audit from real runs** — the 10 agents were authored, then
  validated once live (worked well; the only fix so far was report formatting).
  Continue tuning each specialist's prompt against real audits.
- Confirm `${CLAUDE_PLUGIN_ROOT}` resolves for subagents in the field (agents fall
  back to `uvx` if not).
- Make the optional `trafilatura` main-content path the default for content depth.

## Dev workflow
```bash
python -m unittest discover -s skills/seo-scan/tests -v   # run tests (no deps)
python skills/seo-scan/scripts/scan.py https://example.com  # try a scan
claude plugin validate .                                  # validate plugin manifests
```
CI runs on every push/PR (`.github/workflows/ci.yml`).

## Release process
1. Bump the version in **5 places** (keep in sync):
   `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
   `pyproject.toml`, `skills/seo-scan/scripts/__init__.py`,
   `skills/seo-scan/scripts/cli.py` (fallback).
2. Update [CHANGELOG.md](../CHANGELOG.md) and this file's version line.
3. Commit, push, confirm CI green.
4. `gh release create vX.Y.Z --target main --title … --notes …`
5. Users update: `/plugin marketplace update narwhal` → `/plugin update narwhal@narwhal` (restart).

Versioning is additive-minor / patch-fix; the plugin rename in 1.2.0 only changed
the *install string* (`narwhal@narwhal`), not behavior.
