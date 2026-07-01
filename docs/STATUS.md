# Project status & handoff

_Last updated: 2026-07-01 · version **1.14.0**_

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
- **#14 shipped:** **Scan diffing / regression tracking** — `narwhal diff
  old.json new.json` (score delta + new/resolved/worsened/improved findings,
  `--fail-on-regression` CI gate). Database-free by design: diffs the JSON we
  already emit (`diff_scan.py`).
- **#17 shipped:** **MCP server** — `narwhal mcp` exposes all auditors as MCP
  tools over stdio (`mcp_server.py`, FastMCP; optional `mcp` extra). Verified
  against the current MCP Python SDK release.
- **#16 shipped:** **Hardened `--render`** — actionable missing-browser message,
  capped networkidle settle, guaranteed browser cleanup, honest failures; new CI
  `render-smoke` job executes JS end to end (verified vs Playwright 1.61).
- **#15 shipped:** **Real Core Web Vitals** — `narwhal vitals` (`crux.py`) fetches
  LCP/INP/CLS field data from the CrUX API. Opt-in (API key), never on the default
  path; honest when no key / no data. Verified vs the live CrUX API contract.
  **`--lab` (v1.12.0, `psi.py`)** adds PageSpeed Insights Lighthouse *lab* data for
  any URL (fills CrUX's low-traffic gap); labeled synthetic, key optional.
- **#18 shipped:** **Dark-mode logo** — `assets/logo-dark.png`; README auto-swaps
  via `<picture>`. Derived deterministically from the light logo
  (`assets/make-dark-logo.py`).
- **P2 backlog (#13–#18) fully cleared.**
- **Tests:** 107, green in CI across Python 3.8–3.12 + Windows (+ render-smoke job).
- **CrUX key convenience (v1.10.0):** `narwhal vitals` resolves the key from
  `--crux-key` > `CRUX_API_KEY` env > `.env` file (`lib/env.py`, zero-dep).
- **Plugin-native `vitals`/`diff` (v1.11.0):** both wired into `/narwhal <action>`
  and the skill.
- **Vitals in the audit report (v1.13.0):** `audit.py --vitals` runs CrUX field
  (or PSI lab fallback) and adds a Core Web Vitals section to **all** formats
  (md/html/pdf/json); `/narwhal audit` passes `--vitals`. md_to_html now does
  `_italic_`.
- **Released:** v1.0.0 → v1.14.0. Plugin installs as `narwhal@narwhal`.

## Layout
```
narwhal/
├── .claude-plugin/        plugin.json + marketplace.json (name: narwhal)
├── commands/narwhal.md    /narwhal <action> <site> (dispatch + audit orchestration)
├── agents/                10 specialist subagents (narwhal-*.md)
├── skills/seo-scan/
│   ├── SKILL.md           auto-triggering skill
│   ├── scripts/           scan, crawl_site, validate_sitemap, generate_schema,
│   │                      generate_llms, audit, diff_scan, crux, psi, mcp_server, cli + lib/ (http, htmlx, report,
│   │                      robots, links, sitemap, simhash, text, content_quality,
│   │                      config, env, brand)
│   ├── references/        deep-dive guidance per auditor
│   └── tests/             offline unittest suite (no network, no deps)
├── docs/                  ROADMAP, CONFIG, STATUS (this), index, samples/
├── narwhal.example.toml   config template
└── pyproject.toml         uvx/pip packaging (narwhal-seo)
```

## What's next (open issues)
The P0–P2 roadmap is complete. Remaining tracked work:
- **#19** Tune the multi-agent audit from real runs (ongoing quality work).
- **#20** Make the optional `trafilatura` main-content path the default.
- Plus the not-yet-ticketed ideas at the bottom of [ROADMAP.md](ROADMAP.md)
  (microdata/RDFa, OG-image validation, image-weight checks, a11y lens, hreflang
  bidirectionality, per-finding "learn more" deep links).

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
