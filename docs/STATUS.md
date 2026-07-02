# Project status & handoff

_Last updated: 2026-07-02 · version **1.25.1**_

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
  (10 specialists), filler/AI-writing content scorer, link-check perf fix,
  **`/narwhal fix`** (v1.17.0) — closes the audit → fix loop: maps findings to
  source edits in the workspace, re-scans, and diffs to prove the delta,
  **Search Console integration** (v1.18.0, `gsc.py`) — real query data
  (striking distance, CTR laggards, decay, cannibalization) via stdlib-only
  OAuth; standalone `narwhal gsc` + `audit --gsc` fold-in.
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
- **Real-world tuning round (v1.19.0, closes #19 + #20):** scanned 8 diverse live
  sites + graded 3 live specialist-agent runs. Fixed the stdlib parser (nested
  `<h1><a>` lost headings; anchor text missing from visible text), stopworded
  month tokens, added **page-type-aware checks** (`htmlx.is_hub_page/looks_article/
  is_homepage`): homepage brand titles, hub thin-content, article-only byline,
  article-scoped GEO severities. All 10 agent prompts gained **Judgment rules**
  (classify page type, sample an inner page, respect owner opt-outs, report
  *Discounted script findings*), and the orchestrator honors the discounts.
  Depth findings state their extraction basis (trafilatura vs visible text).
  `${CLAUDE_PLUGIN_ROOT}` confirmed resolving for subagents. Scores on well-run
  sites corrected: jvns 62→79, HN 52→66, pydocs 75→86, Verge 71→80.
- **Tests:** 179, green in CI across Python 3.8–3.12 + Windows (+ render-smoke job).
- **CrUX key convenience (v1.10.0):** `narwhal vitals` resolves the key from
  `--crux-key` > `CRUX_API_KEY` env > `.env` file (`lib/env.py`, zero-dep).
- **Plugin-native `vitals`/`diff` (v1.11.0):** both wired into `/narwhal <action>`
  and the skill.
- **Vitals in the audit report (v1.13.0):** `audit.py --vitals` runs CrUX field
  (or PSI lab fallback) and adds a Core Web Vitals section to **all** formats
  (md/html/pdf/json); `/narwhal audit` passes `--vitals`. md_to_html now does
  `_italic_`.
- **Branded report file from `/narwhal audit` (v1.15.0):** the command writes
  `narwhal-audit-report.md` then renders a branded HTML (offers PDF) via the new
  `narwhal render` (`render_report.py`) — Markdown → branded HTML/PDF, reusing the
  report shell. md_to_html now renders `[links]`.
- **Two PDF engines (v1.16.0):** `report.pdf_from_html` tries WeasyPrint then
  headless Chromium (Playwright `page.pdf`, pixel-perfect, verified). `/narwhal
  audit` delivers **HTML by default** (v1.16.1 — needs no tools); PDF is opt-in
  (`--format pdf`).
- **Released:** v1.0.0 → v1.16.1. Plugin installs as `narwhal@narwhal`.

## Layout
```
narwhal/
├── .claude-plugin/        plugin.json + marketplace.json (name: narwhal)
├── commands/narwhal.md    /narwhal <action> <site> (dispatch + audit orchestration)
├── agents/                10 specialist subagents (narwhal-*.md)
├── skills/seo-scan/
│   ├── SKILL.md           auto-triggering skill
│   ├── scripts/           scan, crawl_site, validate_sitemap, generate_schema,
│   │                      generate_llms, audit, diff_scan, render_report, crux, psi, mcp_server, cli + lib/ (http, htmlx, report,
│   │                      robots, links, sitemap, simhash, text, content_quality,
│   │                      config, env, brand)
│   ├── references/        deep-dive guidance per auditor
│   └── tests/             offline unittest suite (no network, no deps)
├── docs/                  ROADMAP, CONFIG, STATUS (this), index, samples/
├── narwhal.example.toml   config template
└── pyproject.toml         uvx/pip packaging (narwhal-seo)
```

## What's next (open issues)
The original roadmap (#1–#20) is **complete**. The **next wave (v2.x)** came out
of the 2026-07 project self-review — relative + strategic answers, still
local-first (see ROADMAP "Next wave" for detail):
- ~~#21~~ `narwhal compare` — **shipped v1.20.0** (compare.py, /narwhal compare, MCP compare_pages)
- ~~#22~~ Site-graph analysis — **shipped v1.21.0** (lib/sitegraph.py, always-on in crawl/audit)
- ~~#23~~ JS-dependence check — **shipped v1.22.0** (lib/jsdiff.py, --render diffs raw vs rendered)
- ~~#24~~ Image weight/format + og:image — **shipped v1.23.0** (lib/images.py, HEAD-budgeted + dimension probe)
- ~~#25~~ Hreflang reciprocity — **shipped v1.24.0** (lib/hreflang.py, probe + exact pairs) — P1 tier complete
- **#26** Content-brief flow (GSC + compare grounded) (P2)
- **#27** E-commerce checks + conditional store specialist (P2)
- **#28** Test-suite health: split monolith + golden-file tests (P3)

### Ongoing quality practice
Specialist tuning (#19) is a loop, not a one-shot: each real `/narwhal audit` run
is tuning material. When a specialist misses, over-flags, or parrots the script,
encode the correction in its `agents/narwhal-*.md` **Judgment rules** and, where
the root cause is measurable, fix the deterministic check + add a regression test
(see the v1.19.0 round for the pattern).

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
