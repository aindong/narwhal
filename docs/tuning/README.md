# How Narwhal is tuned

Narwhal's checks and specialist agents aren't written once and trusted forever —
they're **tuned against the real web**, and the evidence is committed here so you
can audit the auditor. Each round follows the same loop:

```
1. SWEEP     scan a diverse batch of real, public sites (JSON snapshots saved)
2. DIFF      read every critical/high/medium finding looking for false positives
             — a well-run site scoring poorly is a smell in OUR tool, not theirs
3. FIX       repair the root cause in the deterministic scripts
             (parser/extraction/check logic), never by hiding findings
4. PROVE     re-scan the same sites; every score change must come from removing
             *wrong* findings, with a regression test locking each one in
5. GRADE     run the actual specialist agents on live sites and grade their
             reasoning — do they correct the script, or parrot it?
6. ENCODE    turn what the good runs did into permanent "Judgment rules" in
             the agents/narwhal-*.md prompts
```

Two principles keep the loop honest:

- **Never loosen a check to make a score go up.** A fix must explain *why the
  finding was wrong* (a parser bug, a page-type mismatch) and carry a test.
- **The sites aren't the patients — Narwhal is.** The tuning corpus is
  deliberately full of excellent sites; when Narwhal flags them, Narwhal is
  usually what needs fixing.

## Rounds

### [2026-07 · Round 2](2026-07-round-2/RESULTS.md) — shipped in v1.25.0

**Corpus grown 8 → 14 pages**, adding *page types* rather than just more sites:
a product URL, real articles (blog + docs tutorial), a Recipe-schema page, a
**French-language** site, an international 137-locale hreflang site, and a
**deliberately dead URL**. The Round 1 sites re-ran as a regression check
(all stable).

**What the sweep caught** (fixed at source, 6 regression tests added):

| Discovery | Fix |
|:--|:--|
| A 404 page scored **88/100** (one critical = −12) | Unfetchable pages hard-fail to **0** |
| og:image behind a rate-limiting CDN reported "**broken**" (HTTP 429) | Gated codes → "could not be verified (low)", never broken |
| French prose judged by **English-calibrated** Flesch + filler patterns | Non-English pages skip those checks — and claim nothing |
| "Very hard to read (medium)" on terse marketing homepages | Article-scoped severity (medium on articles, low elsewhere) |
| "No JSON-LD (medium)" on listing/index pages with no single entity | Hub-aware: low on hubs |
| Heavy-image weights overstate on `srcset` sites (browsers fetch smaller variants) | Finding reframed as **fallback weight**, severity capped low — *a lesson taught by the graded performance agent* |

**Agent grading** (2 specialists, live): the **schema** specialist validated the
recipe page's full JSON-LD graph beyond the script — image aspect-ratio arrays,
review `datePublished`, a semantically-wrong `NewsArticle` co-type, and knowing
the sitelinks SearchAction is deprecated — with paste-ready fixes. The
**performance** specialist measured real Brotli wire sizes, verified the image
CDN's WebP negotiation with Accept headers, and *identified the srcset caveat in
our own scanner* — which is now encoded in both the check and its prompt.

### [2026-07 · Round 1](2026-07-round-1/RESULTS.md) — shipped in v1.19.0

**Corpus:** 8 public sites chosen for page-type diversity — SaaS (Stripe,
Vercel), e-commerce (Allbirds), news (The Verge), docs index (docs.python.org),
personal blog (jvns.ca), wiki (Wikipedia), link-hub (Hacker News).

**What the sweep caught** (all fixed at the source, 14 regression tests added):

| Discovery | Root cause | Fix |
|:--|:--|:--|
| False "No H1" on most real blogs | Stdlib parser lost headings that wrap a link (`<h1><a>…</a></h1>`) | Capture stack |
| Link-heavy pages looked "thin" | Anchor text was dropped from visible text | Anchor text counts as content |
| "Dominant topics: dec, jan, nov" | Month tokens counted as keywords on archive pages | Stopworded |
| "Thin content (high)" on HN / docs indexes | No notion of page type | New hub/article/homepage detection scopes every check |
| "Title very short (high)" on brand homepages | Same | Homepage-aware severity |
| Byline demanded on shop/home pages | Same | Article-only check |
| GEO checks firing on ~90% of sites | Question-headings/evidence checks weren't article-weighted | Article-scoped severity |

**Score corrections** (wrong findings removed — checks not loosened):
jvns.ca **62 → 79** · Hacker News **52 → 66** · docs.python.org **75 → 86** ·
The Verge **71 → 80** · Vercel **83 → 89** · full table + per-site diffs in
[RESULTS.md](2026-07-round-1/RESULTS.md), raw JSON snapshots in
[`before/`](2026-07-round-1/before/) and [`after/`](2026-07-round-1/after/).

**Agent grading** (3 specialists run live on jvns.ca): the runs were strong —
the technical specialist *independently rediscovered the parser bug* being fixed
that hour ("the scanner apparently missed the nested-anchor markup") and adjusted
its score with a stated reason; the GEO specialist recognized the site's explicit
"NO LLM PLZ" robots.txt banner as a deliberate opt-out and split every
recommendation by owner intent instead of "fixing" it; the content specialist
discounted index-page readability artifacts and graded E-E-A-T from real articles
it fetched itself. Those behaviors are now **standard**: every specialist prompt
gained *Judgment rules* (classify the page type first, sample an inner page from
a domain root, respect deliberate owner choices) and a *Discounted script
findings* output section that the audit orchestrator is bound to honor.

## Contributing a round

Run a sweep on sites you care about (`scan.py <url> --format json`), look for
findings that are *wrong* (not merely harsh), and open an issue with the JSON
attached. The bar for a fix: name the root cause, keep the check honest, add a
regression test.
