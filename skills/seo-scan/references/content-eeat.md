# Content quality & E-E-A-T reference

Google's Search Quality Rater Guidelines reward content that demonstrates
**E-E-A-T**: Experience, Expertise, Authoritativeness, Trustworthiness. Raters
don't set rankings directly, but the systems are trained to approximate their
judgments. The content auditor surfaces heuristic proxies for these signals.

## How the text is measured (extraction basis)
Depth/readability/citability checks run on the page's **main content when it can
be isolated** — the optional `trafilatura` library strips nav, footers, and
boilerplate, and is used automatically whenever installed (recommended:
`pip install trafilatura`). Without it, checks fall back to **all visible text**,
which over-counts page chrome on prose pages; each depth finding states which
basis was used. Page-type detection (hub/listing vs article) further scopes the
checks so link-dominated index pages aren't judged as thin articles.

## Content depth (not word count for its own sake)

Read the page in context: useful coverage depends on its purpose and readers,
not a fixed length. Google's [SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
states that content length alone does not determine ranking and supplies no
minimum/maximum word-count target. Narwhal does not measure usefulness, intent
satisfaction, content depth, ranking or AI citation likelihood from a count.

### Page text-length observation

- `meta.content_length` records the selected extracted text's Python-string
  length (Unicode code points), historical ASCII-pattern match count, count of
  non-ASCII letters/combining marks, extraction basis, declared language, actual
  configured bounds and whether threshold review was interpreted. It does not
  retain raw text. Language/basis strings are capped at 80/160 code points with
  clipping flags; these are receipt display limits, not total CPU/heap budgets.
  Finite built-in int/float bounds stay numeric; Decimal/Fraction bounds use
  exact tagged strings, non-finite floats are tagged and unknown custom numeric
  types stay unrecorded. Raw comparison behavior is not rounded; recording a
  bound is not configuration validation.
- The preserved pattern is `[A-Za-z][A-Za-z'-]+`. It excludes single-letter
  words and non-ASCII letters and can split accented words. Its matches are
  **not universal word counts**. No language is inferred, no dictionary is loaded
  and no Unicode word segmentation runs. Non-ASCII coverage uses the running
  Python's Unicode letter/mark categories, not a language detector or a Unicode
  segmentation conformance claim. [Unicode's segmentation guidance](https://www.unicode.org/reports/tr29/)
  explains why languages such as Chinese/Japanese need tailored word boundaries;
  replacing the regex with a whitespace split would not solve that problem.
- Threshold review is not applied to declared non-English languages or selected
  text containing non-ASCII letters/marks, even when `lang=en` or absent. This is
  a conservative coverage rule, not language detection. Even one accented letter
  leaves this check uninterpreted. Counts and the reason remain visible as a
  non-scoring observation; there is no invented zero-word defect or depth pass.
- English/English-subtag or undeclared text without non-ASCII letters/marks may
  receive a **low-priority contextual review** below the configured bounds.
  `thin_content`/`short_content` remain 300/600 by default, with the original
  comparison order and numeric behavior. They are unvalidated editorial defaults,
  not SEO targets. Keep useful concise text; edit only confirmed coverage gaps.
  A non-flagged count is not a content-depth or quality certificate.
- Historical IDs `content.thin.content`, `content.content.is.on.the.short.side`,
  `content.link.hub.page.with.little.prose` and `content.sufficient.content.depth`
  remain for interpreted checks. New titles require reviewing title-based ignore
  filters. At default weights, the high→low correction raises a score by five points;
  an uninterpreted check emits no length finding. Neither is an improved page.
  Current and legacy remediation plans keep edits conditional, not word padding.
- Current scans record `scan_settings.content_length_reviewed`. A known change
  in threshold coverage prevents a page/audit diff from claiming score improvement
  or issue resolution, including for common crawl URLs. Matching uninterpreted
  coverage is not automatically a comparison failure. Missing legacy flags stay
  unknown, not inferred from language; they do not certify full comparability.
- This scopes the **page content auditor's length check** only. Readability,
  keywords and the question/subtopic heuristics remain separate; this
  does not validate their linguistic or content-depth assumptions.

### Comparison and brief length observations

- Comparison facts preserve their historical `words` scalar, calculated with
  Python `str.split()` on selected extracted text. It counts whitespace-separated
  tokens, **not linguistic words**; 6,000 unspaced Chinese code points can be one
  token. This differs from the page auditor's ASCII-pattern count. Neither is a
  multilingual word segmenter. Formatting and extraction can change either count.
- Facts add a versioned `text_length` receipt with `basis=python_str_split`,
  `whitespace_tokens`, Unicode `code_points`, and the extraction basis (capped at
  160 code points with a clipping flag). No raw text is newly retained. A known
  conflicting alias, unsupported marker or malformed count leaves the basis
  unverified; the tool version alone never supplies missing provenance.
- Comparison and brief roots add neutral `text_length` observations, including
  hubs and zero counts. Missing own-page input in topic mode is `not_supplied`
  with a null count, not zero. Known-basis compared pages supply a count range;
  missing legacy measurements stay null/unrecorded. Reports label units and
  limits rather than infer completeness, ranking or AI citation impact.
- Length alone no longer produces a `Content depth` gap/lead or brief
  `structure.target_words`/`your_words`. New reports omit those target fields;
  other structure heuristics remain. Consumers should use literal observations,
  not silently turn the longest page into a requirement. Deliberate user/editorial
  length constraints may still be useful; keep them separate from measurements.
- Rendering older compare/brief data does not mutate its JSON. Known legacy
  depth verdicts are not repeated as advice; old target fields receive an
  unrecorded-basis warning without rendering their values as requirements.
  Bare legacy `words` values can be shown only as basis-unrecorded counts.
- Compare's `content_length_reviewed` fact is read only from an explicit page
  scan boolean (otherwise null). It labels page-threshold scope, not validity of
  the whitespace count, content quality, or a pass/fail on linguistic coverage.
  Scores and all unrelated fact measurements remain unchanged by this correction.

## Experience & expertise
- Show first-hand experience: original photos, test results, "we measured…",
  specific anecdotes. This is the "Experience" that generic AI-written content
  can't fake and that raters explicitly reward.
- Review actual creators/reviewers and editorial ownership where readers expect
  attribution; add accurate bylines/profile information when appropriate. Never
  invent names, biographies or credentials to satisfy an audit. Google encourages
  accurate attribution and warns against fabricated profiles in its
  [Who guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content#who-created-the-content).

### Attribution cues (not identity verification)

The content scan and comparison share a bounded source observer. It records
nonempty `name=author` / `property=article:author` metadata, declared `rel=author`
link destinations (`a`, `area`, `link`), and short leading byline-like blocks.
Ordinary prose containing "by" or "author", and whitespace-only metadata, no
longer pass. Source checks are independent of main-content extraction, which
may remove a real header byline. A captured cue is not a verified writer.

- Unmarked bylines need an English leading label (`By`, `Written by`, `Reviewed
  by`, `Author:`), a short payload of at most eight words and no digits, with
  an uppercase or uncased initial letter. Exact class tokens `byline`,
  `article-author`, `author-name`, `post-author` also admit short names without
  those labels, including lowercase names. These are heuristics, not person-name
  recognition; a prose fragment can still resemble a byline. Other languages,
  unmarked lowercase pen names and unsupported layouts can be missed.
- Source checks inspect at most 250,000 characters, leading blocks beginning
  within 1,500 normalized source-text characters, 80 nesting levels and five
  distinct kind/value candidates. Values are clipped at 160 characters; byline
  blocks longer than that are not candidates. Known source/depth/candidate limits
  are recorded. Programmatic Docs without source use normalized fields instead,
  at most 1,000 meta fields and 1,000 combined links, plus supplied leading text;
  field-limit exhaustion is explicit. Declaration attributes are inspected only
  through 4,096 raw characters per value, and normalized `rel` lists through 64
  items, without joining the full list or copying unrelated attributes. Limits
  retain unknown suffixes and mark clipped witnesses; cutting an attribute must
  not turn a partial relation token into `author`. Human-report input values use
  the same raw-character cap. These are not total CPU/heap guarantees.
- Script/style/template/textarea/title, nav/footer/aside, `hidden` and
  `aria-hidden=true` contexts are excluded; noscript is inspected only when the
  Doc selected its fallback. This is a conservative stdlib projection, not a
  full HTML5 DOM or computed-CSS visibility/accessibility inspection.
- `meta.authorship_cues` retains JSON-safe witnesses, basis and coverage. Page
  Markdown/HTML/PDF show literal evidence and limits for candidates or an article
  review. Link values are untrusted declarations, never followed or rendered as
  evidence hyperlinks. The HTML [author relation](https://html.spec.whatwg.org/multipage/links.html#link-type-author)
  can concern a nearest article or whole page; Narwhal does not resolve that
  ownership or verify destinations, identities, credentials, expertise or trust.
  Structured-data author graphs are not interpreted by this observer.
- No candidate on an article gives a **low-priority contextual review**, not an
  anonymity or poor-quality verdict. Nonarticles without cues get no missing
  attribution finding. A candidate gets a passing *observation*, not quality
  certification. Neither case establishes ranking or AI-citation outcomes.
- Historical rule IDs `content.no.visible.author.byline` and
  `content.authorship.signal.present` stay stable; comparison keeps the boolean
  `author_signal` and adds the same cue receipt. Titles change, so review
  title-based ignore filters. Missing-cue priority changes from medium to low:
  tool scores can rise by two points without page changes; removing a false
  prose-word pass can instead add a one-point low advisory. These are corrected
  tool findings, not measured SEO gains. Planner edits stay review-required for
  current and legacy reports.

## Authoritativeness & trust
- Cite primary sources; link out to authoritative references.
- Expose contact info, an about page, editorial policy, and clear ownership.
- For transactional pages: visible pricing, return/refund policy, real reviews.
- Trust is the most important E-E-A-T member — a page can be expert but
  untrustworthy (deceptive, unsafe), and that caps its quality rating.

<a id="freshness"></a>

## Date cues (not freshness verification)

Review the page's actual purpose and original date evidence. Add accurate,
appropriately labelled publication/update information when useful and known;
do not invent dates, relabel event dates as publication or cosmetically refresh
dates without substantive changes. Google's [byline-date guidance](https://developers.google.com/search/docs/appearance/publication-dates)
distinguishes page publication/update dates from dates of the events described,
uses multiple signals, and does not guarantee a displayed date. Narwhal does not
measure engine interpretation, freshness, accuracy or ranking/citation impact.

- Page content scans and comparison/brief facts share `date_cues`: normalized
  nonempty `property=article:published_time`, `property=article:modified_time`
  and `name=date` metadata, plus English-month/ISO-like patterns in the first
  2,000 Unicode code points of selected extracted text. Bare `20xx` years are
  counted separately, not publication evidence on their own. Metadata values
  and pattern matches can be invalid or unrelated; no calendar, ownership,
  rendered-visibility, multilingual date or structured-data date-graph validation
  occurs. A candidate gets a passing observation, not a freshness certificate.
- The receipt checks at most 1,000 normalized metadata fields and retains five
  distinct kind/value candidates. Declaration attributes are inspected through
  4,096 raw characters; witnesses normalize whitespace/controls and clip at 160.
  JSON records field ordinals or zero-based selected-prefix offsets, extraction
  basis and metadata/value/candidate/prefix limit flags. These are output/check
  bounds, not total CPU/heap guarantees. Human page reports show literal bounded
  witnesses, not source hyperlinks; JSON may retain sensitive metadata values,
  so inspect before sharing. No extra fetch or external API is added.
- Missing candidates on article-like pages give a low conditional review, not
  a missing-date verdict. Nonarticles without candidates get no date instruction.
  Dates can exist outside the selected prefix, in unsupported formats or in
  omitted metadata. Selected-text extraction may remove real date information;
  normalized metadata is parser-dependent, not an independent HTML5 projection.
- Historical IDs `content.no.visible.date.signal` and
  `content.date.freshness.signal.present` stay stable; review title-based ignore
  filters for the new labels. Comparison's `date_signal` boolean now means a
  shared candidate was captured: modified metadata and date-like text can turn
  it true; blank metadata and bare years alone no longer do. Missing/unsupported
  legacy receipts remain unrecorded; do not reconstruct scope from the boolean.
- Comparisons/briefs no longer generate `Publish/update date` gaps/leads. Their
  renderers suppress those known legacy prescriptions without changing saved
  JSON. Candidate counts are neutral observations, not date quotas. Current and
  legacy missing-date plans keep edits review-required and conditional on known,
  useful information. Other checks and fetch guards remain unchanged. Corrected
  date findings can change tool scores without any page or measured SEO gain.

## Readability
- Aim for scannable prose: short paragraphs, ~15–20 words/sentence average,
  descriptive subheads, lists where appropriate.
- The auditor reports a **Flesch Reading Ease** score and an approximate
  **Flesch–Kincaid grade level**: 70+ is easy, 50–70 moderate, 30–50 difficult,
  <30 very difficult. Match the target to your audience — general-audience content
  should usually land 50+; specialist/technical content can be denser.
- Readable content is also more *quotable* — see `geo-llmo.md`.

## Topical focus
- The auditor extracts the page's most frequent terms and phrases (its "dominant
  topics") and candidate entities. If none of the **title/H1** keywords appear
  among the body's top terms, the page may not actually develop the topic it
  promises — bad for ranking and for AI topical grounding. Keep the title, H1, and
  body reinforcing one clear subject.

## Social / preview metadata
- Open Graph (`og:title`, `og:description`, `og:image`) and `twitter:card` don't
  affect ranking but control how links render in social feeds and chat apps,
  which drives clicks and shares (an indirect authority signal).

## The AI-content question
- AI assistance isn't penalized per se; low-quality, unhelpful, unoriginal
  content is — regardless of how it was produced. The guideline test is whether
  the page helps the user better than what already exists.
- Attribution/date cues, specifics, sources and wording need contextual review.
  Their presence or absence cannot identify AI authorship or establish quality;
  improvements should address actual reader needs and supporting evidence.

<a id="filler--ai-writing-detection"></a>

## Filler & phrase review
- The content auditor flags **filler/padding phrases** ("in today's fast-paced
  world", "when it comes to", "needless to say"…) and **configured common phrases**
  ("it's worth noting", "delve into", "a testament to", "unlock the potential"…),
  plus low **lexical diversity** (repetitive vocabulary), with example matches.
- A match is a prompt for **editorial review**, not evidence of AI authorship,
  poor quality, unoriginality or a search penalty. Even literal subject words
  such as "tapestry" can match. Read the context and intended audience before
  deciding whether any edit is useful; accurate, useful wording can stay.
- Two or more distinct common-phrase matches produce a low-priority advisory;
  four or more no longer become a medium-priority authorship/ranking warning.
  The thresholds are unvalidated editorial defaults, not measured SEO risk.
- An absence of these matches does not prove originality, helpfulness or human
  authorship either. Vocabulary variety is a count, not an assessment of truth.
- Historical `ai_*` helper keys and finding rule IDs remain for compatibility,
  not as detector claims. Displayed titles have changed, so update title-based
  `[ignore].titles` filters if they used the previous AI-sounding labels.
  A score change caused by the priority correction is not a page improvement.
- Google's [guidance on generative AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)
  emphasizes accuracy, quality, relevance and value for users, rather than these
  phrase lists. Narwhal does not measure those outcomes from phrase counts.
