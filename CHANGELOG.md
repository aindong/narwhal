# Changelog

All notable changes to Narwhal are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [1.19.0] — 2026-07-02

Real-world tuning round (#19, #20): scans of 8 diverse live sites (SaaS,
e-commerce, news, docs, blog, wiki, link-hub) + 3 live specialist-agent runs,
then every false positive fixed at the source. Average score change on well-run
sites: jvns.ca 62→79, HN 52→66, docs.python.org 75→86, The Verge 71→80 — all
from removing *wrong* findings, not loosening checks.

### Fixed
- **Stdlib parser lost headings that wrap links** (`<h1><a>…</a></h1>` recorded no
  H1 — false "No H1" on most real blogs) and **dropped all anchor text from the
  visible text** (link-heavy pages looked falsely thin). Captures are now a stack
  and captured text flows into the page text; `<title>` stays out of body copy.
- **Month names counted as "dominant topics"** on date-heavy archive pages
  (`dec (78), jan (74)…`) — now stopworded.

### Changed — page-type-aware checks
New shared helpers (`htmlx.is_hub_page` / `looks_article` / `is_homepage` /
`link_text_share`) scope checks to the page's role:
- Brand-only **homepage titles** are a low note, not "Title very short (high)".
- **Link-hub/index pages** get "hub with little prose (low)" instead of "Thin
  content (high)"; readability isn't judged on nav fragments.
- **Byline/author** is only expected on article pages.
- GEO **question-headings** and **evidence-density** are medium on articles, low
  elsewhere (they used to fire on ~90% of real sites).
- The schema auditor's "article-like page" now uses the shared heuristic instead
  of raw text length (no more Article-schema nags on text-heavy homepages).
- Depth findings state their **extraction basis** (trafilatura main-content vs
  visible text), and the trade-off is documented (#20).

### Changed — specialist agents (tuned from graded live runs)
All 10 `agents/narwhal-*` prompts gain **Judgment rules**: classify the page type
first and discount type-mismatched script findings; sample a representative inner
page when auditing a domain root; respect deliberate owner choices (e.g.
intentional AI-crawler opt-outs — split advice by intent, never "fix" an opt-out).
GEO adds the training-vs-answer-engine distinction (GPTBot ≠ AI-answer
visibility); technical verifies surprising negatives in raw HTML. Specialists now
return a **Discounted script findings** section, and the audit orchestrator
honors it (discounts are never re-added to the action plan).
`${CLAUDE_PLUGIN_ROOT}` confirmed to resolve for subagents in the field.

## [1.18.0] — 2026-07-02

### Added
- **Google Search Console integration (`narwhal gsc <site>`)** — opt-in, real
  query data for your verified property: **striking-distance** queries
  (positions 8–20 with impressions), **CTR laggards** (top-10 rankings far below
  the expected-CTR curve — title/meta rewrite candidates; the curve is a labeled
  heuristic), **decaying pages** (clicks down ≥25% vs the prior window), and
  **keyword cannibalization** (several pages splitting one query). Markdown/JSON
  output; `--days`, `--min-impressions`.
- **Stdlib-only OAuth** (GSC has no API-key path): `GSC_ACCESS_TOKEN`
  passthrough, or the durable `GSC_CLIENT_ID`/`GSC_CLIENT_SECRET`/
  `GSC_REFRESH_TOKEN` trio — obtained once with **`narwhal gsc --auth`**
  (loopback browser consent; `--write-env` stores the credentials in `.env`).
  Read-only scope; only fixed Google hosts are contacted. Service-account auth
  deliberately deferred (would need a crypto dependency).
- **`narwhal audit --gsc`** folds the same data into the audit (new
  "Search performance (GSC)" section in Markdown/HTML, `gsc` block in JSON, and
  a clicks headline in the metrics strip), mirroring `--vitals`; degrades to a
  one-line note without credentials. `/narwhal audit` now prioritizes the action
  plan by real queries when the block is present, and `/narwhal fix` fixes pages
  with actual search opportunity first.

### Changed
- The audit's conditional report sections (Core Web Vitals, Search performance)
  are now numbered dynamically instead of hardcoding "4."

## [1.17.0] — 2026-07-02

### Added
- **`/narwhal fix <site>` — close the audit → fix loop.** When the site's source
  is in the current workspace, the agent maps each scan/audit finding to the file
  that owns it (title/meta, canonical, OG/Twitter, JSON-LD via
  `generate_schema.py`, alt text, robots.txt, `llms.txt` via `generate_llms.py`),
  applies minimal framework-idiomatic edits, then **re-scans and runs
  `diff_scan.py`** to prove what resolved and the score delta. Honest by design:
  localhost re-scans verify page-level fixes only (site-level signals are labeled
  *verify after deploy*), "applied, pending deploy" when there's no local preview,
  no edits + a per-finding fix plan when the source isn't in the workspace, and a
  "needs manual action" list for findings unreachable from the repo. Fix-loop
  guidance also added to `SKILL.md` and `AGENTS.md` for non-Claude agents.

## [1.16.1] — 2026-07-02

### Changed
- **`/narwhal audit` delivers HTML by default again** (needs no extra tools). PDF is
  now opt-in — the Chromium/WeasyPrint engines and `--format pdf` remain available
  for anyone who wants a PDF, and the self-contained HTML can be Printed → Saved as
  PDF from any browser.

## [1.16.0] — 2026-07-02

### Added
- **Second PDF engine: headless Chromium (Playwright).** `pdf_from_html` now tries
  WeasyPrint, then Chromium print-to-PDF — which renders our exact CSS (pixel-perfect
  branded PDF) and installs cleanly cross-platform (it also powers `--render`).
  Verified end to end (real branded PDF generated via Chromium).

### Changed
- **`/narwhal audit` delivers a PDF by default.** Step 4 now renders
  `narwhal-audit-report.pdf`; with no PDF engine it falls back to a self-contained
  HTML (and the message lists both install options + the "Print to PDF from your
  browser" escape hatch).

## [1.15.0] — 2026-07-02

### Added
- **`/narwhal audit` now delivers a branded report file** — not just chat output. It
  writes `narwhal-audit-report.md`, then renders a self-contained, branded **HTML**
  report (`narwhal-audit-report.html`) of the synthesis and offers a **PDF**.
- **`narwhal render <file.md>`** (`render_report.py`) — turns any Markdown report
  into a branded HTML/PDF (inline CSS + logo, same look as scan/audit reports).
  Reuses the report renderer; `--format html|pdf`, first `# heading` becomes the
  title, reads stdin with `-`.
- The Markdown→HTML converter now renders `[text](https://…)` **links**.

## [1.14.0] — 2026-07-01

### Added
- **Branded HTML/PDF reports** — the Narwhal logo now appears in the report header
  (next to the title) and footer. It's embedded **inline as a base64 data URI**
  (`lib/brand.py`), so reports stay fully self-contained (no external request,
  works offline and in the pip/uvx package where `assets/` isn't shipped).
  Regenerate with `assets/make-brand-logo.py`. Applies to `scan` and `audit`
  HTML/PDF output.

## [1.13.0] — 2026-07-01

### Added
- **Core Web Vitals in the audit report** — `narwhal audit <site> --vitals` now runs
  CrUX **field** data (origin-level, when `CRUX_API_KEY` is set) and falls back to
  PageSpeed Insights **lab** data for low-traffic sites, then includes a **Core Web
  Vitals** section in **every** output format: Markdown, **HTML, PDF**, and JSON
  (plus a headline in the report's metrics strip). Field vs lab is clearly labeled.
  ```bash
  narwhal audit https://example.com --vitals --format pdf -o audit.pdf
  ```
- The `/narwhal audit` command passes `--vitals` in its baseline step, folds the
  verdict into the report, and offers a shareable HTML/PDF that includes it.

### Fixed
- The Markdown→HTML converter now renders `_italic_` (so the honest field/lab notes
  in HTML/PDF reports no longer show literal underscores); word-boundary-guarded so
  `snake_case` and paths are untouched.

## [1.12.0] — 2026-07-01

### Added
- **PageSpeed Insights (Lighthouse) lab data** via `narwhal vitals <url> --lab`
  (`psi.py`) — the companion to CrUX field data. Works for **any URL regardless of
  traffic**, so it fills the gap when CrUX has no field data (most pages). Returns
  an overall performance score plus LCP, **TBT** (the lab proxy for INP), CLS, FCP,
  Speed Index, and TTI, each rated.
  - Clearly labeled **lab/synthetic** (an estimate for catching regressions), never
    conflated with real-user field data. Lab has no INP.
  - PSI key optional (keyless runs at a shared, easily-exhausted quota, so a key is
    recommended): `PAGESPEED_API_KEY`, or reuse the CrUX key with the PageSpeed
    Insights API also enabled. `--strategy mobile|desktop`.
  - The CrUX "no data" message now points to `--lab`; verified against the live
    PSI v5 API contract.

## [1.11.0] — 2026-07-01

### Added
- **`vitals` and `diff` are now plugin-native** — wired into the `/narwhal <action>
  <site>` command and documented in the skill, not just the CLI. `/narwhal vitals
  example.com` runs the real CrUX Core Web Vitals lookup (resolving the key from the
  env or a `.env`, which Claude Code inherits), and `/narwhal diff old.json new.json`
  compares two saved reports.
- **The multi-agent `audit` now folds in real Core Web Vitals** when a `CRUX_API_KEY`
  is available (runs `crux.py --origin` and merges the field verdict into the
  performance section); otherwise it stays honest and points at `/narwhal vitals`.

## [1.10.0] — 2026-07-01

### Added
- **`.env` support for the CrUX key** so you don't have to pass `--crux-key` every
  time. `narwhal vitals` now resolves the key as **`--crux-key` > `CRUX_API_KEY`
  env var > `.env` file** (auto-loaded from the working directory or a parent).
  Zero-dependency loader (`lib/env.py`); `.env` is gitignored, so secrets never get
  committed. Added [`.env.example`](.env.example); the "key required" message now
  lists all three options. (Never put the key in `narwhal.toml` — that's committed.)

## [1.9.0] — 2026-07-01

### Added
- **Dark-mode logo** (`assets/logo-dark.png` + `-512`): the navy structure and
  "NARWHAL" wordmark are recolored to light icy-blue so the mark reads on dark
  backgrounds, while the teal/aqua stays vivid. The README auto-swaps to it via a
  `<picture>` element (`prefers-color-scheme: dark`). Derived deterministically
  from the light logo (`assets/make-dark-logo.py`, luminance fold) — same artwork,
  regenerable in one command.

This release also marks the **P2 roadmap backlog (#13–#18) fully cleared.**

## [1.8.0] — 2026-07-01

### Added
- **Real Core Web Vitals** (`narwhal vitals <url>`): opt-in field data from Google's
  Chrome UX Report (CrUX) API — **LCP, INP, CLS** at the 75th percentile, each rated
  good/needs-improvement/poor, with a pass/fail verdict, plus FCP/TTFB as secondary.
  Origin- or URL-level, per form factor. Verified against the current CrUX API.
  - The only feature that calls an external service — **opt-in**, gated behind an API
    key (`--crux-key` / `CRUX_API_KEY`); never on the default scan path.
  - Honest: no key → clear message; low-traffic URL with no CrUX data → says so
    (suggests `--origin`); never fabricates field metrics.
  - Built against the CrUX API directly, since PageSpeed Insights is dropping CrUX
    field data in 2026 (and INP replaced FID in 2024).
- The `narwhal-performance` agent now points at `narwhal vitals` for real field data.

## [1.7.0] — 2026-07-01

### Changed
- **Hardened the `--render` (Playwright) path.** Verified against Playwright 1.61:
  - Missing Chromium binary now yields an actionable one-line fix
    (`python -m playwright install chromium`) instead of a raw error.
  - Navigation waits on `domcontentloaded` then a **capped** `networkidle` settle
    (5s max) — `networkidle` alone could hang on analytics/long-polling sites.
  - Browser is always closed via `try/finally` (no leak on error); container-safe
    launch (`--disable-dev-shm-usage`, sandbox kept on for untrusted pages).
  - A render that can't run reports an honest error rather than silently degrading
    to raw HTML.
- `pdf_from_html` now also handles WeasyPrint being installed without its native
  libraries (`OSError`), falling back to HTML instead of crashing.

### Added
- CI **`render-smoke`** job: installs Playwright + Chromium and asserts the
  `--render` path executes JavaScript end to end (serves a JS page, checks the
  post-JS DOM). Bumped `actions/checkout` to v5.

## [1.6.0] — 2026-07-01

### Added
- **MCP server** (`narwhal mcp`): exposes the auditors as Model Context Protocol
  tools over stdio — `scan_page`, `crawl_site`, `audit_site`, `validate_sitemap`,
  `generate_llms`, `generate_schema`, `diff_reports`. A thin, typed adapter over the
  existing scripts (results match the CLI). Built on the MCP Python SDK's `FastMCP`;
  verified against the current release. Optional `mcp` extra
  (`pip install "narwhal-seo[mcp]"`) + `narwhal-mcp` console script; the core
  toolkit stays zero-dependency and prints a friendly hint when `mcp` is absent.

## [1.5.0] — 2026-07-01

### Added
- **Scan diffing / regression tracking** (`narwhal diff old.json new.json`): compare
  two saved JSON reports — score delta plus **new / resolved / worsened / improved**
  findings. Deliberately database-free (diff the JSON we already emit): human-readable,
  git-friendly, and directly readable by the agent.
  - Dynamic finding titles (e.g. `Thin content (210 words)`) are normalized so the
    same issue matches run-to-run.
  - `--fail-on-regression` exit code for CI gating (score dropped, or a new
    critical/high finding appeared).
  - Accepts both `scan` and `audit --format json` output; Markdown + JSON output.

## [1.4.0] — 2026-07-01

### Added
- **HTML report export** (`--format html`): a self-contained, styled report —
  inline CSS, an SVG score gauge, a per-area breakdown with score bars, and
  severity-coloured finding cards. No external resources, so it renders offline
  and is easy to share. Available on both `scan.py` and the flagship `audit.py`.
- **PDF export** (`--format pdf`): renders the HTML to PDF via WeasyPrint when it's
  installed, and gracefully falls back to writing HTML (with a clear note) when it
  isn't — no crash, no hard dependency.
- Sample HTML report in [`docs/samples/`](docs/samples/sample-report.html); new
  optional `pdf` extra (`pip install narwhal-seo[pdf]`).

### Changed
- Report output writing is unified through `report.deliver()`, shared by `scan.py`
  and `audit.py`, so all four formats behave consistently.

## [1.3.0] — 2026-07-01

### Added
- **Filler / AI-writing content-quality scorer** (`lib/content_quality.py`, stdlib):
  detects padding/filler phrases, telltale AI-writing patterns, and low lexical
  diversity — surfaced as hard-data findings (with example matches) in the content
  auditor and the `narwhal-content` specialist.

## [1.2.1] — 2026-07-01

### Fixed
- Multi-agent `/narwhal audit` synthesis now uses plain GitHub-flavored Markdown
  (pipe tables + lists) instead of Unicode box-drawing tables, which corrupted in
  terminals.

## [1.2.0] — 2026-07-01

### Added
- **Multi-agent deep audit**: `/narwhal audit` runs the deterministic baseline, then
  fans out ~10 specialist subagents in parallel (`agents/`: technical, content,
  schema, geo, performance, links, duplication, sitemap, sxo, + conditional local)
  and synthesizes an SEO Health Score + prioritized action plan.
- **`/narwhal <action> <site>` command** dispatching audit/scan/crawl/sitemap/llms/schema.
- **Comprehensive `audit` action** combining homepage + site crawl + sitemap.
- **Audit-style report**: executive summary, per-area subscores, quick wins.

### Changed
- Plugin renamed `seo-scan` → **`narwhal`** (install: `narwhal@narwhal`).
- Link checking uses a shorter HEAD timeout + more workers; audit uses lighter
  sub-limits — link-heavy sites went from hanging to ~25s.

## [1.1.0] — 2026-07-01

### Added
- GitHub Actions **CI** (Python 3.8–3.12 + Windows, with/without extras).
- **`--fail-under N`** CI quality gate on `scan` and `crawl`.
- Unified **`narwhal` CLI** + **`uvx`** (git-based, no install, no PyPI).
- **Polite crawler** (robots.txt-aware, `--concurrency`, `--delay`, cached signals).
- **RFC 9309 robots.txt matcher** (`lib/robots.py`).
- **Broken-link checker** (`crawl --check-links`).
- **Sitemap validation** (`narwhal sitemap`): indexes, lastmod, 404 sampling, gzip.
- **`narwhal.toml` config** (weights, thresholds, CLI defaults, ignore rules).
- **`llms.txt` generator** (`narwhal llms`).
- **Readability** (Flesch) + keyword/entity extraction + topical-focus check.
- **Near-duplicate detection** (SimHash) with canonical checks.

## [1.0.0] — 2026-07-01

### Added
- Initial release: four auditors (technical, content/E-E-A-T, schema, GEO/LLMO),
  `scan` / `crawl` / `schema` tools, SSRF-safe fetching, Markdown/JSON reports,
  Claude Code plugin install, and the offline test suite.

[1.3.0]: https://github.com/aindong/narwhal/releases/tag/v1.3.0
[1.2.1]: https://github.com/aindong/narwhal/releases/tag/v1.2.1
[1.2.0]: https://github.com/aindong/narwhal/releases/tag/v1.2.0
[1.1.0]: https://github.com/aindong/narwhal/releases/tag/v1.1.0
[1.0.0]: https://github.com/aindong/narwhal/releases/tag/v1.0.0
