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
- < ~300 words of main text usually reads as thin — it rarely satisfies intent
  and is seldom cited by AI answers. The fix is *coverage*, not padding.
- Depth means answering the obvious follow-up questions, covering edge cases, and
  including specifics (numbers, examples, steps) a generalist couldn't fake.
- Match length to intent: a definition page can be short; a "best X for Y" guide
  usually can't.

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
  field-limit exhaustion is explicit. These are not total CPU/heap guarantees.
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

## Freshness
- Show a published and/or last-updated date. Freshness matters most for topics
  that change (news, prices, "best of {year}", software).
- Don't fake updates — changing only the date without substantive edits is a
  pattern raters and systems penalize.

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
