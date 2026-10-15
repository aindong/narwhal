# SEO & GEO Audit — https://example.test/guides/answer-visibility

**Health score: 79/100 (score band: good)**  ·  status 200

Checked auditor groups: Technical SEO; Content & E-E-A-T; Structured data; GEO / LLMO. All four groups ran for this page, not a site-wide or exhaustive validation. Image resource checks were disabled. Findings use served HTML.

| Critical | High | Medium | Low | Passed |
|:--:|:--:|:--:|:--:|:--:|
| 0 | 1 | 2 | 9 | 15 |

## Summary

**1 high, 2 medium issue(s) need attention in the completed checks, plus 9 quick win(s).** This page scores **79/100 (score band: good)**.

**Top priorities:**
- 🟠 Thin content (Content & E-E-A-T)

## Breakdown by area

| Area | Score | 🔴 | 🟠 | 🟡 | 🔵 | 🟢 |
|:--|:--:|:--:|:--:|:--:|:--:|:--:|
| Technical SEO | 96 | 0 | 0 | 1 | 1 | 8 |
| Content & E-E-A-T | 87 | 0 | 1 | 1 | 4 | 2 |
| Structured data | 98 | 0 | 0 | 0 | 2 | 1 |
| GEO / LLMO | 98 | 0 | 0 | 0 | 2 | 4 |

## Priority fixes

### 1. 🟠 Thin content  
*Content & E-E-A-T · high*

- **Observed:** ~146 words of main text (measured on visible text).
- **Fix:** Expand to cover the topic fully; thin pages struggle to rank and are rarely cited by AI answers.
- [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#content-depth-not-word-count-for-its-own-sake)

### 2. 🟡 Images missing alt text  
*Technical SEO · medium*

- **Observed:** 1 of 1 <img> tags have no alt attribute.
- **Fix:** Add descriptive alt text (empty alt="" only for decorative images).
- [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/technical-seo.md#images)

### 3. 🟡 No visible author/byline  
*Content & E-E-A-T · medium*

- **Observed:** No author meta tag or byline detected near the top.
- **Fix:** Add a named author with credentials — a core E-E-A-T (experience/expertise) signal.
- [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#experience--expertise)

## Quick wins

- 🔵 **No compression header** — Enable gzip or Brotli compression to cut transfer size. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/technical-seo.md#http-hygiene)
- 🔵 **Content is fairly hard to read** — Consider shorter sentences/simpler words unless the audience is specialist. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#readability)
- 🔵 **No visible date signal** — Expose a publish or last-updated date to signal freshness. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#freshness)
- 🔵 **Incomplete Open Graph tags** — Add og:title, og:description and og:image for rich social and chat-app link previews. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#social--preview-metadata)
- 🔵 **No Twitter/X card type** — Add twitter:card (e.g. summary_large_image) for X previews. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#social--preview-metadata)
- 🔵 **Article missing recommended properties** — Consider applicable, known author, datePublished, image values; do not invent authors or dates. Google Article markup has no required properties, and this is not an invalidity or eligibility verdict. Source: https://developers.google.com/search/docs/appearance/structured-data/article · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/schema.md)
- 🔵 **No Organization/WebSite entity** — Add Organization + WebSite JSON-LD (typically sitewide) to establish the publishing entity. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/schema.md)
- 🔵 **No configured introductory answer cues** — Review whether the opening serves the reader's intent and language. Add a concise answer only when useful; English cue absence does not prove a missing answer. Answer accuracy and citation impact are not measured. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/geo-llmo.md#4-direct-answer-intro-inverted-pyramid)
- 🔵 **No root llms.txt observed** — Optionally publish a curated llms.txt if useful; this is not a required ranking or access control. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/geo-llmo.md#llmstxt--low-cost-low-certainty)

## Root llms.txt response evidence

Root llms.txt absent: the root request returned HTTP 404 or 410 (HTTP 404). Root /llms.txt request only; independent subpath files and rel=describedby discovery were not checked. Redirect destinations are recorded. This is not full proposal validation, linked-resource verification, engine adoption or evidence of ranking/citation impact.

## Passing checks

- 🟢 **Title length is in range** — 43 characters
- 🟢 **Meta description length is in range** — 92 characters
- 🟢 **Exactly one H1** — Practical guide to answer-engine visibility
- 🟢 **Self-referencing canonical** — https://example.test/guides/answer-visibility
- 🟢 **No generic meta noindex detected** — Generic meta robots observation only; it excludes HTTP headers and crawler-specific meta. Absence is not proof of indexability.
- 🟢 **Responsive viewport declared**
- 🟢 **robots.txt references a sitemap**
- 🟢 **XML sitemap reachable**
- 🟢 **Few configured style-pattern matches** — 0 filler matches; 0 distinct common-phrase matches; lexical diversity 0.815. This does not establish authorship, originality or content quality.
- 🟢 **Dominant topics detected** — page (4), should (4), evidence (2), engines (2), without (2), teams (2)  ·  phrases: practical guide, answer-engine visibility, page easy
- 🟢 **Structured data present** — Article
- 🟢 **Configured question-heading cues present** — 2/2 subheadings match configured English starters or a terminal ASCII question mark. Question relevance and engine matching are not measured.
- 🟢 **Sentence groups in the configured word range** — 3/4 synthetic sentence groups contain 40–120 counted ASCII-word matches. Actual paragraphs, self-containment and engine citability are not measured.
- 🟢 **Configured statistics/citation cues present** — 0 configured statistic-pattern matches; 2 citation-cue matches. Lexical cues only; factual support and source validity are not checked.
- 🟢 **Search/retrieval agents are not disallowed at site root** — robots.txt only; live access, other paths, indexing and citations are not verified.
