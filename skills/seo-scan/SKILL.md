---
name: seo-scan
description: >-
  Audit a web page or site for SEO and GEO/LLMO (AI-search) readiness. Use when
  the user wants to scan, audit, or improve a URL's search visibility — technical
  SEO, on-page content and E-E-A-T, schema.org/JSON-LD structured data, or how
  well a page can be cited by AI answer engines (ChatGPT, Claude, Perplexity,
  Google AI Overviews). Also use to generate valid JSON-LD or check AI-crawler
  access. Triggers: "SEO audit", "check my meta tags", "why isn't this ranking",
  "make this page AI-search friendly", "GEO", "LLMO", "structured data", "llms.txt".
license: MIT
---

# SEO & GEO/LLMO Scan

A local-first toolkit that audits a page or site for classic SEO **and** GEO/LLMO
(Generative Engine Optimization — being cited by AI answer engines). It fetches
the real page, runs four auditors, and returns a prioritized, fix-first report.
No accounts or API keys are required.

## When to use this skill

- Auditing a page or whole site for search visibility.
- Diagnosing why a page underperforms (thin content, missing meta, no schema).
- Preparing content to be **cited by AI answers**, not just to rank in blue links.
- Generating correct schema.org JSON-LD.
- Checking whether AI crawlers (GPTBot, ClaudeBot, PerplexityBot…) can access a site.

## Setup

Scripts run on a bare Python 3.8+ install. For higher-fidelity parsing and JS
rendering, optionally install the extras (the tools auto-detect them):

```
pip install -r skills/seo-scan/requirements.txt
python -m playwright install chromium   # only needed for --render
```

## How to run

All scripts live in `scripts/`. Run them and read the report back to the user in
your own words — lead with the highest-severity fixes.

**Comprehensive site audit** (the flagship `audit` action — combines a homepage
audit + site crawl + sitemap validation into one report):
```
python scripts/audit.py https://example.com
```

**Audit one page** (Markdown report to stdout):
```
python scripts/scan.py https://example.com/page
```

Useful flags:
- `--render` — render JavaScript with Playwright (for SPAs / client-rendered pages).
- `--format json|html|pdf` — machine-readable JSON, a self-contained styled HTML
  report, or PDF (needs WeasyPrint; falls back to HTML). Use `-o <file>` to save.
  `html`/`pdf` also work on `audit.py` for a shareable, stakeholder-ready report.
- `--only technical,geo` — run a subset: `technical`, `content`, `schema`, `geo`.
- `--fail-under N` — exit non-zero if the score is below `N` (CI quality gate;
  `crawl_site.py` gates on the average score).

**Audit a whole site** (discovers URLs via sitemap or internal links, rolls up
the issues that recur most — the highest-leverage fixes):
```
python scripts/crawl_site.py https://example.com --max-pages 25
```
The crawler is polite by default: it **honors robots.txt** (skips disallowed URLs;
reported in the summary), fetches site-level signals once, and scans pages in
parallel. Tune with `--concurrency N` (default 4), `--delay SECONDS` (sequential
rate-limit), and `--ignore-robots` to override. `--fail-under N` gates on the
average score. Add `--check-links` to check outbound links (internal + external)
for 4xx/5xx/dead — reported grouped by source page (`--max-links N` caps how many;
rate-limited/bot-blocked codes like 429/403 are treated as gated, not broken).
**Near-duplicate content detection** runs by default (SimHash fingerprints;
clusters pages ≥`--dup-threshold` % similar and flags clusters lacking a
consistent canonical; disable with `--no-dupes`).

**Generate schema.org JSON-LD:**
```
python scripts/generate_schema.py Article --field headline="…" --field author="…"
python scripts/generate_schema.py --list      # supported types
```

**Validate a site's XML sitemap(s)** (discovers from robots.txt/common paths or
takes a sitemap URL; recurses indexes, validates `loc`/`lastmod`, samples URLs for
404s, handles gzip):
```
python scripts/validate_sitemap.py https://example.com --sample 20
```

**Generate a starter `llms.txt`** (seeds from the homepage + discovered pages,
grouped into sections; a curation starting point, not a finished file):
```
python scripts/generate_llms.py https://example.com -o llms.txt
```

**Track health over time / catch regressions** (no database — diff two saved JSON
reports). Save a scan as JSON now, re-scan later, and compare:
```
python scripts/scan.py https://example.com --format json -o before.json
# ...later...
python scripts/scan.py https://example.com --format json -o after.json
python scripts/diff_scan.py before.json after.json
```
The diff reports the score delta and which findings are **new**, **resolved**,
**worsened**, or **improved** (dynamic titles like "Thin content (210 words)" are
matched across runs). Add `--fail-on-regression` for a CI gate: it exits non-zero
if the score dropped or a new critical/high finding appeared. Works on `audit`
JSON too (uses the overall score + homepage findings).

**Real Core Web Vitals** (opt-in; the one tool that calls an external service).
Everything else is local and must never fabricate field metrics — for the *real*
LCP/INP/CLS (what Chrome users experience), query the CrUX API:
```
python scripts/crux.py https://example.com/page      # needs a CrUX API key
python scripts/crux.py https://example.com --origin --form-factor phone
```
The key is resolved from `--crux-key`, the `CRUX_API_KEY` env var, or a `.env` file
(auto-loaded) — so once the user has set it, just run the script. If it reports the
key is missing, relay the three ways to provide one and the free-key link
(`https://developer.chrome.com/docs/crux/api`); **do not** invent numbers. Low-traffic
URLs return "no data" — suggest `--origin`. Get a key: enable the *Chrome UX Report
API* in Google Cloud Console and create an API key (free, 150 queries/min).

When CrUX has **no data** (most pages are below its traffic floor), use lab data —
a PageSpeed Insights (Lighthouse) synthetic test that works for any URL:
```
python scripts/crux.py https://example.com/page --lab                 # mobile
python scripts/crux.py https://example.com/page --lab --strategy desktop
```
It returns a performance score + LCP, TBT (lab proxy for INP), CLS, FCP, SI, TTI.
**Always label lab data as synthetic/estimate, not real-user field data.** The PSI
key is optional (keyless quota is shared/often exhausted); set `PAGESPEED_API_KEY`
or reuse the CrUX key with the PageSpeed Insights API also enabled.

**Real Search Console query data** (opt-in; OAuth — GSC has no API-key path).
Turns "what's broken" into "what to fix *first*" using the user's own queries:
```
python scripts/gsc.py https://example.com            # needs GSC credentials
python scripts/gsc.py https://example.com --days 28 --format json
```
Reports striking-distance queries (positions 8–20 with impressions), CTR
laggards (top-10 rankings whose CTR is far below the expected-for-position
curve — title/meta rewrite candidates; the curve is a labeled heuristic used
only for ranking), decaying pages (clicks down ≥25% vs the prior window), and
keyword cannibalization (several pages splitting one query — cross-check the
crawler's near-duplicate clusters). Credentials resolve from env/`.env`:
`GSC_ACCESS_TOKEN` (e.g. `gcloud auth print-access-token`, expires ~1h) or the
durable `GSC_CLIENT_ID`/`GSC_CLIENT_SECRET`/`GSC_REFRESH_TOKEN` trio. If
missing, relay the one-time setup: create a **Desktop** OAuth client (enable
the Search Console API), put the ID/secret in `.env`, run
`python scripts/gsc.py --auth --write-env`. Add `--gsc` to `audit.py` to fold
the same data into the audit report/JSON (degrades to a note without
credentials). These are real numbers for the user's verified property — never
fabricate or extrapolate them.

**Turn a Markdown report into a branded HTML/PDF** (e.g. after synthesizing an
audit — write it to a `.md`, then render):
```
python scripts/render_report.py report.md -o report.html      # branded HTML
python scripts/render_report.py report.md --format pdf -o report.pdf   # needs WeasyPrint
```
The output is self-contained (inline CSS + logo), with the Narwhal header/footer —
same look as the scan/audit reports.

## What each auditor covers

| Auditor | Focus |
|---|---|
| `technical` | title/meta, headings, canonical, robots directives, viewport, hreflang, images, links, HTTP hygiene, robots.txt, sitemap |
| `content` | word count / thin content, readability, author & date (E-E-A-T), Open Graph/Twitter cards |
| `schema` | JSON-LD detection, required/recommended property validation, deprecated rich-result types |
| `geo` | question-based headings, citable passage structure, evidence density, direct-answer intro, `llms.txt`, **AI-crawler access** |

Deep-dive guidance (heuristics, thresholds, and the *why* behind each check) lives
in `references/` — read the relevant file when the user asks for detail or wants to
go beyond the automated checks:

- `references/technical-seo.md`
- `references/content-eeat.md`
- `references/schema.md`
- `references/geo-llmo.md`

## Interpreting output

Each report has a **0–100 health score** and findings bucketed by severity
(`critical → high → medium → low`, plus passing checks). Scores are directional,
not absolute — always explain the *specific* fixes, not just the number. When a
finding is a heuristic (readability, citability, entity clarity), say so; these
flag pages worth a human look rather than issuing verdicts.

## Deep audit (multi-agent)

For a comprehensive audit, `/narwhal audit <site>` runs the deterministic
`audit.py` baseline and then fans out ~10 specialist subagents in parallel (in the
plugin's `agents/` dir) — technical, content, schema, geo, performance, links,
duplication, sitemap, sxo, and local — each using these scripts as tools and adding
reasoning + exact fixes, synthesized into one prioritized report. The individual
scripts above remain the fast, deterministic path.

## Fix loop (audit → edit → prove it)

When the site's **source code is in the current workspace**, don't stop at the
report — close the loop (`/narwhal fix <url>` in Claude Code):

1. Save a baseline: `python scripts/scan.py <url> --format json -o before.json`
   (or reuse a fresh audit JSON).
2. Map each finding to the file that owns the artifact (layout `<head>` for
   title/meta/canonical/OG, page source for alt/headings, static dir for
   robots.txt) and apply minimal, framework-idiomatic edits. Use
   `generate_schema.py` for JSON-LD and `generate_llms.py` for llms.txt rather
   than hand-writing them.
3. Re-scan a local preview (`--allow-private` for localhost) as `after.json`,
   then `python scripts/diff_scan.py before.json after.json` to show what
   resolved and the score delta.

Honesty rules: a localhost re-scan only verifies **page-level** fixes — label
site-level signals (robots.txt, sitemap, HTTPS, canonical host, llms.txt) as
*verify after deploy*; if there's no local preview, report "applied, pending
deploy" with the re-scan commands. If the source is **not** in the workspace,
make no edits — give a per-finding fix plan instead. Findings unreachable from
the repo (CDN/redirect config, real CWV) go in a "needs manual action" list.

## Configuration

An optional `narwhal.toml` at the project root (auto-discovered) tunes scoring
weights, check thresholds, CLI defaults, and ignore rules. Precedence is
**CLI flag > narwhal.toml > default**. Use `--config PATH` or `--no-config` to
override. If the user has one, respect it; to suppress a finding they consider
acceptable, add it to `[ignore]` rather than hard-coding around it. Full docs:
`docs/CONFIG.md`.

## Guardrails

- **SSRF-safe:** hosts resolving to private/loopback IPs are blocked. Only pass
  `--allow-private` when the user is intentionally scanning a local/staging site.
- **Local-only by default:** no external services are called. API integrations
  (PageSpeed, CrUX, SERP data) are intentionally out of the default path.
- Don't fabricate metrics the tools don't measure (e.g. exact Core Web Vitals
  field data needs a real device/CrUX; the scan only flags likely LCP hygiene
  issues). Report what was measured and what would need an external source.
