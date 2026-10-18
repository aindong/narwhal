# GEO / LLMO reference — optimizing to be cited by AI answers

**GEO** (Generative Engine Optimization), also called **LLMO** (LLM Optimization)
or **AEO** (Answer Engine Optimization), is about being *quoted and cited* by AI
answer engines — ChatGPT, Claude, Perplexity, Google AI Overviews — not just
ranking in classic blue links.

## First principle: GEO is mostly good SEO, plus structure for extraction
Google's [AI-feature guidance](https://developers.google.com/search/docs/appearance/ai-features)
states that no special optimization or additional technical requirements are
needed for its AI features. Fundamental SEO and helpful content remain relevant;
eligibility is not a guarantee of inclusion. That does not establish identical
behavior across other engines. Narwhal's text cues are prompts for contextual
editorial review, not measurements of AI-answer visibility or citation likelihood.

## The signals the auditor scores

### 1. Question-based headings
The check counts H2–H6 text whose first token is a configured English starter
(such as "how" or "what") or which ends in an ASCII `?`. Below a 20% match
fraction it emits a low-priority review prompt, including on articles. This is
an unvalidated editorial threshold, not an engine requirement. It does not
recognize every language or establish that a heading matches a real user query.
Keep descriptive headings that work for readers; use questions only when useful.

### 2. Citable, self-contained passages
The legacy helper splits extracted text at selected sentence boundaries and
accumulates fragments until the configured minimum word count. Its word regex
matches ASCII-letter sequences (with apostrophes/hyphens), not words in every
language. The resulting **synthetic groups are not actual paragraphs**.

`passage_min`/`passage_max` default to 40–120; a match fraction below 30% emits
a low-priority prompt. Neither those unvalidated defaults nor an in-range group
establish self-containment, completeness or engine citability. Review readability
and useful context; do not pad or split useful text just to match a number.

### 3. Evidence density
The check counts a limited statistic-pattern list (for example, percentages and
some scaled quantities) and English lexical citation cues such as "study" or
"report". It does **not** enumerate all numbers, dates, bibliography entries or
links, and does not validate factual support or source quality. Zero matches are
not proof of missing evidence; a "study" mention is not proof of a real study.
Review actual claims and sources in context. Do not invent statistics or citations
to satisfy the check. Both zero-match advice and positive counts stay bounded to
what was observed, not an engine-attribution prediction.

### 4. Direct-answer intro (inverted pyramid)
The check looks for configured English terms such as "is", "are" or "helps" in
the first 80 whitespace-separated tokens of extracted text. A match does not
prove a direct or accurate answer; no match does not prove one is absent.
Other languages and non-answer page intents may not fit this pattern. Lead with
useful information for the actual audience, adding an answer only when suitable.
No citation likelihood or effect of moving text is measured.

### Text-cue output and compatibility

`meta.geo_text_cues` records version 1, `editorial_review_only` interpretation,
the English-oriented basis/limits and four bounded count objects:
`question_headings`, `sentence_groups`, `evidence_cues` and `intro_cues`.
Empty-input counts are observations, not passes. These receipts do not validate
language understanding, paragraph semantics, source truth or engine behavior.

`sentence_groups.word_min`/`word_max` retain plain integers and finite floats.
Programmatic `Decimal`/`Fraction` values use JSON-safe `{kind, value}` descriptors
with exact string representations; nonfinite floats use explicit descriptors
rather than nonstandard JSON numbers. Other comparable numeric types use an
`unrecorded_numeric_type` marker. The actual comparisons keep the original values:
no float coercion rounds a threshold near an integer boundary. A serializable
receipt is not validation of custom settings or a verified configuration snapshot.

The matching algorithms, thresholds and legacy rule IDs remain stable. IDs with
historical names such as `citable`, `evidence.signals` or `direct.answer` are
machine identifiers, not semantic certification; read the counts and limits.
Three negative checks previously using medium priority now use low priority (question
and evidence checks on articles, and sentence-group range checks). A score may
rise without any page change; that is a priority correction, not an SEO result.
Displayed labels have changed: update title-based `[ignore].titles` filters.
The planner keeps new and legacy cue-rule edits conditional on contextual review.
Crawler, `llms.txt`, rendering and entity checks are separate and unchanged.

### Comparison and brief cue observations

Comparison facts preserve `stats_cites`, the sum of these same two regex match
counts, and add a versioned `evidence_cues` receipt. Its basis
`audit_geo_stat_and_cite_hint_v1` identifies the unchanged patterns;
`statistic_matches`, `citation_cue_matches` and `total_matches` distinguish their
units. `source_validity_checked` is explicitly false. Extraction basis is clipped
at 160 code points with a flag; no raw text is newly retained. These limits are
not total resource bounds or source-verification claims.

A linked reference may have zero matches; repeated words such as "report" may
have many without naming any source. Neither direction establishes evidence
quality. Comparison no longer creates an `Evidence density (stats/citations)`
gap, and briefs no longer generate `structure.evidence_target`/`your_evidence`,
including the previous zero-count target in topic mode. Counts remain neutral
observations across page kinds, including hubs; no own page is invented in topic
mode. Deliberate editorial source requirements are separate from these counts.

Rendering new facts shows actual units and limits. Missing/malformed receipts,
unknown markers and conflicting aliases remain basis-unrecorded; tool versions
do not backfill missing provenance. A bounded nonblank extraction label and a
boolean clipping flag are required to recognize a cue or length receipt;
missing/malformed provenance is not a recorded extraction basis.
Rendering legacy data does not mutate its
JSON or repeat known old evidence-density verdicts/targets as advice. Real
claims and sources need contextual review, not a quota or fabricated citations.
Scores, page-auditor receipts and other measurements stay unchanged by this
comparison/brief correction. Question and subtopic heuristics remain unvalidated.

### 5. Entity clarity
Keep the `<title>`, `<h1>`, and opening aligned on one clear subject entity, and
declare the publishing entity with `Organization`/`Person` schema + `sameAs`
links (Wikipedia, LinkedIn, official socials). Clear entities help models ground
and attribute the page.

## AI-crawler policies — distinguish purpose before recommending access
Robots directives are policy signals, not live access tests or promises of
indexing/citations. Role guidance was checked **2026-10-15** against the
[OpenAI crawler documentation](https://developers.openai.com/api/docs/bots),
[Anthropic bot guidance](https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler),
[Perplexity crawler documentation](https://docs.perplexity.ai/docs/resources/perplexity-crawlers),
[Google Search AI controls](https://developers.google.com/search/docs/appearance/ai-features#controlling-your-content-in-ai-features-in-search),
[Google-Extended guidance](https://developers.google.com/crawling/docs/crawlers-fetchers/google-common-crawlers#google-extended),
and [Common Crawl's CCBot description](https://commoncrawl.org/ccbot).

| Purpose | Agents / controls | Interpretation |
|---|---|---|
| Search / documented retrieval | `OAI-SearchBot`, `Claude-SearchBot`, `Claude-User`, `PerplexityBot`, `Googlebot` | Review restrictions if those channels match the owner's goals. Claude-User is user-directed retrieval, not an index crawler. |
| Training collection | `GPTBot`, `ClaudeBot` | Distinct from search agents; a training opt-out is not a search-access defect. |
| Other data-use control | `Google-Extended` | Covers training and specified Gemini/Vertex grounding uses, not Google Search or AI Overviews access/ranking. |
| Dataset collection | `CCBot` | A Common Crawl restriction alone is not proof of direct search impact. |
| User-triggered fetch directives | `ChatGPT-User`, `Perplexity-User` | OpenAI says robots may not apply; Perplexity says its user fetcher generally ignores robots. Do not call these proven fetch blocks or search-index opt-outs. |
| Unverified / legacy role | `Claude-Web`, `Bytespider` | No current role inference or search penalty from these tokens alone. |

The deterministic check evaluates **`/` only**, not every page path. Page JSON
records `meta.ai_crawler_access` with the checked path, robots-only basis,
dated roles, per-agent source URLs and root disallowance results. Training/data-use,
nonbinding user-fetch and unverified restrictions appear as **non-scoring policy
notes** in Markdown/HTML (and therefore PDF input), not green endorsements or
instructions to enable training. Only documented search/retrieval restrictions
produce the existing high finding. Its title/rule ID remain compatible with
title ignores and planner ownership; it is explicitly a site-root observation.

Preserve deliberate opt-outs. A robots allow result does not verify WAF rules,
bot identity/IP handling, live reachability, other paths, indexing or citations.
Google Search snippet/index controls are separate from Google-Extended. Policy
sources are static guidance shipped with the toolkit; scans do not fetch them.

## llms.txt — low cost, low certainty
The [llms.txt proposal](https://llmstxt.org/) describes Markdown guidance for
agents; v2 also permits scoped subpath files and requires an H1 (checked
2026-10-15). This is not a ranking/access-control requirement. Treat a curated
file as optional guidance, not a replacement for crawlable, useful content.

Narwhal probes the root endpoint only, preserving status, media type, final
redirect URL and body-budget evidence. A complete supported text response with
an initial ATX/simple Setext H1 is only a candidate, not full format validation
or proof an engine used it. Complete root 404/410 observations do not establish absence
of subpath files. HTML fallback, gating, unsupported/empty/partial/truncated
responses remain unverified rather than passing or missing. Known HTTP
uncertainty blocks relevant score comparisons and produces verification-only
plan actions, not automatic file creation. Legacy flags are explicitly caller
context; no HTTP measurement is inferred from them. No runtime proposal fetch,
linked-resource discovery or engine/ranking/citation measurement is performed.

## Myths worth rejecting
- "Just add llms.txt and you'll rank in AI." — no evidence.
- "Stuff pages with AI keywords / 'as an AI language model' bait." — spam.
- "GEO replaces SEO." — it's an extension of it, not a replacement.
Focus on genuinely useful, well-structured, attributable content. Measure actual
traffic and citations separately; lexical cues and scanner scores do not prove
those outcomes or identical behavior across engines.
