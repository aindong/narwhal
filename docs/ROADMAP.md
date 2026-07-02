# Narwhal Roadmap

This is the planning source of truth for where Narwhal is headed. Each item links
to its tracking issue — issues hold the detailed tasks and acceptance criteria;
this page is the map.

> **Status (v1.19.0):** the original roadmap is **complete** — #1–#20 all closed,
> plus the beyond-roadmap features below (fix loop, GSC, branded reports, tuning
> rounds). Active planning now lives in the **[🌊 Next wave](#-next-wave-v2x--from-the-2026-07-project-review)**
> section: #21–#28. See [STATUS.md](STATUS.md) for the full snapshot.

> **Legend:** 🔴 P0 (foundation) · 🟠 P1 (high-leverage) · 🔵 P2 (later)
> **Status:** ⬜ planned · 🟡 in progress · ✅ done

## Guiding principles

Every item on this roadmap must preserve the four principles the tool is built on
(see [CONTRIBUTING.md](../CONTRIBUTING.md)):

1. **Local-first** — no external services on the default path; APIs are opt-in.
2. **Zero required dependencies** — everything runs on the Python stdlib; extras are auto-detected.
3. **SSRF-safe** — all fetching goes through the guarded HTTP layer.
4. **Fix-first, honest output** — lead with the action; never fabricate a metric we can't measure.

---

## Milestones

We group the work into release targets. Milestones are aspirational groupings, not
hard commitments.

| Release | Theme | Issues |
|---|---|---|
| **v1.0** | Shipped: 4 auditors, scan/crawl/schema, plugin install | — |
| **v1.1** | Foundation + core UX | #1, #2, #3, #4 |
| **v1.2** | Crawler depth + site-level intelligence | #5, #6, #7, #8, #9 |
| **v1.3** | GEO & content depth | #10, #11, #12 |
| **v2.0** | Outputs & integrations | #13, #14, #15, #16, #17, #18 |

---

## ✨ Beyond the original roadmap (shipped)

- ✅ **`/narwhal <action> <site>` command** + `audit` alias.
- ✅ **Audit-style report** — executive summary, per-area subscores, quick wins.
- ✅ **Comprehensive `audit`** — combined homepage + crawl + sitemap.
- ✅ **Multi-agent deep audit** — `/narwhal audit` fans out ~10 specialist subagents
  (`agents/`) in parallel over the deterministic baseline, then synthesizes a health
  score + prioritized action plan.

## 🔴 P0 — Foundation

- ✅ **CI on GitHub Actions** — test suite across Python 3.8–3.12 (+ Windows), with
  and without optional deps; status badge in the README. — [#1](https://github.com/aindong/narwhal/issues/1)
- ⬜ **v1.0.0 tag + Release** — pin the plugin version for reproducible installs.
  — [#2](https://github.com/aindong/narwhal/issues/2)

## 🟠 P1 — High-leverage features

- ✅ **`--fail-under <score>` exit code** — Narwhal as a CI quality gate (on both
  `scan.py` and `crawl_site.py`). — [#3](https://github.com/aindong/narwhal/issues/3)
- ✅ **Unified `narwhal` CLI + `uvx` packaging** — one entrypoint (`scan`/`crawl`/
  `schema`), runnable via `uvx --from git+…` with no install and no PyPI. PyPI
  publish is optional and deferred. — [#4](https://github.com/aindong/narwhal/issues/4)
- ✅ **Polite crawler** — honors robots.txt (skips disallowed URLs), bounded
  `--concurrency`, `--delay` rate-limit, site-level signals cached once per site,
  trailing-slash dedup. — [#5](https://github.com/aindong/narwhal/issues/5)
- ✅ **Robust robots.txt matching** — `lib/robots.py`: user-agent groups, `*`/`$`
  wildcards, longest-match with Allow-over-Disallow ties (RFC 9309). Powers the GEO
  AI-crawler check; reused by the crawler (#5). — [#6](https://github.com/aindong/narwhal/issues/6)
- ✅ **Broken-link checker** — `--check-links` on the crawler: HEAD-checks
  outbound links (internal + external) for 4xx/5xx/dead, grouped by source page;
  gated codes (401/403/429) treated as not-broken to avoid false positives.
  — [#7](https://github.com/aindong/narwhal/issues/7)
- ✅ **Deeper sitemap validation** — `narwhal sitemap`: recurses sitemap indexes,
  validates `loc` (absolute/same-host) and `lastmod` (W3C), samples URLs for 404s,
  gzip-aware, reports partial counts when capped. — [#8](https://github.com/aindong/narwhal/issues/8)
- ✅ **Config file (`narwhal.toml`)** — scoring weights, check thresholds, CLI
  defaults, and ignore rules; auto-discovered, `--config`/`--no-config`, CLI >
  config > default. Docs in `docs/CONFIG.md`. — [#9](https://github.com/aindong/narwhal/issues/9)

### GEO & content depth
- ✅ **`llms.txt` generator** — `narwhal llms`: builds a starter `/llms.txt` from
  the homepage + discovered pages, grouped into sections, TODO-marked, honest about
  its low-certainty benefit. — [#10](https://github.com/aindong/narwhal/issues/10)
- ✅ **Readability + entity extraction** — Flesch reading ease + FK grade in the
  content auditor, dominant terms/phrases + candidate entities, and a title/H1
  vs body topical-focus check. — [#11](https://github.com/aindong/narwhal/issues/11)
- ✅ **Duplicate / near-duplicate detection** — SimHash fingerprints across a
  crawl; clusters near-dupes by Hamming distance and flags clusters lacking a
  consistent canonical (`--dup-threshold`, `--no-dupes`). — [#12](https://github.com/aindong/narwhal/issues/12)

## 🔵 P2 — Outputs & integrations

- ✅ **HTML + PDF report export** — self-contained styled HTML (`--format html`,
  score gauge + severity cards) on `scan` and `audit`; PDF via WeasyPrint with
  graceful HTML fallback (`--format pdf`). — [#13](https://github.com/aindong/narwhal/issues/13)
- ✅ **Scan diffing / regression tracking** — `narwhal diff old.json new.json`:
  score delta + new/resolved/worsened/improved findings, `--fail-on-regression` CI
  gate. Database-free (diffs the JSON we already emit). — [#14](https://github.com/aindong/narwhal/issues/14)
- ✅ **CrUX integration (opt-in)** — `narwhal vitals`: real Core Web Vitals field
  data (LCP/INP/CLS at p75) from the Chrome UX Report API, gated behind an API key.
  Built against CrUX directly (PSI is dropping CrUX field data in 2026).
  — [#15](https://github.com/aindong/narwhal/issues/15)
- ✅ **Harden `--render` (Playwright)** — actionable missing-browser error, capped
  `networkidle` settle, guaranteed browser cleanup, honest render-failure errors,
  and a CI render-smoke that executes JS end to end. — [#16](https://github.com/aindong/narwhal/issues/16)
- ✅ **MCP server wrapper** — `narwhal mcp` exposes all auditors (scan/crawl/audit/
  sitemap/llms/schema/diff) as MCP tools over stdio (FastMCP; optional `mcp` extra).
  — [#17](https://github.com/aindong/narwhal/issues/17)
- ✅ **Dark-mode logo + README `<picture>`** — `assets/logo-dark.png`; README
  auto-swaps via `prefers-color-scheme`. Derived deterministically from the light
  logo (`assets/make-dark-logo.py`). — [#18](https://github.com/aindong/narwhal/issues/18)

---

## 🌊 Next wave (v2.x) — from the 2026-07 project review

The honest self-review after v1.19.0: Narwhal is a rigorous *auditor*; the next
wave adds the **relative** and **strategic** answers users actually ask for —
without breaking local-first (nothing below needs a paid API).

### P1 — high value, zero new dependencies
- ✅ **`narwhal compare`** — side-by-side competitor gap analysis from our own
  scans (scoreboard, fact table, gaps to close, where you lead; MCP tool
  `compare_pages`). — [#21](https://github.com/aindong/narwhal/issues/21)
- ✅ **Site-graph analysis** — click depth, orphan candidates, unreachable and
  zero-inbound pages, most-linked pages; always on in `crawl`/`audit`, sample-
  aware honesty. — [#22](https://github.com/aindong/narwhal/issues/22)
- ✅ **JS-dependence check** — `--render` diffs served HTML vs rendered DOM:
  JS-only content share (tiered findings), post-JS headings, client-injected
  metadata; GEO finding for AI fetchers. — [#23](https://github.com/aindong/narwhal/issues/23)
- ⬜ **Image weight/format + og:image validation.**
  — [#24](https://github.com/aindong/narwhal/issues/24)
- ⬜ **Hreflang bidirectional validation** across a crawl.
  — [#25](https://github.com/aindong/narwhal/issues/25)

### P2 — the strategy loop, done our way
- ⬜ **Content-brief flow** — briefs grounded in real GSC queries + the compare
  gap, not fabricated volumes. — [#26](https://github.com/aindong/narwhal/issues/26)
- ⬜ **E-commerce checks** — Product/offers completeness, page-vs-schema
  mismatches, conditional store specialist.
  — [#27](https://github.com/aindong/narwhal/issues/27)

### P3 — internal quality
- ⬜ **Test-suite health** — split the monolith, golden-file report tests.
  — [#28](https://github.com/aindong/narwhal/issues/28)

---

## Ideas / not yet ticketed

Captured here so they aren't lost; promote to an issue when scoped.

- Microdata / RDFa parsing (not just JSON-LD) in the schema auditor.
- Accessibility overlaps with SEO (lang, alt, heading order) as an optional lens.
- Per-finding "learn more" deep links into the `references/` guides.
- Single-source the version (today it's synced across 5 files by hand).

---

*Keep this file in sync when issues are opened, closed, or re-scoped. Issues remain
the detailed source of truth; this page is the high-level plan.*
