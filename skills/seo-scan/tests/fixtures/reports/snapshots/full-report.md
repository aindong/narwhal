# SEO & GEO Audit — https://example.test/guides/answer-visibility

**Health score: 86/100 (score band: good)**  ·  status 200

Checked auditor groups: Technical SEO; Content & E-E-A-T; Structured data; GEO / LLMO. All four groups ran for this page, not a site-wide or exhaustive validation. Image resource checks were disabled. Findings use served HTML.

| Critical | High | Medium | Low | Passed |
|:--:|:--:|:--:|:--:|:--:|
| 0 | 0 | 1 | 11 | 15 |

## Summary

**1 medium issue(s) need attention in the completed checks, plus 11 quick win(s).** This page scores **86/100 (score band: good)**.

## Breakdown by area

| Area | Score | 🔴 | 🟠 | 🟡 | 🔵 | 🟢 |
|:--|:--:|:--:|:--:|:--:|:--:|:--:|
| Technical SEO | 96 | 0 | 0 | 1 | 1 | 8 |
| Content & E-E-A-T | 94 | 0 | 0 | 0 | 6 | 2 |
| Structured data | 98 | 0 | 0 | 0 | 2 | 1 |
| GEO / LLMO | 98 | 0 | 0 | 0 | 2 | 4 |

## Priority fixes

### 1. 🟡 Images missing alt text  
*Technical SEO · medium*

- **Observed:** 1 of 1 <img> tags have no alt attribute.
- **Fix:** Add descriptive alt text (empty alt="" only for decorative images).
- [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/technical-seo.md#images)

## Quick wins

Observations below are bounded, whitespace-normalized previews of reported fields, not independent verification. Full fields remain in JSON.

- 🔵 **No compression header** — Enable gzip or Brotli compression to cut transfer size. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/technical-seo.md#http-hygiene) · **Observed (preview):** `Response has no Content-Encoding (gzip/br).`
- 🔵 **Review limited ASCII-token count** — Review whether the captured text serves the reader and page intent. Keep useful concise text; edit only confirmed coverage gaps. Do not pad content to reach a configured count. Ranking and citation impact are not measured. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#content-depth-not-word-count-for-its-own-sake) · **Observed (preview):** `146 matches of the configured ASCII-only pattern in selected extracted text (visible text). Below the configured lower bound. ASCII-pattern matches are not universal word counts or a measure of content depth, usefulness, ranking or AI citations. Configured bounds are editorial defaults, not engine requirements.`
- 🔵 **Content is fairly hard to read** — Consider shorter sentences/simpler words unless the audience is specialist. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#readability) · **Observed (preview):** `Flesch reading ease 38.0 (difficult); ~grade 11.1.`
- 🔵 **Review article attribution cues** — Review the real byline, profile links and editorial ownership in context. Identify actual creators/reviewers where appropriate; do not invent people or credentials. Missing cues do not establish anonymity or poor quality. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#experience--expertise) · **Observed (preview):** `No attribution candidate was observed in the bounded metadata, author-link and leading source-block checks. This does not prove anonymity.`
- 🔵 **Review article date cues** — Review actual page purpose and original date evidence. Add accurate publication/update information only when useful and known; do not invent dates, relabel events as publication or refresh a date without substantive change. Ranking/citation effects are not measured. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#date-cues-not-freshness-verification) · **Observed (preview):** `No candidate observed in the checked metadata and selected-text prefix. Date-related candidates only, not validated dates, publication/update ownership, rendered visibility, content freshness, accuracy or ranking/citation impact. Metadata values and English-month/ISO-like text patterns can be unrelated or invalid. Bare years alone are not publication evidence. Non-observation in these bounded chec…` (truncated; full value in JSON)
- 🔵 **Incomplete Open Graph tags** — Add og:title, og:description and og:image for rich social and chat-app link previews. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#social--preview-metadata) · **Observed (preview):** `Missing: og:description, og:image.`
- 🔵 **No Twitter/X card type** — Add twitter:card (e.g. summary_large_image) for X previews. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/content-eeat.md#social--preview-metadata) · **Observed (preview):** `Missing <meta name="twitter:card">.`
- 🔵 **Article missing recommended properties** — Consider applicable, known author, datePublished, image values; do not invent authors or dates. Google Article markup has no required properties, and this is not an invalidity or eligibility verdict. Source: https://developers.google.com/search/docs/appearance/structured-data/article · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/schema.md) · **Observed (preview):** `Recommended fields absent or blank: author, datePublished, image.`
- 🔵 **No Organization/WebSite entity** — Review existing publisher/site markup and intended consumer before adding applicable entity data. Do not duplicate entities, invent publisher facts or add both types automatically. Preserve valid JSON-LD, Microdata or RDFa; eligibility and ranking benefits are not established. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/schema.md) · **Observed (preview):** `No Organization, LocalBusiness or WebSite type was observed in this page's supported subset; this is not a whole-site identity or exhaustive-extraction check.`
- 🔵 **No configured introductory answer cues** — Review whether the opening serves the reader's intent and language. Add a concise answer only when useful; English cue absence does not prove a missing answer. Answer accuracy and citation impact are not measured. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/geo-llmo.md#4-direct-answer-intro-inverted-pyramid) · **Observed (preview):** `No configured English answer term matched in the first 80 whitespace-separated tokens. This does not establish whether the opening answers a question.`
- 🔵 **No root llms.txt observed** — Optionally publish a curated llms.txt if useful; this is not a required ranking or access control. · [Learn more](https://github.com/aindong/narwhal/blob/main/skills/seo-scan/references/geo-llmo.md#llmstxt--low-cost-low-certainty) · **Observed (preview):** `Root llms.txt absent: the root request returned HTTP 404 or 410 (HTTP 404). Root /llms.txt request only; independent subpath files and rel=describedby discovery were not checked. Redirect destinations are recorded. This is not full proposal validation, linked-resource verification, engine adoption or evidence of ranking/citation impact.`

## Root llms.txt response evidence

Root llms.txt absent: the root request returned HTTP 404 or 410 (HTTP 404). Root /llms.txt request only; independent subpath files and rel=describedby discovery were not checked. Redirect destinations are recorded. This is not full proposal validation, linked-resource verification, engine adoption or evidence of ranking/citation impact.

## Text-length observation (not content quality)

Reported selected text: 1046 Unicode code points; 146 ASCII-pattern matches; 0 non-ASCII letter/mark code points. Threshold review uses the configured ASCII-pattern counts only. ASCII-pattern matches are not universal word counts or a measure of content depth, usefulness, ranking or AI citations. Configured bounds are editorial defaults, not engine requirements. Extraction basis and configured bounds are recorded in JSON.

## Attribution cue evidence (not identity verification)

Attribution candidates only: writer identity, rendered visibility, expertise, trust, author-link destinations and ranking impact are not verified. These bounded checks do not establish that attribution is absent.

```text
No candidate observed in the checked sources; attribution remains unverified.
```

## Date-cue evidence (not freshness verification)

Date-related candidates only, not validated dates, publication/update ownership, rendered visibility, content freshness, accuracy or ranking/citation impact. Metadata values and English-month/ISO-like text patterns can be unrelated or invalid. Bare years alone are not publication evidence. Non-observation in these bounded checks does not establish that the page lacks dates; structured-data date graphs are not inspected.

```text
No candidate observed in the checked metadata and selected-text prefix; dates may exist elsewhere.
Checked 4 normalized metadata field(s) and 1046 selected-text prefix code points (visible text).
Year-pattern matches in selected prefix: 0 (not publication evidence on their own).
```

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
