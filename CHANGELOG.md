# Changelog

All notable changes to Narwhal are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

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
