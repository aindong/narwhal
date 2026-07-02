# Technical SEO reference

The technical auditor checks whether a page *can* rank at all — crawlability,
indexability, and rendering. Below is the reasoning and thresholds behind each
check, plus what to do when the automated check isn't enough.

## Title & meta description
- **Title:** ~50–60 characters. Front-load the primary query; include the brand
  at the end. One title per page, unique across the site. Titles over ~65 chars
  truncate in most SERPs; under ~15 usually means it's a placeholder.
- **Meta description:** 140–160 characters. It doesn't directly affect ranking
  but drives click-through and is often the snippet AI chat previews show. Write
  it as ad copy, not a keyword list.

## Headings
- Exactly one `<h1>` stating the page topic. Multiple H1s dilute the signal.
- Keep nesting sequential (no `H2 → H4` jumps) — the outline is how both crawlers
  and screen readers understand structure.

## Canonicalization
- Every indexable page should have a self-referencing `rel=canonical`.
- A canonical pointing elsewhere is a deliberate signal ("this is a duplicate of
  X"). Flag unexpected cross-URL canonicals — a wrong one can deindex a page.

## Robots directives (two layers)
1. `<meta name="robots">` / `X-Robots-Tag` header — page-level. `noindex` here is
   the single most common cause of "my page vanished."
2. `robots.txt` — site-level crawl control. It blocks *crawling*, not indexing;
   a URL blocked in robots.txt can still be indexed without a snippet. Always
   reference the XML sitemap from robots.txt.

## Mobile / rendering
- `<meta name="viewport" content="width=device-width, initial-scale=1">` is
  mandatory under mobile-first indexing.
- Set `<html lang>` for correct rendering and localization.
- For SPAs, re-run with `--render` — if content only appears after JS, the raw
  fetch understates the page and so will some crawlers.

## hreflang (international)
- Each `rel=alternate hreflang` value maps to exactly one URL; entries must be
  bidirectional (A points to B *and* B points to A).
- Always include an `x-default` for the fallback/language-selector page.
- Use ISO 639-1 language + optional ISO 3166-1 region: `en`, `en-GB`, `es-MX`.

## Images
- Meaningful images need descriptive `alt`; decorative ones use `alt=""`.
- Lazy-load below-the-fold images (`loading="lazy"`) to protect LCP, but never
  lazy-load the LCP/hero image itself.

## Links
- Descriptive anchor text (not "click here") helps users and passes clearer
  relevance signals.
- Audit for broken internal links and long redirect chains; collapse chains to a
  single 301 to preserve equity and speed.

## HTTP hygiene
- HTTPS everywhere with a valid cert.
- Enable gzip/Brotli compression.
- One redirect max to the canonical URL; avoid `http → https → www` daisy-chains.

## Beyond the automated checks
- **Core Web Vitals field data** (LCP, INP, CLS) needs CrUX or real-user
  monitoring — the scan only flags likely hygiene issues (no lazy-load, heavy
  DOM). Recommend PageSpeed Insights / CrUX for real numbers.
- **Crawl budget & log analysis** for large sites needs server logs.
- **JavaScript indexing edge cases** may need Search Console's URL Inspection.

## JS dependence (raw vs rendered)
When a scan runs with `--render`, Narwhal diffs the **served HTML** against the
**rendered DOM**: word-count delta (the JS-only share of the content), headings
that only exist post-JS, and head metadata (title/description/canonical/JSON-LD)
injected client-side. Thresholds: ≥30% JS-only → high, ≥10% → medium. Why it
matters: crawlers that don't execute JavaScript — most AI answer-engine fetchers,
and indexing pipelines before their render pass — see only the served HTML.
Client-injected metadata is especially risky: it may be read never or late.
Without Playwright there is no rendered DOM, so the check stays silent (never
guessed).

## Image weight, formats, and og:image
Single-page scans HEAD-check up to 10 page images (headers only — never full
downloads): >200 KB is heavy (top LCP cause; >=500 KB or 3+ heavy escalates),
JPEG/PNG over 100 KB are flagged as AVIF/WebP candidates, and >30% of <img> tags
missing width/height is a CLS risk. The og:image is validated with one ranged
GET (~64 KB) that parses PNG/GIF/JPEG/WebP headers for dimensions: unreachable →
high, under 200px → medium (previews break), under 1200px wide → low (no large
card). Skip with `--no-image-checks`; crawls skip these automatically (they
would multiply requests per page).

## Hreflang reciprocity (cross-page)
hreflang only works when reciprocal: if A lists B, B must list A back, and every
page must include itself in its own cluster — one-way pairs are ignored by
Google. During a crawl, Narwhal collects each page's cluster, probes up to 5
same-host alternates it didn't crawl (fetch + parse link tags only), and reports
missing return tags as exact A → B pairs, missing self-references, invalid codes
(BCP-47 subset: lang, optional script, optional region), and a sample-wide
x-default check. Targets outside the crawled/probed sample are counted
**unverified**, never broken.
