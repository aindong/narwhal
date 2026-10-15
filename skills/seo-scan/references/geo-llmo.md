# GEO / LLMO reference — optimizing to be cited by AI answers

**GEO** (Generative Engine Optimization), also called **LLMO** (LLM Optimization)
or **AEO** (Answer Engine Optimization), is about being *quoted and cited* by AI
answer engines — ChatGPT, Claude, Perplexity, Google AI Overviews — not just
ranking in classic blue links.

## First principle: GEO is mostly good SEO, plus structure for extraction
Google's own guidance is blunt: there's no separate "AI SEO" trick — the same
helpful, well-structured, trustworthy content wins. What GEO adds is optimizing
for **passage-level extraction**: an answer engine lifts a *chunk* of your page,
so each chunk must be quotable and self-contained. Be skeptical of vendors
selling GEO as a distinct dark art.

## The signals the auditor scores

### 1. Question-based headings
Answer engines match user questions to question-shaped headings. Rewrite key
H2/H3s as the actual questions people ask ("How does X work?", "What is Y?").
Target: a meaningful share of subheads are questions.

### 2. Citable, self-contained passages
Models quote passages best when they stand alone without surrounding context and
sit in a digestible size band (roughly 40–120 words per passage). Avoid giant
unbroken blocks *and* a page of tiny fragments. Each answer paragraph should make
sense if pasted on its own.

### 3. Evidence density
AI answers favor and attribute content with concrete evidence: statistics, dates,
named studies, and citations ("According to a 2024 study, 40%…"). A page with
zero numbers or sources is easy to ignore.

### 4. Direct-answer intro (inverted pyramid)
Lead with a 1–2 sentence direct answer or definition before the details. AI
overviews and featured snippets lift the top summary; burying the answer costs
you the citation.

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
or proof an engine used it. Root 404/410 observations do not establish absence
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
Optimize for genuinely helpful, well-structured, attributable content; the AI
citations follow the same quality signals as classic ranking.
