# Round 2 results — per-page before/after (v1.24.0 → v1.25.0)

Corpus expanded from 8 to 14 pages: the Round 1 sites (regression check)
plus new *page types* — a product URL, real articles, a recipe page with
rich schema, a French-language site, an international hreflang site, and
a deliberately dead URL. Raw scan JSONs in [`before/`](before/) and
[`after/`](after/), captured 2026-07-02.

| Page | Before | After |
|:--|--:|--:|
| allbirds.com (e-commerce home) | 79 | **79** |
| allbirds product URL (404 — deliberate dead page) | 88 | **0** |
| apple.com (international, 137-locale hreflang) | 87 | **87** |
| news.ycombinator.com (link-hub) | 66 | **69** |
| jvns.ca blog post (article) | 77 | **77** |
| jvns.ca (blog home) | 79 | **81** |
| lemonde.fr (French — non-English) | 87 | **87** |
| docs.python.org tutorial page (docs article) | 85 | **85** |
| docs.python.org/3 (docs index) | 84 | **86** |
| allrecipes.com lasagna (Recipe schema) | 82 | **82** |
| stripe.com (SaaS home) | 87 | **87** |
| theverge.com (news home) | 75 | **77** |
| vercel.com (SaaS home) | 90 | **92** |
| en.wikipedia.org/wiki/Narwhal (wiki article) | 73 | **78** |

## news.ycombinator.com (link-hub) — 66 → 69
- ❌ removed: **low** · No visible date signal
- ❌ removed: **medium** · No structured data (JSON-LD)
- ✅ now: **low** · No structured data (JSON-LD)

## jvns.ca (blog home) — 79 → 81
- ❌ removed: **medium** · No structured data (JSON-LD)
- ✅ now: **low** · No structured data (JSON-LD)

## docs.python.org/3 (docs index) — 84 → 86
- ❌ removed: **medium** · No structured data (JSON-LD)
- ✅ now: **low** · No structured data (JSON-LD)

## theverge.com (news home) — 75 → 77
- ❌ removed: **medium** · Heavy images (4 over 200 KB)
- ✅ now: **low** · Heavy images (4 over 200 KB)

## vercel.com (SaaS home) — 90 → 92
- ❌ removed: **medium** · Content is very hard to read
- ✅ now: **low** · Content is very hard to read

## en.wikipedia.org/wiki/Narwhal (wiki article) — 73 → 78
- ❌ removed: **high** · og:image is broken
- ✅ now: **low** · og:image could not be verified


## Corpus addition: openskyelabs.xyz (JS-shell with `<noscript>` fallback) — 89 → 87

Added mid-round at the owner's request — and it immediately earned its place:
the site serves its entire content as `<body><noscript>…</noscript>` plus a JS
shell. Both parser backends **stripped `<noscript>`entirely**, so the scan
measured **"~0 words of main text"** with empty headings/links — while non-JS
crawlers and AI fetchers actually read that fallback just fine.

- ❌ removed: **false "~0 words"** measurement (and empty heading/link text)
- ✅ now: content measured on the fallback, labeled `measured on noscript
  fallback` — "Thin content (~131 words)" is a *true* positive
- ✅ new architecture finding: **Content served only as a `<noscript>` fallback
  (medium)** — rendering and non-rendering crawlers see different documents;
  SSR recommended
- Tiny noscript blocks (font loaders) verified not to change behavior
