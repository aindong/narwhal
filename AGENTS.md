# AGENTS.md — SEO & GEO/LLMO scanning toolkit

This repository provides a local-first toolkit for auditing web pages and sites
for **SEO** and **GEO/LLMO** (visibility in AI answer engines). It works with any
coding agent (Codex, Cursor, OpenCode, Claude Code, …). Claude Code additionally
loads it as a skill from `skills/seo-scan/SKILL.md`; the guidance below is the
same for every agent.

## When to use it
Reach for these tools whenever the user wants to scan, audit, or improve a URL's
search visibility: technical SEO, on-page content / E-E-A-T, schema.org JSON-LD,
or how citable a page is for ChatGPT / Claude / Perplexity / Google AI Overviews.

## Tools (all under `skills/seo-scan/scripts/`)

| Command | Purpose |
|---|---|
| `python scan.py <url>` | Audit one page → prioritized Markdown report |
| `python scan.py <url> --format json -o out.json` | Machine-readable output |
| `python scan.py <url> --render` | Render JS (SPAs) via Playwright if installed |
| `python scan.py <url> --only technical,geo` | Run a subset of auditors |
| `python scan.py <url> --fail-under 80` | Exit non-zero below a score (CI quality gate) |
| `python crawl_site.py <url> --max-pages 25` | Site-wide scan + recurring-issue rollup |
| `python crawl_site.py <url> --concurrency 4 --delay 0.5` | Polite crawl: honors robots.txt, parallel, rate-limited |
| `python crawl_site.py <url> --check-links` | Also check outbound links (internal + external) for 4xx/5xx/dead |
| `python generate_schema.py <Type> --field k=v …` | Emit valid schema.org JSON-LD |
| `python generate_schema.py --list` | List supported schema types |

Auditor names: `technical`, `content`, `schema`, `geo`.

## Setup
Runs on a bare Python 3.8+ install (stdlib fallback). Optional extras improve
parsing/rendering and are auto-detected:
```
pip install -r requirements.txt
python -m playwright install chromium   # only for --render
```

## How to report results to the user
1. Run the relevant script and read the report.
2. Lead with the **highest-severity fixes**, phrased as concrete actions.
3. Treat heuristic findings (readability, citability, entity clarity) as "worth a
   look," not verdicts — say so.
4. Don't invent metrics the tools don't measure (e.g. real Core Web Vitals field
   data needs CrUX/PageSpeed). State what was measured vs. what needs an external
   source.

## Deeper guidance
The reasoning and thresholds behind each check are in
`skills/seo-scan/references/` (`technical-seo.md`, `content-eeat.md`,
`schema.md`, `geo-llmo.md`). Read the relevant file when the user wants detail.

## Guardrails
- **SSRF-safe by default:** URLs resolving to private/loopback IPs are rejected.
  Only pass `--allow-private` for intentional local/staging scans.
- **Local-only:** no external accounts or APIs are called by default.
