---
description: Run a Narwhal SEO & GEO/LLMO audit, scan, crawl, or generator on a site
argument-hint: <audit|fix|gsc|compare|scan|crawl|sitemap|llms|schema|vitals|diff|render> <site>
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
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/audit.py" $2 --vitals --gsc --format json -o narwhal-audit.json
```
This gives homepage + site-wide + sitemap data, per-area subscores, broken links,
and duplicate clusters. `--vitals` also fetches **real Core Web Vitals** — CrUX
field data (if `CRUX_API_KEY` is set), falling back to PageSpeed Insights **lab**
data for low-traffic sites (see `vitals` below for keys); it lands in
`narwhal-audit.json` under `vitals`. `--gsc` folds in **real Search Console query
data** under `gsc` when GSC credentials are set (see `gsc` below) — striking-
distance queries, CTR laggards, decaying pages, cannibalization; without
credentials it degrades to a note, and the rest of the audit is unaffected. Skim
the JSON to detect the **business type** (SaaS, publisher, e-commerce,
local/brick-and-mortar, directory/people-search…).

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
  a rough effort tag. Call out fixes that resolve several findings at once. When the
  baseline has a `gsc` block, let **real search data outrank severity guesswork**:
  striking-distance pages become quick wins, CTR laggards become title/meta
  rewrites, decaying pages get urgency, and cannibalization pairs with the
  duplication findings (consolidate/canonicalize). Cite the actual queries and
  numbers. Without a `gsc` block, note once that GSC credentials
  (`/narwhal gsc --auth`) unlock data-driven prioritization and move on.
- **Quick wins** — low-effort, high-impact.
- **Core Web Vitals** — the field/lab verdict from Step 2b.
- **Per-area detail** — one concise section per specialist.

**Honor the specialists' discounts.** Specialists return a *Discounted script
findings* section (page-type artifacts, verified false positives, deliberate owner
choices like intentional AI-crawler opt-outs). Do **not** re-add those to the
action plan from the raw baseline JSON — the specialist's judgment overrides the
script. If one specialist marks something a deliberate choice (e.g. "do not
'fix'"), no other area's recommendation may contradict it.

**Step 4 — Deliver the branded report file.** Write the synthesized report to
`narwhal-audit-report.md`, then render it into a **self-contained, branded HTML
report** (Narwhal logo + styling, containing *your* synthesis) — HTML needs no
extra tools and opens anywhere:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/render_report.py" narwhal-audit-report.md --subtitle "$2" -o narwhal-audit-report.html
```
Tell the user the file path. Only produce a **PDF** if they ask (add `--format pdf
-o narwhal-audit-report.pdf`) — it needs a rendering engine (WeasyPrint or
Playwright's Chromium) and falls back to HTML otherwise. The HTML is shareable as
is, and can be opened and *Printed → Save as PDF* from any browser.

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

## If `$1` is `fix` → close the audit → fix loop

Apply the findings as real code edits in the current workspace, then re-scan and
diff to **prove** the score moved. Never claim improvement without a diff.

**Step 1 — Baseline.** If a fresh scan/audit JSON for `$2` already exists in the
CWD (e.g. `narwhal-audit.json` from a recent `/narwhal audit`), reuse it.
Otherwise run:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/scan.py" $2 --format json -o narwhal-fix-before.json
```

**Step 2 — Confirm the source is here.** Verify the current workspace contains
the site's source: grep for distinctive strings the scan saw (the `<title>`, a
heading, the meta description). If it does **not**, make **no edits** — output a
per-finding fix plan instead (for each finding: what file/artifact to change and
the exact snippet to add) and stop.

**Step 3 — Map findings → edits.** Work through the baseline findings, critical
→ high → medium. If the baseline JSON has a `gsc` block, **order the work by
search opportunity first**: pages appearing in `striking` and `laggards` get
fixed before pages with no search data (a title rewrite on a page-2 query beats
a meta fix on a page nobody searches for). For each finding, find the file that
owns the artifact and decide the concrete edit. Typical mappings:
- **title / meta description / canonical / OG & Twitter tags / hreflang** → the
  head: layout or per-page front-matter/metadata (Next `metadata` export, Astro/
  Hugo/Jekyll layout partial, or the raw `<head>` in plain HTML).
- **Missing/invalid JSON-LD** → generate it, don't hand-write:
  `python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/generate_schema.py" <Type> --field …`
- **Image alt text, heading structure, thin/direct-answer intro, question
  headings** → the page/component source or content Markdown.
- **robots.txt / AI-crawler access** → the static robots.txt (or its template).
- **Missing llms.txt** → `python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/generate_llms.py" $2 -o <static-dir>/llms.txt`, then curate its TODOs.

Anything unreachable from this repo (server/CDN redirect config, DNS, real Core
Web Vitals, an external service) goes in a **"needs manual action"** list —
never silently dropped.

**Step 4 — Apply.** Make the edits, minimal and idiomatic to the detected
framework (Next/Nuxt/Astro/Hugo/Jekyll/plain HTML…). Keep a list of every file
touched. Do not commit — the user reviews via git.

**Step 5 — Verify.** If the site can be previewed locally (dev server, or a
static build via `python -m http.server`), re-scan the local URL and diff:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/scan.py" http://localhost:<port>/<page> --allow-private --format json -o narwhal-fix-after.json
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/diff_scan.py" narwhal-fix-before.json narwhal-fix-after.json
```
(diff against whichever baseline Step 1 used — `narwhal-fix-before.json` or the
reused audit JSON.)

**Honesty rule:** a localhost scan verifies **page-level** fixes (title, meta,
schema, alt, OG, headings). **Site-level** signals — robots.txt, sitemap, HTTPS,
canonical host, llms.txt — come from the *local server's* origin, not the
deployed site, so label those **verify after deploy**, not fixed or regressed.
In a prod-baseline → localhost-after diff, expect the raw verdict to say
"Regressed" with new critical/high findings like "not served over HTTPS" / "no
robots.txt" / "no sitemap" — those are localhost artifacts; discount them and
judge by the page-level findings that resolved. If no local preview is possible,
report **"applied, pending deploy"** and give the exact re-scan + diff commands
to run post-deploy.

**Step 6 — Report.** Deliver: the score delta (or "pending deploy"), findings
resolved (from the diff), files changed, the verify-after-deploy list, and the
manual-action list. Never fabricate a score.

---

## Otherwise → run the matching tool and report back

| `$1` | Run | Then |
|---|---|---|
| `scan` | `scan.py $2` | full single-page audit report |
| `compare` | `compare.py $2 $3 [$4 $5]` | side-by-side competitor gap analysis — `$2` is the user's page, the rest are competitors; leads with "gaps to close". Local-first: on-page differences only, never claim it explains rankings |
| `crawl` | `crawl_site.py $2 --check-links` | site-wide (broken links + dupes) |
| `sitemap` | `validate_sitemap.py $2` | validate XML sitemap(s) |
| `llms` | `generate_llms.py $2 -o llms.txt` | generate a starter llms.txt |
| `schema` | `generate_schema.py $2 …` | here `$2` is the schema **Type** (e.g. Article) |
| `vitals` | `crux.py $2` | **real** Core Web Vitals (LCP/INP/CLS) from CrUX — see key note below |
| `gsc` | `gsc.py $2` | **real** Search Console query data: striking distance, CTR laggards, decaying pages, cannibalization — see the OAuth note below |
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

**`gsc` — OAuth, not an API key:** this action calls Google's Search Console API
for the user's **own verified property** (read-only). Credentials resolve from
env or `.env`, in order: `GSC_ACCESS_TOKEN` (e.g. `gcloud auth
print-access-token`; expires ~1h) or the durable
`GSC_CLIENT_ID`/`GSC_CLIENT_SECRET`/`GSC_REFRESH_TOKEN` trio. If they're missing,
relay the one-time setup: create a **Desktop** OAuth client in Google Cloud
Console (enable the "Google Search Console API"), put the client ID/secret in
`.env`, then run `gsc.py --auth --write-env` — it opens the browser consent page
and stores the refresh token. Useful flags: `--days N` (window, default 28),
`--min-impressions N`, `--format json`. The numbers are real search data — never
supplement them with guessed ones; the expected-CTR curve in the laggards table
is a labeled heuristic used only for ranking.

Edge cases: if `$1` is empty/unrecognized, treat it as `audit`. If `$2` (the site) is
missing, ask for it. Only add `--allow-private` for local/staging targets.
