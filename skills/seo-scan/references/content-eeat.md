# Content quality & E-E-A-T reference

Google's Search Quality Rater Guidelines reward content that demonstrates
**E-E-A-T**: Experience, Expertise, Authoritativeness, Trustworthiness. Raters
don't set rankings directly, but the systems are trained to approximate their
judgments. The content auditor surfaces heuristic proxies for these signals.

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
- Name a qualified **author** with a bio and credentials. Anonymous
  "Your-Money-Your-Life" content (health, finance, safety) is held to a much
  higher bar.

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
- Warning signs the auditor approximates: no author, no dates, no specifics, no
  sources, filler phrasing. Fixing those usually means adding genuine expertise.

## Filler & AI-writing detection
- The content auditor flags **filler/padding phrases** ("in today's fast-paced
  world", "when it comes to", "needless to say"…) and **AI-writing patterns**
  ("it's worth noting", "delve into", "a testament to", "unlock the potential"…),
  plus low **lexical diversity** (repetitive vocabulary), with example matches.
- These are *signals*, not proof — a few is fine; a high density suggests hollow or
  generically-generated content. The fix is always the same: replace cliché phrasing
  with concrete, first-hand specifics, data, and examples.
