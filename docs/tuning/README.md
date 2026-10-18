# How Narwhal is tuned

Narwhal's deterministic checks and specialist prompts are revised through
maintainer investigation, not model training. Historical report snapshots are
committed here; new sensitive source captures stay private. Neither is a
completed independent accuracy benchmark. The development loop is:

```
1. FREEZE    declare sampling/settings and preserve available inputs with limits;
             keep reserved evaluation findings out of development tuning
2. INSPECT   check observations, priority and advice separately against evidence;
             investigate reported issues and missed issues, not just low scores
3. FIX       name the root cause in extraction, detection, priority or advice;
             do not suppress findings merely to improve a score
4. VERIFY    test controlled regressions and replay frozen development inputs;
             explain changed findings/scores, including new findings and drops
5. REVIEW    inspect specialist reasoning against evidence, not agreement with
             the scripts; self-review is not independent adjudication
6. REFINE    revise check logic or agent prompts and document behavior/limits;
             a prompt instruction is not proof of agent compliance
```

Two principles guide development:

- **Correctness, not score direction.** A fix needs a reason and regression
  evidence. Detection corrections can add or remove findings; justified priority
  changes can change scores while leaving the observed page fact unchanged.
- **Reputation is not ground truth.** A familiar site can have real issues and
  an unfamiliar site can be sound. Check the captured evidence and owner intent;
  do not infer a false positive or endorse advice from the site's name or score.

## How to interpret scores and verification

| Evidence | What it supports | What it does not establish |
|---|---|---|
| Passing regression tests / CI | Tested behavior under the recorded fixtures and environments | Real-world false-positive rate, recall or SEO outcomes |
| Before/after frozen development replay | How a scanner change affects the same retained inputs | Better pages, independent validation or complete network evidence |
| Higher/lower Narwhal score | A change in reported weighted findings | Page quality, ranking changes or AI citation likelihood |
| Review labels or specialist agreement | Recorded opinions against the attached evidence | Reviewer independence, missed-issue coverage or correctness by consensus |

Use findings as investigation prompts: inspect the source/response/DOM evidence,
check whether the recommendation fits the page and owner's intent, then verify
an actual edit with comparable scans. Keep scanner version, settings and
coverage comparable; if the scanner changed, distinguish tool corrections from
website changes. Heuristic editorial advice needs human judgment. A clean
report means no flagged findings in the measured scope, not a certified site.

Historical reports below have no attached frozen page inputs, so they cannot
isolate all live-page or environment differences. Their narrative labels and
agent observations are maintainer interpretations, not independent adjudication.
The score tables are preserved as history, not accuracy measurements.

## Report-review readiness (Unreleased)

The offline [review-pack workflow](REVIEW.md) inventories the historical corpus
without treating reports as ground truth. It separates observation, priority
and advice review, hashes local inputs and refuses stale/edited source data.
All 15 legacy reports remain report-only, unadjudicated cases; no accuracy or
recall metric is inferred. This is validation infrastructure, not a completed
independent benchmark or proof of ranking gains.

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

**Corpus addition (v1.25.1): openskyelabs.xyz** — a JS-shell site whose entire
content ships inside `<body><noscript>…</noscript>`. Both parser backends
stripped `<noscript>`, so the scan read **"~0 words"** while non-JS crawlers
happily read the fallback. Fixed: noscript is now a separate measured channel
(`extraction: noscript fallback`), headings/links inside it keep their text, and
a new **"Content served only as a `<noscript>` fallback"** finding flags the
architecture. Sites that *break* the tool are the most valuable corpus members —
send us more.

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

**Historical tool-score changes** (extraction/detection and priority revisions,
not demonstrated website improvements):
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
