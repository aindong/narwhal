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

**Audit one page** (Markdown report to stdout):
```
python scripts/scan.py https://example.com/page
```

Useful flags:
- `--render` — render JavaScript with Playwright (for SPAs / client-rendered pages).
- `--format json` — machine-readable output (use `-o report.json` to save).
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
