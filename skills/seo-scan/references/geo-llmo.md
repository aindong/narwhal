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

## AI-crawler access — the make-or-break check
An answer engine can only cite a page its crawler is **allowed to fetch**. Check
`robots.txt` for these agents and decide deliberately:

| User-agent | Engine |
|---|---|
| `GPTBot`, `OAI-SearchBot`, `ChatGPT-User` | OpenAI / ChatGPT |
| `ClaudeBot`, `Claude-Web` | Anthropic / Claude |
| `PerplexityBot` | Perplexity |
| `Google-Extended` | Google Gemini / AI Overviews |
| `CCBot` | Common Crawl (feeds many LLMs) |

If you *want* AI visibility, don't `Disallow: /` these. If you're protecting
content, blocking them is legitimate — the auditor flags the state so the choice
is intentional, not accidental.

## llms.txt — low cost, low certainty
`/llms.txt` is a proposed markdown file pointing AI crawlers to your key content.
Adoption by major engines is still limited and there's **no strong evidence** it
moves rankings today. Treat it as a cheap, optional bet — publish it if trivial,
but don't oversell it, and don't let it displace the fundamentals above.

## Myths worth rejecting
- "Just add llms.txt and you'll rank in AI." — no evidence.
- "Stuff pages with AI keywords / 'as an AI language model' bait." — spam.
- "GEO replaces SEO." — it's an extension of it, not a replacement.
Optimize for genuinely helpful, well-structured, attributable content; the AI
citations follow the same quality signals as classic ranking.
