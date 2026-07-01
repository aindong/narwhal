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
| `python audit.py <url>` | Comprehensive site audit: homepage + crawl + sitemap in one report |
| `python scan.py <url>` | Audit one page → prioritized Markdown report |
| `python scan.py <url> --format json -o out.json` | Machine-readable output |
| `python scan.py <url> --format html -o report.html` | Self-contained, styled HTML report (also on `audit.py`) |
| `python scan.py <url> --format pdf -o report.pdf` | PDF report (needs WeasyPrint; falls back to HTML) |
| `python diff_scan.py old.json new.json` | Diff two JSON reports: score delta, new/resolved/worsened findings |
| `python diff_scan.py old.json new.json --fail-on-regression` | CI gate: exit non-zero if score dropped or a new critical/high appeared |
| `python render_report.py report.md -o report.html` | Render any Markdown report as branded HTML (`--format pdf` for PDF) |
| `python crux.py <url> --crux-key KEY` | Real Core Web Vitals (LCP/INP/CLS) from the CrUX API — opt-in field data, needs a key |
| `python crux.py <url> --lab` | PageSpeed Insights (Lighthouse) LAB metrics for any URL (use when CrUX has no data); key optional |
| `narwhal mcp` (needs `pip install "narwhal-seo[mcp]"`) | Run as an MCP server: exposes scan_page/crawl_site/audit_site/validate_sitemap/generate_llms/generate_schema/diff_reports over stdio |
| `python scan.py <url> --render` | Render JS (SPAs) via Playwright if installed |
| `python scan.py <url> --only technical,geo` | Run a subset of auditors |
| `python scan.py <url> --fail-under 80` | Exit non-zero below a score (CI quality gate) |
| `python crawl_site.py <url> --max-pages 25` | Site-wide scan + recurring-issue rollup |
| `python crawl_site.py <url> --concurrency 4 --delay 0.5` | Polite crawl: honors robots.txt, parallel, rate-limited |
| `python crawl_site.py <url> --check-links` | Also check outbound links (internal + external) for 4xx/5xx/dead |
| `python crawl_site.py <url>` | Also detects near-duplicate content by default (`--no-dupes`, `--dup-threshold`) |
| `python generate_schema.py <Type> --field k=v …` | Emit valid schema.org JSON-LD |
| `python generate_schema.py --list` | List supported schema types |
| `python validate_sitemap.py <url> --sample 20` | Validate XML sitemap(s): indexes, lastmod, 404 sampling, gzip |
| `python generate_llms.py <url> -o llms.txt` | Generate a starter llms.txt (curate before publishing) |

Auditor names: `technical`, `content`, `schema`, `geo`.
Unified CLI subcommands: `narwhal audit|scan|crawl|schema|sitemap|llms`.

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

## Fix loop (audit → edit → prove it)
When the site's **source is in the current workspace**, close the loop instead of
stopping at the report:
1. Baseline: `python scan.py <url> --format json -o before.json`.
2. Map each finding to the owning file (layout `<head>` for title/meta/canonical/
   OG, page source for alt/headings, static dir for robots.txt) and apply minimal,
   framework-idiomatic edits. Use `generate_schema.py` / `generate_llms.py` for
   generated artifacts.
3. Re-scan a local preview (`--allow-private`) as `after.json`, then
   `python diff_scan.py before.json after.json` to show resolved findings + delta.

Honesty: a localhost re-scan verifies **page-level** fixes only — mark site-level
signals (robots.txt, sitemap, HTTPS, canonical host, llms.txt) *verify after
deploy*; with no local preview, report "applied, pending deploy" + the re-scan
commands. Source not in the workspace → **no edits**, emit a per-finding fix plan.
Findings unreachable from the repo go in a "needs manual action" list.

## Multi-agent deep audit (Claude Code)
`/narwhal audit <site>` runs the deterministic `audit.py` baseline, then fans out
~10 specialist subagents in parallel (defined in `agents/`: technical, content,
schema, geo, performance, links, duplication, sitemap, sxo, + local when relevant),
and synthesizes an SEO Health Score + prioritized action plan. Each agent uses the
scripts above as its tools and adds reasoning on top.

## Configuration
An optional `narwhal.toml` (auto-discovered from the project root) tunes scoring
weights, thresholds, CLI defaults, and ignore rules. Precedence: CLI > config >
default. Use `--config PATH` / `--no-config`. See `docs/CONFIG.md` and
`narwhal.example.toml`.

## Deeper guidance
The reasoning and thresholds behind each check are in
`skills/seo-scan/references/` (`technical-seo.md`, `content-eeat.md`,
`schema.md`, `geo-llmo.md`). Read the relevant file when the user wants detail.

## Guardrails
- **SSRF-safe by default:** URLs resolving to private/loopback IPs are rejected.
  Only pass `--allow-private` for intentional local/staging scans.
- **Local-only:** no external accounts or APIs are called by default.
