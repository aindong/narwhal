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
- `--render` — render JavaScript with Playwright and compare paired served/
  rendered snapshots: selected-text equality, whitespace-token deltas, headings
  and metadata presence/block counts. `js_dependence.text_comparison` records
  scope; legacy `js_only_pct` is a positive net count delta, not JS-only content.
  Equal counts can hide replacement text. Review differences manually before
  SSR/metadata edits; do not infer JS causation, crawler access or citation impact.
  Missing legacy receipts do not certify content parity or server rendering.
- `--format json|html|pdf` — machine-readable JSON, a self-contained styled HTML
  report, or PDF (needs WeasyPrint; falls back to HTML). Use `-o <file>` to save.
  `html`/`pdf` also work on `audit.py` for a shareable, stakeholder-ready report.
- `--only technical,geo` — run a subset: `technical`, `content`, `schema`, `geo`.
  Unknown names and empty comma-separated entries fail before fetching (CLI exit
  2); MCP follows the same rule. Omitted/empty selection runs all four.
- Image checks run by default on single-page scans (a few HEADs + one ~64 KB
  ranged GET): heavy images (>200 KB), legacy formats worth AVIF/WebP, missing
  width/height (CLS), and og:image validation (reachable? real dimensions?).
  Skip with `--no-image-checks`; crawls skip them automatically.
- The schema auditor conditionally applies a merchant bar to evidenced product
  pages: Product/Offer completeness, ProductGroup variants, expired prices, and
  explicit visible-vs-schema price/currency/availability/SKU/brand consistency.
  Ordinary pages and editorial Product reviews are not treated as stores.
- `--fail-under N` — exit non-zero if the score is below `N` (CI quality gate;
  `crawl_site.py` gates on the average score).

**Compare against competitors** (local-first — your page first, then 1-3
competitor pages; same auditors run on each, then a gap analysis):
```
python scripts/compare.py https://you.com/page https://rival.com/page
```
Reports a scoreboard, a side-by-side fact table, **"Gaps to close"** (what they
have that you don't: schema types, meta strategy, question headings,
social packaging) and **"Where you lead"**. Honesty rule: it compares
the recorded HTML snapshots (served or rendered, as labelled) — never claim a
gap explains rankings. Text length is a neutral whitespace-token observation,
not a depth gap/lead or writing target. Legacy `words` values without a recorded
basis stay unverified. No rank/keyword data is used or implied.
Statistic/citation-pattern counts are likewise observations, not verified sources
or evidence-density gaps. `evidence_cues` explains the basis and unchecked source
validity; legacy `stats_cites` alone does not supply a measurement basis.
Question-heading differences are optional contextual reviews using exact
`question_cues` counts, not the preserved rounded `question_ratio`. The one-in-five
heuristic does not establish real queries or engine matching; keep useful
descriptive headings and use questions only when helpful. Missing counts/basis
and no eligible headings are not interpreted as a measured low fraction.
`schema_search_features` carries a dated Google retirement snapshot; it is not
schema.org validation or live eligibility. Retired Google appearances do not
require deleting accurate semantic markup. Unlisted types are not certified
eligible, and missing legacy snapshot provenance stays unverified.
`schema_extraction` records supported-extractor errors/warning-detail counts.
Known problems or missing receipts cannot certify schema absence. Keep observed
types visible, inspect existing markup before adding/duplicating a candidate,
and do not claim schema/overall score gains from unverified extraction. A
`no_known_problem` receipt is not full conformance/eligibility or exhaustive coverage.
`date_cues` records bounded metadata/selected-text candidates, not validated
publication/update dates or freshness. Modified-only metadata counts; blank values
and bare years alone do not. Review real page purpose and known dates when useful;
never invent dates, relabel event dates or cosmetically refresh them to clear a
finding. Compared candidates do not impose a date quota. See the
[date-cue boundaries](references/content-eeat.md#date-cues-not-freshness-verification).

**Build a data-driven content brief** (what to *write*, grounded in real data —
no keyword APIs, no invented volumes):
```
python scripts/brief.py https://you.com/page https://rival.com/page
python scripts/brief.py --topic "widget calibration" https://rival.com/guide
```
Combines the page's own **striking-distance GSC queries** (positions 8–20 —
demand it nearly satisfies; needs GSC credentials, same setup as `gsc.py`),
the **competitor gap analysis**, **compared-heading review candidates** (a lexical
H2/H3 term filter, not verified missing semantic coverage), **question-shaped candidates**
(compared headings + your recorded question-shaped queries, distinguished by
`source_kind`; legacy missing kinds stay unverified), schema suggestions,
and a question-heading structure heuristic on non-hubs.
Review candidates for actual relevance and coverage; neither compared headings
nor a structure flag require rewriting headings or forcing a first-sentence answer.
Keep deliberate user/editorial format choices separate from measured cues.
The legacy `missing_subtopics` field keeps review candidates, not absence verdicts.
`subtopic_review` and per-candidate `term_match` record the ASCII/English prefix-term
basis and exact counts/cutoff. Synonyms can be missed and unrelated words can match;
compared headings do not prove section content. Topic mode has no own-page matches.
Missing/malformed legacy receipts stay unrecorded; inspect relevance and existing
coverage before recommending sections, without overriding explicit editorial choices.
`text_length` contains neutral length observations, including hubs; do not infer
a word target or missing coverage from length alone. Keep explicit user/editorial
length constraints separate from measured observations. Citation/statistic cues
do not establish factual support or a source quota; review real claims and
sources without inventing numbers/citations to satisfy counts.
`target_words`/`your_words` and `evidence_target`/`your_evidence` are no longer
generated. `--topic` mode
plans a page that doesn't exist yet from
competitor pages only (add `--gsc-site <your-site>` to fold in real adjacent
queries). Without GSC credentials it produces a clearly labeled
**structure-only** brief — target queries are omitted, never invented.
Schema candidates carry `google_search_appearance` notes from that same dated
snapshot. Keep semantic generators available, but add only actual visible
content for the intended consumer; a competitor's type or a question candidate
does not establish validity, eligibility or ranking/citation gains.
`/narwhal brief` layers an editorial synthesis (outline, metadata drafts) on
top of this data.

**Audit a whole site** (discovers URLs via sitemap or internal links, rolls up
the issues that recur most — the highest-leverage fixes):
```
python scripts/crawl_site.py https://example.com --max-pages 25
```
The crawler is polite by default: it **honors robots.txt** (skips disallowed URLs;
reported in the summary), fetches site-level signals once, and scans pages in
parallel. Tune with `--concurrency N` (default 4), `--delay SECONDS` (minimum
spacing of parallel page-scan starts; sequential post-scan pause), and
`--ignore-robots` to override. Delay must be finite and nonnegative; it does not
pace discovery, site resources or optional probes. Crawl/audit page and worker
limits must be positive integers (including config defaults); invalid limits
fail before fetching with CLI exit 2. Link and sitemap file/sample caps require
nonnegative integers; zero retains scoped optional-check skips, not an all-network
off switch. Consumed config defaults follow the same preflight. MCP retains its
page/worker clamps. Sitemap probes sample distinct exact URL strings at evenly
spaced positions in parsed-file order (endpoints when selecting at least two;
one selects the first). JSON/Markdown record the policy. This bounded sample is
not random or representative; changed selection is not evidence of a site change. `--fail-under N` gates on the
average score. Add `--check-links` to check outbound links (internal + external)
for 4xx/5xx/dead — reported grouped by source page (`--max-links N` caps how many;
rate-limited/bot-blocked codes like 429/403 are treated as gated, not broken).
**Hreflang reciprocity** is validated automatically when the site uses
hreflang: missing return tags reported as exact A → B pairs, missing
self-references, invalid codes, x-default presence; up to 5 same-host
alternates are probed so return tags are verifiable, and anything outside
the sample is labeled unverified — never broken.
**Site-structure analysis** is always included: click depth from the start
URL, pages unreachable within the sample, zero-inbound pages (weak link
equity), most-linked pages, and sitemap **orphan candidates** — all
sample-aware (the report states the crawl size next to every claim).
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
if the score dropped, a new critical/high finding appeared, or an existing
finding escalated to critical/high (even with an offsetting score improvement).
Known incomparable coverage also fails the gate. Add `--require-comparable`
to reject unknown legacy coverage with exit 2; planner commands use both flags.
Comparability covers recorded checks only, not unrecorded settings or a whole site. Different complete recorded
audit crawl URL samples (including multiplicities) withhold verdicts and exit 2;
order does not matter. Missing/malformed legacy samples stay unverified.
Works on `audit` JSON too (overall score + homepage findings). Separate
`crawl_rule_changes` compares native recurring rules only with matching recorded
coverage and nonempty exact crawl samples. New critical/high rules and severity
escalations trigger the regression gate even without a score drop. Removed rules
mean no longer observed in that sample, not per-page fixes or complete site
coverage. Missing, legacy or unsupported rollups remain explicitly unverified.
For audits, `--require-comparable` also requires a verified crawl-rule comparison;
missing/unsupported rollups or absent/empty crawl samples exit 2. Ordinary viewing
and the non-strict regression flag retain legacy behavior with a warning.

**Map findings to source before editing** (read-only, no changes applied):
```
python scripts/plan.py before.json --repo .
python scripts/plan.py before.json --repo . --format json -o plan.json
```
The versioned plan detects plain HTML, Next.js, Astro, Nuxt, Hugo, or Jekyll;
links stable finding IDs to likely owning files; groups shared-template fixes;
and separates safe candidates, review-required work, external/manual work, and
changes that require post-deploy verification. Treat file matches as evidence-
backed candidates, not permission to edit blindly; inspect warnings and conflicts.
Fresh crawl/audit JSON includes up to five sorted, distinct URL-label witnesses
per recurring rule observation, with truncation/omission receipts. They use the
recorded final URL when present and otherwise the requested label, not proof of
response destinations, successful access or the full affected-page set. Counts
and scores are unchanged. Labels over 4,096 characters and shared credential-like
markers are omitted from these samples, not truncated into new URLs. For recurring page-local actions, plans use supported
same-origin witnesses to locate inventoried route sources instead of a healthy
homepage fallback. Unsupported/legacy unlocated rollups require manual source
confirmation or a fresh audit; shared-framework head candidates remain heuristic.
Viewport automation eligibility is blocked by `unlocated_page_witness` when any
recorded page label has no inventoried source candidate, even if others do.
Next.js page candidates include observed default-extension sources and Pages
Router directory indexes under `app/`, `pages/`, or `src/`. Dynamic routes,
rewrites and custom page extensions still need manual ownership confirmation.
Next.js robots/sitemap candidates include observed JavaScript and static app
metadata files alongside TypeScript/public owners. Inspect the actual source
before edits and verify the generated resource after deploy.
Astro candidates include observed `.astro`, `.md`, `.mdx` and `.html` root,
direct and directory-index pages in `src/pages/`. Confirm MDX integration,
dynamic routes and content-collection ownership manually before editing.
Nuxt candidates include observed `app/pages/` routes alongside legacy `pages/`,
including root and directory-index Vue files. Confirm custom source directories,
layers, route overrides and actual page ownership manually.
Hugo candidates include observed home/section `_index.md` branch bundles under
`content/`. Confirm custom content roots, multilingual layouts, URL overrides
and permalinks before choosing an owner.
Owner previews label inventory status and disclose candidates beyond the first
three; the complete list remains in plan JSON. Uninventoried paths are not proven
missing, and inventoried files are not proven active source owners.
Owner and related-action path previews use literal code spans, including names
with backticks or Markdown punctuation; original path strings remain in JSON.
Markdown evidence previews are literal, capped at 600 characters and not
reverified; full action evidence remains in JSON. Synthesized sitemap failure
actions retain the first five reported status/URL witnesses and their total.
Consult the original report for remaining witnesses and verify before editing.
Sitemap sample reporting/planning uses the shared crawl HTTP classification;
unsupported statuses or malformed/error fields remain unverified even when raw
compatibility problem rows retain them. JSON includes selected-target response
counts beside the raw observations.
Audit crawl link failures and uncertain/capped/unknown coverage produce separate
manual actions with bounded target/source witnesses. They assign no source owner
or automatic link edit; verify HEAD/GET behavior and anchor intent first. New
`crawl.links.unverified` records preserve checked uncertain targets and referrers
for that follow-up. Crawl Markdown shows up to 20 rows with bounded URL previews;
JSON retains all checked records. Legacy missing identities are not inferred.

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
same look as the scan/audit reports. Scan/audit/render require regular output
files and return exit 2 for expected delivery failures. Other CLI text artifact
saves use the same regular-file/UTF-8 checks and preserve analysis gate codes; PDF engine bytes are
staged first. Final writes remain non-atomic. Choose an output file distinct from
the source; direct/link aliases are rejected for HTML, PDF and actual fallback
HTML writes. PDF bytes are staged first; separate final writes remain non-atomic.
Avoid redirecting stdout over the input (the shell truncates before Narwhal runs).

## What each auditor covers

| Auditor | Focus |
|---|---|
| `technical` | title/meta, headings, canonical, robots directives, viewport, hreflang, images, links, HTTP hygiene, robots.txt, sitemap |
| `content` | scoped text-length/readability cues, attribution/date candidates, Open Graph/Twitter cards |
| `schema` | JSON-LD detection, required/recommended property validation, deprecated rich-result types |
| `geo` | contextual question-heading, synthetic sentence-group, statistic/citation and intro cues; `llms.txt`, role-aware **AI-crawler policies** |

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
Known structured-data extraction uncertainty also prevents page/audit diff
improvement/resolution verdicts; the CI gate exits 2, including uncertain crawl
contributions. Fix/verify extraction before treating missing findings as fixes.
Page scans with known extraction gaps withhold generic/Article/site-entity/Product
absence advice while retaining checks on observed nodes. Plans make extraction
verification manual-only, not markup-generation work; actual syntax/property
repairs remain reviewable. Even without known errors, non-observation is only a
conditional review: preserve valid formats/entities and do not promise eligibility.
JSON decoder syntax errors remain repair candidates. JSON-LD decoder limits,
numeric/Unicode handling or node-processing failures are verification-only, not
proof of invalid source or engine rejection. `jsonld_error_stages` records actual
runtime counts; missing legacy stages stay unclassified. Verify before rewriting
data, and do not increase global parser/body limits just to clear a note.
`meta.readability` exposes historical ASCII-token, punctuation-fragment and
vowel-group inputs with English-oriented Flesch/FK formula estimates, not actual
comprehension, school grade or engine citability. Non-English declarations,
non-ASCII letters/marks, hub hints and unusable inputs leave interpretation
unassessed. Keep useful concise/specialist text and necessary precision; simplify
only where useful for the actual audience, not to meet a universal score/word quota.
Current/legacy plans use the same conditional review. Known changes in recorded
`readability_reviewed` scope make page/audit/crawl diffs incomparable, not fixes;
missing legacy scope stays unknown. See `references/content-eeat.md#readability`.
`meta.lexical_focus` records top-eight ASCII-term frequency and exact title/first-H1
overlap, not dominant topics or semantic coverage. Cutoffs/ties, synonyms,
inflections and extraction can hide matches; incidental overlap is not relevance.
Review actual page purpose/wording and edit only confirmed misleading labels or
missing useful content, without keyword stuffing or forced overlap. Legacy IDs
remain; missing receipts do not supply measured scope. See
`references/content-eeat.md#topical-focus` for witnesses, limits and compatibility.

## Deep audit (multi-agent)

For a comprehensive audit, `/narwhal audit <site>` runs the deterministic
`audit.py` baseline and then fans out ~10 specialist subagents in parallel (in the
plugin's `agents/` dir) — technical, content, schema, geo, performance, links,
duplication, sitemap, sxo, local, and conditional e-commerce — each using these scripts as tools and adding
reasoning + exact fixes, synthesized into one prioritized report. The individual
scripts above remain the fast, deterministic path.

## Fix loop (audit → edit → prove it)

When the site's **source code is in the current workspace**, don't stop at the
report — close the loop (`/narwhal fix <url>` in Claude Code):

1. Save a baseline: `python scripts/scan.py <url> --format json -o before.json`
   (or reuse a fresh audit JSON).
2. Run `python scripts/plan.py before.json --repo . --format json -o plan.json`.
   Review its likely owners, safety classes, conflicts, and coverage, then apply
   minimal, framework-idiomatic edits. Use
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
