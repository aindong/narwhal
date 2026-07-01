---
description: Run a Narwhal SEO & GEO/LLMO audit, scan, crawl, or generator on a site
argument-hint: <audit|scan|crawl|sitemap|llms|schema|vitals|diff|render> <site>
---

# Narwhal — SEO & GEO/LLMO

The user ran: `/narwhal $ARGUMENTS`

- **Action:** `$1`
- **Target:** `$2`

## How to run the deterministic tools
Prefer the plugin's local scripts:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/<script>" <args>
```
Fallback (needs `uv`): `uvx --from git+https://github.com/aindong/narwhal narwhal <action> <args>`.
They are local-first and SSRF-safe; only `vitals` (CrUX field data) needs an API
key. Respect any `narwhal.toml`.

---

## If `$1` is `audit` → run the parallel multi-agent deep audit

This is the flagship. Produce a comprehensive, prioritized SEO + GEO audit by
combining deterministic measurement with specialist reasoning.

**Step 1 — Deterministic baseline (hard data, fast).** Run:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/audit.py" $2 --vitals --format json -o narwhal-audit.json
```
This gives homepage + site-wide + sitemap data, per-area subscores, broken links,
and duplicate clusters. `--vitals` also fetches **real Core Web Vitals** — CrUX
field data (if `CRUX_API_KEY` is set), falling back to PageSpeed Insights **lab**
data for low-traffic sites (see `vitals` below for keys); it lands in
`narwhal-audit.json` under `vitals`. Skim it to detect the **business type** (SaaS,
publisher, e-commerce, local/brick-and-mortar, directory/people-search…).

**Step 2 — Fan out specialists IN PARALLEL.** In a *single message*, spawn these
subagents with the Task tool (pass each the URL `$2` and the path `narwhal-audit.json`):
- **Always:** `narwhal-technical`, `narwhal-content`, `narwhal-schema`,
  `narwhal-geo`, `narwhal-performance`, `narwhal-links`, `narwhal-duplication`,
  `narwhal-sitemap`, `narwhal-sxo`
- **Conditional:** `narwhal-local` — only when Step 1 indicates a local / service-area
  business.

Each returns a domain score + prioritized findings with exact fixes.

**Step 2b — Core Web Vitals.** The `vitals` block is already in
`narwhal-audit.json` from Step 1's `--vitals` (CrUX field, or PSI lab fallback).
Fold its verdict into the performance section. Label it correctly — **field**
(real users, CrUX) vs **lab** (synthetic, PSI) — and never fabricate numbers. If
`vitals` came back empty (no key at all), note that setting `CRUX_API_KEY` /
`PAGESPEED_API_KEY` unlocks it and move on.

**Step 3 — Synthesize one report.** Merge the specialists into:
- **SEO Health Score (0–100)** — reconcile the deterministic scores with the
  specialists' judgment; explain the number in one sentence.
- **Executive summary** — business type, biggest risks, and the 3 highest-leverage moves.
- **Prioritized action plan** — Critical → High → Medium → Low, each with the fix and
  a rough effort tag. Call out fixes that resolve several findings at once.
- **Quick wins** — low-effort, high-impact.
- **Core Web Vitals** — the field/lab verdict from Step 2b.
- **Per-area detail** — one concise section per specialist.

**Step 4 — Deliver the branded report file.** Write the synthesized report to
`narwhal-audit-report.md`, then render it into a **self-contained, branded HTML
report** (Narwhal logo + styling, containing *your* synthesis):
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/render_report.py" narwhal-audit-report.md --subtitle "$2" -o narwhal-audit-report.html
```
Also try a **PDF** (add `--format pdf -o narwhal-audit-report.pdf`); it needs
WeasyPrint and prints a note + writes HTML instead if it's missing. Tell the user
the exact file path(s) produced, and that a PDF needs `pip install weasyprint`.

**Formatting (important):** write the report in plain **GitHub-flavored Markdown**
— `#`/`##` headings, `|`-delimited pipe tables, `-` bullet lists, `**bold**`. Do
**NOT** draw Unicode/ASCII box tables (`┌─┬─┐│└┘`) or fixed-width column art: they
corrupt in terminals and when streamed. Keep any table to ≤4 **narrow** columns; if
it would be wide, use a list instead. Produce one clean report — don't paste each
specialist's raw output verbatim.

Guardrails: never fabricate metrics. Real Core Web Vitals come from the `vitals`
action (CrUX) when a key is set — otherwise say so and treat perf as hygiene only.
Be honest where a claim needs an external tool. Keep the synthesis tight, not a
wall of raw output.

---

## Otherwise → run the matching tool and report back

| `$1` | Run | Then |
|---|---|---|
| `scan` | `scan.py $2` | full single-page audit report |
| `crawl` | `crawl_site.py $2 --check-links` | site-wide (broken links + dupes) |
| `sitemap` | `validate_sitemap.py $2` | validate XML sitemap(s) |
| `llms` | `generate_llms.py $2 -o llms.txt` | generate a starter llms.txt |
| `schema` | `generate_schema.py $2 …` | here `$2` is the schema **Type** (e.g. Article) |
| `vitals` | `crux.py $2` | **real** Core Web Vitals (LCP/INP/CLS) from CrUX — see key note below |
| `diff` | `diff_scan.py $2 $3` | compare two saved JSON reports (`$2`=old, `$3`=new); add `--fail-on-regression` for a gate |
| `render` | `render_report.py $2 -o report.html` | here `$2` is a Markdown file → branded HTML (`--format pdf` for PDF) |

Read the report back **in your own words, leading with the highest-severity fixes** —
summarize, don't paste everything.

**`vitals` — field vs lab, and API keys:** this action calls an external service.
Two data sources:
- **Field (default):** `crux.py $2` → real-user CrUX data. Needs `CRUX_API_KEY`
  (auto-resolved from env or a `.env`; if missing, relay the three ways to set it —
  `--crux-key`, the env var, or `.env` — and the free key link
  `https://developer.chrome.com/docs/crux/api`). Use `--origin` for the whole-site
  aggregate, `--form-factor phone|desktop|tablet` to narrow the device.
- **Lab (`--lab`):** `crux.py $2 --lab` → PageSpeed Insights (Lighthouse) synthetic
  metrics that work for **any URL regardless of traffic**. Use this when CrUX has
  **no data** (low-traffic pages). Key is optional but recommended
  (`PAGESPEED_API_KEY`, or reuse the CrUX key with the PageSpeed Insights API
  enabled) — keyless quota is shared and often exhausted. `--strategy mobile|desktop`.

Always label lab data as synthetic/estimate, never as real-user field data; never
guess numbers.

Edge cases: if `$1` is empty/unrecognized, treat it as `audit`. If `$2` (the site) is
missing, ask for it. Only add `--allow-private` for local/staging targets.
