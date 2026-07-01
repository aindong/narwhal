# Narwhal Roadmap

This is the planning source of truth for where Narwhal is headed. Each item links
to its tracking issue — issues hold the detailed tasks and acceptance criteria;
this page is the map.

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

## 🔴 P0 — Foundation

- ⬜ **CI on GitHub Actions** — run the test suite across Python 3.8–3.12, with and
  without optional deps; add a status badge. — [#1](https://github.com/aindong/narwhal/issues/1)
- ⬜ **v1.0.0 tag + Release** — pin the plugin version for reproducible installs.
  — [#2](https://github.com/aindong/narwhal/issues/2)

## 🟠 P1 — High-leverage features

- ⬜ **`--fail-under <score>` exit code** — use Narwhal as a CI quality gate.
  — [#3](https://github.com/aindong/narwhal/issues/3)
- ⬜ **Unified `narwhal` CLI + PyPI packaging** — one entrypoint (`scan`/`crawl`/
  `schema`), `pipx install`. — [#4](https://github.com/aindong/narwhal/issues/4)
- ⬜ **Polite crawler** — honor robots.txt, rate-limit, bounded concurrency,
  caching. — [#5](https://github.com/aindong/narwhal/issues/5)
- ⬜ **Robust robots.txt matching** — wildcards + Allow/Disallow precedence; report
  which paths are blocked per agent. — [#6](https://github.com/aindong/narwhal/issues/6)
- ⬜ **Broken-link checker** — internal + external, grouped by source page.
  — [#7](https://github.com/aindong/narwhal/issues/7)
- ⬜ **Deeper sitemap validation** — nested indexes, `lastmod`, 404 sampling.
  — [#8](https://github.com/aindong/narwhal/issues/8)
- ⬜ **Config file (`narwhal.toml`)** — thresholds, ignore rules, severity weights.
  — [#9](https://github.com/aindong/narwhal/issues/9)

### GEO & content depth
- ⬜ **`llms.txt` generator** — build a starter `/llms.txt` from sitemap + metadata.
  — [#10](https://github.com/aindong/narwhal/issues/10)
- ⬜ **Readability + entity extraction** — Flesch–Kincaid, top terms/entities,
  topical-focus check. — [#11](https://github.com/aindong/narwhal/issues/11)
- ⬜ **Duplicate / near-duplicate detection** — shingling/SimHash across a crawl;
  flag dupes missing canonical. — [#12](https://github.com/aindong/narwhal/issues/12)

## 🔵 P2 — Outputs & integrations

- ⬜ **HTML + PDF report export** — shareable, styled reports.
  — [#13](https://github.com/aindong/narwhal/issues/13)
- ⬜ **Scan diffing / regression tracking** — SQLite snapshots, compare runs.
  — [#14](https://github.com/aindong/narwhal/issues/14)
- ⬜ **PageSpeed/CrUX integration (opt-in)** — real Core Web Vitals field data.
  — [#15](https://github.com/aindong/narwhal/issues/15)
- ⬜ **Harden `--render` (Playwright)** — SPA fixtures, timeouts, clear errors, CI
  smoke test. — [#16](https://github.com/aindong/narwhal/issues/16)
- ⬜ **MCP server wrapper** — expose `scan_page` / `crawl_site` / `generate_schema`
  as MCP tools. — [#17](https://github.com/aindong/narwhal/issues/17)
- ⬜ **Dark-mode logo + README `<picture>`** — high-contrast in both themes.
  — [#18](https://github.com/aindong/narwhal/issues/18)

---

## Ideas / not yet ticketed

Captured here so they aren't lost; promote to an issue when scoped.

- Microdata / RDFa parsing (not just JSON-LD) in the schema auditor.
- Open Graph image validation (fetch, dimensions, aspect ratio).
- Image weight / next-gen-format checks (needs fetching images).
- Accessibility overlaps with SEO (lang, alt, heading order) as an optional lens.
- Hreflang return-tag validation across a full crawl (bidirectionality).
- Per-finding "learn more" deep links into the `references/` guides.

---

*Keep this file in sync when issues are opened, closed, or re-scoped. Issues remain
the detailed source of truth; this page is the high-level plan.*
