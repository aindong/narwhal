<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark-512.png">
    <img src="assets/logo-512.png" alt="Narwhal logo" width="240">
  </picture>
</p>

<h1 align="center">Narwhal</h1>

<p align="center"><strong>Local-first SEO &amp; GEO/LLMO scanning — as an agent skill.</strong></p>

<p align="center">
  Inspect pages and sites for SEO <em>and</em> AI-answer visibility signals
  <br>(ChatGPT · Claude · Perplexity · Google AI Overviews) — straight from your coding agent.
</p>

<p align="center">
  <a href="https://github.com/aindong/narwhal/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/aindong/narwhal/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-2ea44f">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8%2B-3776ab?logo=python&logoColor=white">
  <img alt="Agents: Claude Code, Codex, Cursor, OpenCode" src="https://img.shields.io/badge/agents-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Cursor%20%C2%B7%20OpenCode-1f6feb">
  <img alt="Local-first" src="https://img.shields.io/badge/data-local--first-14b8a6">
  <img alt="Dependencies: zero required" src="https://img.shields.io/badge/deps-zero%20required-8957e5">
</p>

<p align="center">
  <img src="assets/demo.gif" alt="Narwhal terminal demo: scan, audit, and Core Web Vitals" width="760">
</p>

Narwhal scans a web page or whole site for **SEO** and **GEO/LLMO** (visibility in
AI answer engines) and hands back a **prioritized, fix-first report**. It ships as
an agent skill: use it from Claude Code via
[`SKILL.md`](skills/seo-scan/SKILL.md), or from any agent that reads
[`AGENTS.md`](AGENTS.md) — Codex, Cursor, OpenCode, and friends.

Default scans need no accounts or API keys and send no telemetry. They fetch the
requested site and related audit resources; external data integrations are
opt-in. Narwhal runs on a bare Python install, with additional extraction and
rendering paths available through optional libraries.

Use Narwhal as an **audit assistant, not a final SEO verdict**. Check findings
against their evidence and your site's intent before changing anything. Its
score summarizes reported findings, not page quality or measured ranking/AI
citation performance. Passing tests do not establish real-world accuracy; see
[how to interpret scores and verification](docs/tuning/README.md#how-to-interpret-scores-and-verification).

## Why "Narwhal"?

The narwhal is the perfect mascot for a search-and-AI-visibility tool:

- **The tusk is a sensor, not a weapon.** A narwhal's tusk is packed with millions
  of nerve endings that read tiny changes in the water around it. Narwhal the tool
  does the same for a page — it senses the subtle, easy-to-miss signals (meta,
  canonical, schema, crawler directives and editorial text cues) that help you
  investigate a page's presentation and accessibility—not predict visibility.
- **It navigates dark, opaque water.** Narwhals thrive in deep, ice-covered Arctic
  seas using sound, surfacing where nothing else can. Modern search and AI answer
  engines are exactly that kind of murky water — Narwhal helps you navigate it.
- **The "unicorn of the sea."** Rare and unmistakable. That's the whole goal of SEO
  and GEO: to be the distinctive result that ranks and gets *cited* by AI, not one
  of the anonymous many.
- **It dives deep.** Deep audits, not surface-level checks.

And yes, it works as a backronym too:
**N**avigate **A**I **R**ankings, **W**eb **H**ealth **A**nd **L**LM-visibility.

## What it checks

| Area | Highlights |
|---|---|
| **Technical SEO** | title/meta, headings, canonical, robots directives, viewport/mobile, hreflang, images, links, HTTP hygiene, robots.txt, sitemap |
| **Content & E-E-A-T** | scoped text-length/readability cues, author/date candidates, Open Graph / Twitter cards |
| **Structured data** | JSON-LD + Microdata + bounded schema.org RDFa detection, required/recommended property validation, merchant checks, source-backed Google feature-retirement notes, JSON-LD generation |
| **E-commerce** | evidence-gated Product detection; Product/Offer/AggregateOffer completeness; variants; expired prices; visible-vs-schema price, currency, availability, SKU, and brand consistency |
| **GEO / LLMO** | contextual review of question-heading, sentence-group, statistic/citation and intro cues—not measured citability—plus `llms.txt` and role-aware **search/retrieval robots policies**, with separate non-scoring training/data-use notes |
| **Search performance** *(opt-in)* | real Google Search Console query data: striking-distance queries, CTR laggards, decaying pages, keyword cannibalization |
| **Site structure** | sampled click depth and start coverage, orphan-page candidates (sitemap vs crawl), inbound-link counts (not measured link equity) — observations stay visible even with zero inter-page edges |
| **Competitor gaps** | `narwhal compare <you> <rival…>`: same auditors on every page, then a gap analysis — schema types, meta strategy, structure, social packaging, with separate neutral length and statistic/citation-pattern observations (local-first; on-page facts only). Your first URL must load as HTML; failed competitors can be skipped, but never become "You". |
| **Content briefs** | `narwhal brief <you> <rival…>`: a data-driven writing plan — your page's real striking-distance GSC queries + competitor gaps, heading-review candidates, questions to review, schema and structure candidates. No keyword APIs; without GSC it's a clearly labeled structure-only brief |

GEO text-cue checks expose literal counts and limits in `meta.geo_text_cues`.
English-oriented patterns do not measure answer accuracy, actual paragraphs,
source validity or citation likelihood. Their low-priority advice keeps edits
conditional; configured ranges and matches are not engine requirements. Legacy
rule IDs remain, but displayed titles change. Priority corrections can raise a
score without changing a page. See the [check boundaries](skills/seo-scan/references/geo-llmo.md#text-cue-output-and-compatibility).

Attribution checks capture bounded metadata, author-link and short leading
byline-like **candidates**, not verified writers or expertise. Ordinary prose
words and blank author metadata do not pass. Missing article cues prompt low
contextual review, not an anonymity verdict; never invent people or credentials
to close a finding. Scans and comparisons use the same observer, with JSON
receipts and literal page-report witnesses. See [scope and limitations](skills/seo-scan/references/content-eeat.md#attribution-cues-not-identity-verification).

Date checks likewise record bounded metadata/selected-text **candidates**, not
verified publication/update dates or freshness. Scans, comparisons and briefs use
the same observer: modified-only metadata counts, blank metadata and a copyright
year alone do not. A missing article cue invites conditional review, not invented
dates or cosmetic refreshes; compared pages do not set a date quota. See
[date-cue scope and compatibility](skills/seo-scan/references/content-eeat.md#date-cues-not-freshness-verification).

Common-phrase checks are editorial review prompts, not AI-authorship detectors.
Quoted examples may be appropriate for the audience; neither matches nor their
absence establish originality, helpfulness or ranking impact. The four-distinct-phrase
advisory is now low priority (previously medium), so that score correction is not
a page improvement. Stable rule IDs remain; update title-based ignore filters
for the [revised labels and interpretation](skills/seo-scan/references/content-eeat.md#filler--phrase-review).

Configured filler-list matches and vocabulary ratios are also low contextual
reviews, with exact ASCII-pattern counts and extraction basis—not padding or
thin/spun-content diagnoses. Keep useful quoted text and consistent terminology;
do not substitute synonyms solely to change a count. Legacy rule IDs remain,
but title-based ignore filters may need updating. Priority calibration is not a
measured website improvement.

Canonical comparisons preserve scheme, path/query case, separators and query/
fragment distinctions rather than collapsing different targets. Limited standard
normalizations and the first non-template href-bearing HTML base are handled
locally, without target requests. Page checks and duplicate clusters share the
same key; `canonical_ok` means matching supported target observations, not verified
consolidation or a search-engine-selected canonical. Unsupported/malformed
declarations stay manual and qualify scores/diffs/comparisons instead of becoming
passes or absence fixes. See [comparison boundaries](skills/seo-scan/references/technical-seo.md#canonicalization).
Literal Unicode path/query/fragment text and its UTF-8 percent encoding compare
consistently; non-ASCII hostname/IDNA comparisons remain unverified.

Page content-length checks report literal ASCII-pattern counts, not universal
word counts or a thinness verdict. Declared non-English text or non-ASCII
letters/marks leave the length threshold uninterpreted, with a non-scoring
coverage note. Applicable below-bound reviews are low priority, not instructions
to reach 300/600 words. Useful concise text can stay. See the
[measurement scope and compatibility](skills/seo-scan/references/content-eeat.md#page-text-length-observation).

Comparison/brief length observations use a different preserved measurement:
Python whitespace-separated tokens, not linguistic words. Counts do not create
content-depth gaps/leads or automatic writing targets. JSON keeps the historical
`words` alias with an explicit `text_length` receipt; briefs no longer generate
`structure.target_words`/`your_words`. Legacy values without a recognized basis
stay unverified. Explicit user/editorial length goals remain separate. See
[comparison and brief compatibility](skills/seo-scan/references/content-eeat.md#comparison-and-brief-length-observations).

Readability reports expose the historical ASCII-token/punctuation-fragment/
vowel-group inputs and Flesch/FK formula estimates, not measured comprehension,
school grade or AI citability. Below-range reviews are low and contextual; useful
concise or specialist text can stay. Non-English declarations, non-ASCII letters/
marks, hub hints or unusable inputs leave interpretation unassessed. No minimum
word count or universal formula target is imposed. See
[readability boundaries](skills/seo-scan/references/content-eeat.md#readability).

Native page/site-audit HTML keeps measurement counts and uncertainty in a compact
overview. Expand **Inspect detailed evidence and limits** with a click or keyboard
to read every witness and caveat. Print/PDF includes all details even if collapsed;
no JavaScript is required. Priorities, quick wins and resource/coverage warnings
remain outside the disclosure. JSON and Markdown stay unchanged. The HTML contains
mutually exclusive screen/print detail copies; use JSON for recorded facts, not
counts of duplicated DOM text.

Lexical-focus checks expose the existing top-eight ASCII-term list and exact
title/first-H1 overlap, not dominant topics or semantic coverage. A title term
may occur outside the cutoff; ties and synonyms can change the heuristic without
an intent mismatch. Review actual wording and purpose, without keyword stuffing
or forced overlap. Counts, selection and score contributions stay unchanged.
See [lexical scope and compatibility](skills/seo-scan/references/content-eeat.md#topical-focus).

Comparison/brief `stats_cites` values are retained lexical match counts, not
verified sources or evidence quality. New `evidence_cues` receipts split statistic
patterns from English-oriented citation cues and explicitly leave source validity
unchecked. They do not produce evidence-density gaps or automatic source quotas;
brief `evidence_target`/`your_evidence` fields are no longer generated. Missing
legacy bases stay unverified. Review actual claims and relevant sources rather
than add numbers to satisfy a count. See [cue boundaries](skills/seo-scan/references/geo-llmo.md#comparison-and-brief-cue-observations).

Question-heading comparisons retain the legacy rounded `question_ratio` but use
explicit `question_cues` counts for one-in-five heuristic decisions. Thus 8/41
is not treated as 20%. Counts/basis missing from older reports stay unverified,
and no eligible headings is not an assessed zero fraction. Questions remain
optional, not proof of real query demand or engine matching. Brief question
candidates label `source_kind` as `compared_heading` or `gsc_query`; older missing
kinds are not inferred from source strings. See [exact-count boundaries](skills/seo-scan/references/geo-llmo.md#exact-heading-cues-in-comparisons-and-briefs).

Compare facts retain `schema_search_features`, the same dated Google retirement
snapshot used by page scans. Brief semantic schema candidates carry per-type
`google_search_appearance` notes, including automatically suggested FAQPage.
These distinguish retired Google appearances from useful schema.org semantics;
generation/types remain available. Missing or unsupported legacy snapshots stay
unverified, and no listed retirement notice is **not** an eligibility certificate.
No policy sources are fetched at scan/render time. See [scope and compatibility](skills/seo-scan/references/schema.md#comparison-and-brief-appearance-context).

Brief `missing_subtopics` is a preserved candidate field, not verified missing
semantic content. New `subtopic_review` and per-candidate `term_match` receipts
explain the ASCII/English prefix-term basis and exact match counts/cutoff. Synonyms
can be missed and unrelated word occurrences can match. Compared H2/H3 labels do
not establish their section content, query demand or ranking gaps. Topic mode has
no own-page match measurement; legacy missing receipts stay unrecorded. Review
relevance and existing coverage before adding sections, preserving editorial choices.

Known structured-data extraction problems are not evidence that markup is absent.
`schema_extraction` facts and page `meta.structured_data.extraction_coverage`
record JSON-LD processing errors and retained Microdata/RDFa warning-detail counts.
Comparisons withhold absence-based schema claims when their required coverage is
unverified; brief candidates remain available but require inspecting existing
markup. Observed types remain visible, with schema/overall comparisons labelled
unverified. Page/audit `diff --fail-on-regression` exits 2 for known schema-extraction
uncertainty, including crawl contributions. Missing legacy coverage is not backfilled
or certified complete. See [extraction boundaries](skills/seo-scan/references/schema.md#known-extraction-uncertainty).

Page scans likewise withhold generic/Article/site-entity/Product absence advice when
extraction has known gaps, while retaining observed syntax/property checks.
Remediation plans make extraction verification manual-only, not source-generation
work, and do not repeat contradictory legacy absence advice for uncertain scopes.
Clean-scan non-observations remain conditional reviews, not feature promises or
whole-site identity checks. See [page/planner behavior](skills/seo-scan/references/schema.md#page-advice-and-remediation-under-uncertain-extraction).

JSON-LD syntax errors are distinct from tool-processing failures. Decoder
`JSONDecodeError` findings remain high repair candidates; other caught decoder/
node failures are low verification notes (`schema.jsonld.processing.unverified`),
not proof of invalid source or engine rejection. `jsonld_error_stages` records
runtime counts; legacy missing stages are not inferred. Limits remain intact,
and both kinds still leave score comparisons unverified. See [error-stage scope](skills/seo-scan/references/schema.md#json-ld-syntax-versus-processing-failures).

Page-report **Quick wins** include reported observation/evidence previews, not
only advice. Each field shows its first 400 whitespace-normalized characters,
plus an omission marker when clipped. Full fields remain in JSON.
Markdown/native HTML/PDF input keeps preview markup literal. These are scanner-reported fields, not
independent verification or proof that an edit is appropriate. Scores, severity,
IDs and recommendations are unchanged.

Site-graph ranked lists use URL order to break equal inbound-link or depth
ranks before display caps. For the same fixed sample, process hash seeds no
longer change which tied pages enter the top-five JSON or top-three Markdown
most-linked list. That tie-break-only change kept numeric priority, counts,
URL identities and scores unchanged; it did not certify complete site coverage.

Crawl discovery, graph nodes/orphan candidates and hreflang matching now group
only fragment aliases, scheme/host case and empty root paths. Non-root trailing/
repeated slashes, semicolon path data and query literals remain distinct. Graph
JSON records `url_identity_basis`; missing legacy policy stays unverified. This
is observed-address grouping, not canonical/redirect/content equivalence.
Graph counts and which pages fit a fixed crawl cap can change, without changing
per-page rules. Audit diffs with current versus unrecorded/different identity
policy withhold fix claims and exit 2 under `--fail-on-regression`; even matching
policy does not prove an identical sample or a website improvement.

Zero recorded inter-page edges no longer hide known unreachable/zero-inbound
URLs, orphan candidates or sample limits. Graph JSON adds `depth_coverage`
(`basis`, `start_present`, `reachable_nodes`, `unreachable_nodes`): BFS over
supplied edges only, not verified crawler access, link equity or ranking.
Depth applies only to reachable nodes; an absent start leaves depth unassessed
even though the historical raw `max_depth` placeholder stays 0. Legacy/malformed
receipts remain unrecorded/unsupported, not inferred. Deep/unreachable/zero-inbound/
orphan lists retain their existing caps with explicit omission counts; inspect
extraction/sampling before editing the site or raising crawl limits. Graph
measurements, fetching and scores stay unchanged.

Relative anchor references such as `guide//chapter` now retain their path
separators when merged with the page URL; `guide/chapter` is a distinct observed
target, not an inferred alias. Collection, fallback crawl discovery and optional
link checks share this resolution. Crawl JSON records `link_resolution_basis`;
audit diffs with a known current versus missing/different policy withhold site-fix
claims and exit 2 under `--fail-on-regression`. Corrected targets can change fixed-cap
selection, graph counts and averages without a site edit. Host/redirect guards,
caps and per-page scoring rules are unchanged. This bounded path correction is
not complete browser/WHATWG conformance: encoded-dot handling and empty-query
transport behavior are not certified by this receipt.

Anchor source checks, collection and fallback discovery now use the first
non-template href-bearing `<base>` when supported (including an explicit empty
first href, rather than a later base). Internal/external classification remains
relative to the fetched document host, not the base host. A base does not grant
fetch permission or expand the same-host crawl boundary. Raw-text/RCDATA
lookalikes do not inject a base into the shared source reader.

Page `meta.anchor_resolution_basis` and crawl `link_resolution_basis` record the
v2 policy; optional `anchor_base` receipts describe declared-base scope without
retaining raw base values. Unsupported/malformed bases and a detected CSP
`base-uri` directive stay unassessed: base-dependent targets are omitted, not
invented or called dead/malformed anchors. Absolute HTTP(S) anchors remain
independently assessable. Separate omission counts and unscored notes survive
page/site HTML, Markdown and PDF; known gaps and current/legacy policy changes
withhold score-improvement claims in diffs, comparisons and briefs. The previous
v1/missing-policy audit guard remains. Counts or averages can change because
target selection was corrected, not because the website improved. This bounded
declaration resolver does not verify CSP enforcement, scripting/noscript or a
complete browser DOM/URL implementation. See [scope details](skills/seo-scan/references/technical-seo.md#declared-anchor-bases).
Malformed-URL warnings from the shared markup tree omit raw values (including
credentials), using bounded extraction-local reference IDs to retain warning
deduplication and caps. This is diagnostic redaction, not a claim that all user-
supplied/report URLs are secret-free.

HTML hreflang uses the declared source URL, not a fabricated absolute target.
Malformed, relative/scheme-relative, non-HTTP and unsupported references are
counted and omitted from relationship/probe analysis; other auditors still run.
Page/crawl `hreflang_policy_basis` and `hreflang_extraction` receipts distinguish
parsed declarations, supported URLs and omission reasons without echoing rejected
values. They do not validate full URI syntax, codes/head placement, translated
content, HTTP-header/sitemap alternatives or search acceptance.

Incomplete/omitted target snapshots are unassessed, not missing return tags or
dead pages. Production same-host probes require complete HTML with recorded
matching URL identity, retain existing request/redirect/SSRF limits and do not
re-fetch sampled pages. Reports keep counts, bounded literal lists and legacy
uncertainty visible without a green cluster certificate. Known gaps and policy
changes guard technical-score diffs/compare/brief; content-only scores are not
invalidated by unselected technical checks. The new low source review is manual
in remediation plans, and x-default advice is conditional, not a page quota.
Corrected findings or sampled relationship counts are not measured SEO gains.
Page `hreflang_source_observation` receipts and crawl
`hreflang_acquisition_basis` also qualify already crawled responses before using
their tags at a requested URL. Changed final identities, empty response bytes,
unknown HTML media types and partial/unavailable bodies remain unassessed and
do not seed probes. A final page can still be scanned normally after a redirect;
its facts and score are not reassigned as proof of annotations at the old URL.
See [hreflang scope](skills/seo-scan/references/technical-seo.md#hreflang-reciprocity-cross-page).

Transport success requires a final 2xx response without a recorded fetch error.
Terminal 3xx responses, including a 304 without a cached representation, do not
receive measured page-health scores or become successful plain-text resources.
Normal redirects are still followed within existing guards/budgets and use the
successful final response. A 2xx status alone is not complete HTML, access,
indexability, search acceptance or page-quality proof; consumer coverage checks
still apply, including partial and empty response handling.

For page audits, primary HTTP 206 or any Content-Range evidence leaves the full
page unassessed before extraction. Reports retain observed status and a bounded
positive `coverage.server_range` receipt, not the raw header, with no completed
auditor groups and a fail-safe zero rather than measured page health. Ranged
served baselines also cannot support served/rendered comparisons. Current and
known historical evidence blocks comparison/brief/diff fix claims and CI gates;
remediation stays manual, without guessed metadata owners or automatic retries.
Complete pages and explicitly byte-limited scans keep their existing paths.
This does not validate HTTP range syntax or certify every other response complete.
The complete-byte resource downloader also withholds 206/Content-Range bodies
before reading or decoding them, so a complete-looking XML fragment cannot be
promoted into a verified sitemap root. Root llms.txt uses header presence, not
truthiness, for range evidence: an empty marker is still unverified. These are
separate completeness checks, not changes to generic 2xx transport success or
the intentional ranged image-header probes.

Root `llms.txt` checks record HTTP response evidence in `meta.llms_txt`: a
complete supported text response with an initial ATX/simple Setext H1 is a
candidate, complete 404/410 is observed root absence, and HTML fallbacks, gates, empty,
partial or truncated responses remain unverified. Unverified responses create
neither a published-file pass nor a missing-file penalty; known HTTP uncertainty
blocks GEO score comparisons/diffs/briefs and yields manual-only plan verification.
Legacy caller flags retain stable finding IDs but are labelled unverified context.
This is a **root request only**, not independent subpath/`rel=describedby` discovery,
full proposal validation, linked-file checking, engine use or a ranking guarantee.

Robots readers ignore one optional file-start UTF-8 BOM, so the first user-agent
group or Sitemap declaration is not lost. Literal markers within paths remain
data; this does not change robots HTTP-error policy or the explicitly requested
crawl-base override.

Robots wildcard matching searches ordered literal pieces without enumerating
star partitions. Repeated-star rules no longer stall candidate filtering;
prefix/end-anchor semantics, encoded literals and Allow/Disallow precedence are
preserved. This does not impose a whole-crawl CPU or network-work budget.

The bare-Python HTML/text fetch path retains the guarded terminal URL and
observed redirect hops even for HTTP errors, so reports and root-resource
receipts identify the response actually fetched. Origin `Content-Location`
claims cannot replace that identity; status/body limits and network guards are
unchanged. This is not a transfer-completeness guarantee.

The generic page robots-meta check combines all active `name="robots"` tags,
recognizes exact `noindex`/`nofollow` names and the `none` alias, and does not
mistake directive parameter values or substrings for restrictions. Its passing
message is scoped to generic meta only. A separate non-scoring observation covers
documented `googlebot` and `googlebot-news` meta declarations of `noindex`,
`nofollow` and `none`, retaining bounded active-tag positions in
`meta.crawler_meta_robots`. It does not calculate effective cross-source policy,
interpret other crawler names or preview/date rules, or recommend removing an
intentional restriction. Unknown names are not assumed to be crawler policies.
Absence of a generic meta restriction does not prove
indexability or actual search inclusion.

Final HTML-response `X-Robots-Tag` headers are checked separately for unprefixed
`noindex`/`nofollow` (including `none`). Named-crawler restrictions are non-scoring
policy observations in reports and `meta.http_robots`, not universal crawler
blocks. Raw transports retain duplicate fields; browser/legacy transports record
their field-boundary limits. Preview/date directives and real indexing are not
evaluated. Header fixes are manual hosting/CDN/middleware actions, not HTML edits.
Rendered scans fail explicitly if another main-document request starts after the
initial navigation: earlier response headers cannot safely describe a replacement
document. Scan the final destination directly. Normal HTTP redirects and
same-document History API changes remain supported.

Crawl JSON retains these HTTP/named-meta receipts on each successfully scanned
page, including leaf pages. Crawl Markdown and comprehensive audit reports show
up to ten sampled pages and eight notes per page, with display omissions labelled
and full receipts retained in JSON. These notes add no score penalties or
whole-site/indexing guarantees; generic HTTP findings remain in the normal
score/issue rollup. Failed or legacy pages do not imply a policy observation.

Page reports record `meta.ai_crawler_access`: dated agent roles, primary sources,
and robots.txt root disallowance results at **`/` only**. Training/data-use choices,
nonbinding user-fetch directives and unverified roles remain visible as
non-scoring policy notes, not search failures or policy endorsements. Documented
search/retrieval restrictions retain the high finding, conditional on owner goals.
This does not test live bot/WAF access, other paths, indexing or citations. See the
[GEO reference](skills/seo-scan/references/geo-llmo.md#ai-crawler-policies--distinguish-purpose-before-recommending-access)
for the role distinctions and source scope; no policy service is called by scans.

Non-passing page findings include **Learn more** links in Markdown/HTML (and PDF
input), plus an additive `reference_url` in JSON. Known rule IDs select guide
sections; unmapped rules in built-in categories receive general category context.
Unknown categories and passing checks have no reference link. These are static
project-guide links, not proof that a heuristic finding is correct; scans do not
fetch them, and scores/rule identities are unchanged.

`compare` and `brief` retain each page's actual `rendered` boolean in JSON facts
and label its HTML source in reports: served HTML or JavaScript-rendered DOM.
Mixed modes are labeled per page; legacy missing flags stay unknown. This is
snapshot provenance, not proof that every dynamic element finished loading.

For large HTML pages, both commands accept `--max-bytes N` (default 5,000,000;
clamped to 64,000–20,000,000), as do their Python `run(..., max_bytes=N)` APIs
and MCP `compare_pages` / `content_brief` tools. One selected limit applies to
each page's primary HTML and, when rendering, its served-HTML baseline. Retry
known incomplete coverage with a sufficient budget; inputs that still exceed
the cap remain excluded rather than silently compared. This is a per-snapshot
retained HTML limit, not a total network, browser-memory or site budget.

`compare` and `brief` exclude scans explicitly marked as truncated. Partial
targets return errors (CLI exit 2); partial competitors are skipped with reasons.
Topic mode needs at least one usable page. Standalone `scan` still emits partial
findings with coverage warnings. Missing/malformed legacy flags are not inferred
to prove truncation or complete coverage.

The primary HTML budget (`scan --max-bytes`, 64KB–20MB) also applies to a rendered
DOM's retained UTF-8 snapshot. Truncation is explicit, without a broken final code
point; JS-dependence is not measured from that incomplete DOM. This is an analysis
input limit, not a cap on Chromium's DOM memory or subresource network traffic.

Rendered scans use the same selected byte budget for their served-HTML baseline.
`meta.coverage.js_comparison` records `measured` or `unverified`, the byte limit,
and an unverified reason. Missing, partial or explicitly non-HTML baselines do
not yield numeric JS-dependence statistics. A complete rendered DOM is not
relabelled as truncated when only its baseline is unavailable. Relevant
technical/GEO score comparisons with a known unverified JS measurement are
incomparable (`diff --fail-on-regression` exits 2); compare/brief skip those page
scores with diagnostics. Legacy missing receipts remain unverified, not inferred.

## Multi-agent deep audit

`/narwhal audit <site>` (in Claude Code) is more than a script — it's a
**parallel, multi-agent** audit:

1. Runs the deterministic baseline (`audit.py`) for fast, reproducible hard data
   (homepage + site crawl + sitemap, per-area subscores, broken links, duplicates).
2. **Fans out ~10 specialist subagents in parallel** — technical, content, schema,
   geo, performance, links, duplication, sitemap, sxo (+ local or e-commerce when relevant). Each
   runs the deterministic scripts as its **tools**, then adds expert reasoning and
   exact fixes for its domain.
3. **Synthesizes** one report: an SEO Health Score, executive summary, prioritized
   action plan (Critical → Low), and quick wins.

The scripts do the **measurement** (fast, zero-dep, reproducible); the agents do the
**reasoning** (business context, what heuristics miss, concrete fixes). Specialist
definitions live in [`agents/`](agents/). The other actions (`scan`, `crawl`,
`sitemap`, `llms`, `schema`) run directly for quick, deterministic output.

## Fix it, don't just report it

The audit *finds*; **`/narwhal fix <site>`** closes the loop. When the site's
source code is in your working directory, it maps each finding to the file that
owns it (title/meta, canonical, Open Graph, JSON-LD, alt text, robots.txt,
`llms.txt`…), applies minimal framework-idiomatic edits, then **re-scans and
diffs** to prove the score moved — resolved findings and the delta, from
`diff_scan.py`, not vibes.

It's honest about what a local re-scan can verify: page-level fixes check out
against a local preview; site-level signals (robots.txt, sitemap, HTTPS) are
labeled *verify after deploy*. If the source isn't in the workspace, it makes no
edits and hands you a per-finding fix plan instead. A SaaS auditor emits a PDF —
Narwhal emits a diff.

Before editing, `narwhal plan before.json --repo .` produces a versioned,
read-only remediation contract. It detects plain HTML, Next.js, Astro, Nuxt,
Hugo, or Jekyll; maps stable finding IDs to likely route/layout/static owners;
groups shared-template fixes; flags policy conflicts; and separates safe,
review-required, external, and post-deploy work. Use `--format json` for agents
or the concise Markdown default for humans. It proposes work but never edits.
See the [remediation-plan contract](docs/REMEDIATION_PLAN.md).

## Real search data (Google Search Console, opt-in)

Audits guess at priority from severity; **your own query data removes the
guessing**. `narwhal gsc <site>` pulls Search Analytics rows for your verified
property and answers "which page do I fix *first*":

- **Striking distance** — queries sitting at positions 8–20 with real
  impressions: the "push to page 1" list.
- **CTR laggards** — top-10 rankings whose CTR is far below the expected curve
  for that position: title/meta rewrite candidates.
- **Decaying pages** — clicks down ≥25% versus the previous period.
- **Keyword cannibalization** — several of your pages splitting one query
  (cross-check with the audit's near-duplicate clusters).

Add `--gsc` to `narwhal audit` and the same data lands in the report + JSON, so
`/narwhal audit` prioritizes by **real queries instead of severity guesswork**,
and `/narwhal fix` fixes the pages with actual search opportunity first.

**One-time setup (~3 minutes).** GSC has no API-key path, so this is OAuth
(read-only scope), all stdlib, credentials in your gitignored `.env`:

1. In [Google Cloud Console](https://console.cloud.google.com): enable the
   **Google Search Console API**, then *Credentials → Create credentials →
   OAuth client ID → **Desktop app***.
2. Put `GSC_CLIENT_ID=…` and `GSC_CLIENT_SECRET=…` in your `.env`.
3. Run `narwhal gsc --auth --write-env` — your browser opens Google's consent
   page; Narwhal catches the redirect on localhost and stores the refresh token.

Then just: `narwhal gsc https://your-site.com`. (Quick alternative, no client
setup: `GSC_ACCESS_TOKEN="$(gcloud auth print-access-token)"` — expires hourly.)
In a pinch for CI, mint the access token outside and pass it in; service-account
auth is deliberately not built in yet (it would require a crypto dependency).

## Quick start

```bash
# 1. (optional) install extras for better parsing + JS rendering
pip install -r skills/seo-scan/requirements.txt

# 2. audit a single page
python skills/seo-scan/scripts/scan.py https://example.com/page

# 3. audit a whole site (polite crawler: honors robots.txt, parallel, rate-limited)
python skills/seo-scan/scripts/crawl_site.py https://example.com --max-pages 25 --concurrency 4 --delay 0.5

# 4. generate valid schema.org JSON-LD
python skills/seo-scan/scripts/generate_schema.py Article \
  --field headline="How GEO works" --field author="Jane Doe"
```

Every report includes a 0–100 findings score and severity-grouped observations
with concrete fixes. Page scans record `meta.scan_scope` (`requested`, `completed`,
`not_selected` auditor groups). Focused scans label their **selected-check score**
and unchecked groups; it is not overall page health. All four groups running
does not mean site-wide or exhaustive validation. Fetch/non-HTML failures show
zero as a fail-safe, not measured health; old reports without scope do not infer
coverage from finding counts. Truncated HTML coverage stays explicit.

Native page-report HTML/PDF headlines follow the highest reported priority, or
say "No flagged findings" when none are present—not "Excellent" as an overall
quality verdict. The numeric score band stays secondary and explicitly describes
reported findings, not page quality. Scores, severity and machine-readable data
are unchanged; absent flags do not certify unchecked or unmeasured conditions.

### Useful flags (`scan.py`)
- `--render` — render JavaScript via Playwright (for SPAs) and compare the
  **paired served/rendered snapshots**: selected extracted-text equality,
  whitespace-token deltas, heading nonmatches and metadata presence/block counts.
  `js_dependence.text_comparison` records each extraction basis and signed delta.
  Legacy `words_raw`, `words_rendered` and `js_only_pct` numbers remain compatible;
  `js_only_pct` is only a positive net token-count increase / rendered count,
  not the percentage of content requiring JS. Equal/shorter counts can hide
  complete text replacements. Differences prompt low, manual verification before
  SSR/metadata rewrites; neither equality nor a delta measures crawler access,
  indexing or citation effects. See [scope and legacy limits](skills/seo-scan/references/technical-seo.md#js-dependence-raw-vs-rendered). Needs
  `pip install playwright` then `python -m playwright install chromium`. If the
  browser isn't installed you get a clear one-line fix, not a stack trace; a
  render that can't run reports an honest error rather than silently falling back
  to raw HTML.
- `--format json|html|pdf [-o file]` — machine-readable JSON, a **self-contained,
  styled HTML** report (score gauge, severity-coloured finding cards — see the
  [sample](docs/samples/sample-report.html)), or **PDF** (needs a PDF engine —
  **WeasyPrint** or **Playwright/Chromium**; falls back to HTML if neither is
  present). `html`/`pdf` also work on `audit.py` for a
  shareable, stakeholder-ready deliverable — and `audit.py --vitals` adds a **Core
  Web Vitals** section (CrUX field data, or PSI lab fallback) right into that
  HTML/PDF/Markdown/JSON:
  ```bash
  python skills/seo-scan/scripts/audit.py https://example.com --vitals --format pdf -o audit.pdf
  ```
- Crawl/audit `--max-pages` and `--concurrency` require positive integers,
  including configured defaults; invalid values fail before fetching (CLI exit
  2). CLI/API limits are not silently capped. MCP keeps its documented page
  (1–100) and worker (1–8) clamps.
- Sitemap URL probes select distinct exact URL strings at deterministic evenly
  spaced positions across parsed-file order, including endpoints when at least
  two are selected. A one-URL sample selects the first. `sample_selection` records
  the policy, requested cap and eligible distinct count; raw URL totals remain.
  This is not random or statistically representative, and a new selection can
  expose different failures on an unchanged sitemap.
- Link caps (`--max-links`) and sitemap file/sample caps (`--max-sitemaps`,
  `--sample`) require nonnegative integers, including consumed config defaults.
  Invalid caps fail before fetching (CLI exit 2). Zero skips the corresponding optional
  checks; sitemap discovery and other audit requests have separate bounds.
- Crawl `--delay SECONDS` spaces parallel page-scan starts; sequential mode
  retains its post-scan pause. The value must be finite and nonnegative. This
  paces page scans, not discovery, site resources or optional probe requests.
- `--only technical,content,schema,geo` — choose auditor groups; duplicates run
  once. For example, `--only schema` produces a focused structured-data report.
  Unknown names and empty comma-separated entries are rejected before fetching
  (CLI exit 2); MCP uses the same strict selection. Omit the selection or pass an
  empty string to run all four.
- `--fail-under N` — exit non-zero if the score is below `N`. Use it as a **CI
  quality gate** (also on `crawl_site.py`, where it checks the average score):
  ```bash
  python skills/seo-scan/scripts/scan.py https://example.com --fail-under 80
  ```
- `--allow-private` — permit localhost/staging targets (off by default; see below).

Expected HTTP acquisition or body-stream failures return a failed-fetch page
report with no measured area scores, including when optional `requests` is
installed. A failed stream is not analyzed as partial success. Use `--fail-under`
to make an unsuccessful scan fail a CI quality gate. HTTP error statuses and
bodies remain available for diagnostics; the `requests` path does not hide
unrelated processing errors.

An otherwise successful response with an unknown or non-text declared charset
produces a bounded failed-fetch diagnostic rather than an assumed fallback
encoding. Fix the server's `Content-Type` charset before treating that page as
measured; supported text encodings and replacement of malformed bytes retain
their existing behavior.

Expected URL syntax, DNS and host-policy failures in `scan`, `audit`, `crawl`,
`llms` and `sitemap` produce a bounded, single-line `ERROR: URL rejected: …`
diagnostic with exit code **2**; no report is created or overwritten. Python
page/site entry APIs raise `ValueError`-compatible `URLInputError` / `SSRFError`
instead. Invalid ports and malformed IPv6 are checked before transport; syntax
diagnostics do not echo parser errors containing credentials or query values.
Initial sitemap target
rejections do not produce error reports with exit 0, including direct XML inputs.
Private access remains an explicit choice for intentional local/staging scans,
never an automatic retry. This is
basic URL/host-policy validation, not a complete URL conformance validator;
unexpected programming errors are not suppressed.

Sitemap validation (also inside `audit`) records `parse_coverage` over fetched
files. Its bounded XML parser supports `urlset`/`sitemapindex` in the official
sitemap namespace, including prefixes, plus namespace-free compatibility. It
decodes XML character escaping and ignores foreign extension elements rather
than counting their locations as pages. Malformed XML, unsupported roots/entry
shapes, DTDs, or limits (128 nesting levels, 500,000 elements, 50,000 entries per
file) leave extraction unverified: all entries from that file are withheld,
valid siblings remain counted, and reports label the partial coverage. DTDs and
external entities are not loaded. Decoded input is capped at **52,428,800 bytes
per fetched file**, before UTF-8 conversion, using sized gzip reads of at most
64KiB and a one-byte overflow probe. Concatenated gzip members share that budget;
corrupt/truncated gzip and budget exhaustion withhold all text/entries/samples,
with fixed `parse_coverage.reasons` and a recorded `decoded_byte_limit`. The
ceiling follows the [sitemap protocol's uncompressed size limit](https://www.sitemaps.org/protocol.html),
but a budget note means extraction is unverified, not a complete validity verdict.
The legacy decode helper is bounded too. This is not XSD/protocol validation,
complete format support, a total Python heap/CPU bound or a transport budget.
Raw-fetch limits and existing network guards are unchanged.
The raw fetch stage retains at most **20,000,000 response-body bytes** and now
withholds the entire body on overflow rather than measuring a capped prefix.
Exact-limit success is distinguished from overflow; non-2xx responses and known
incomplete transfers also contribute no sitemap entries/samples. Failures appear
as fetch notes and a `fetch_failures` file count, not successful fetched files or
unsupported-XML findings. Mixed results label URL totals incomplete. Raw and
decoded limits describe different stages; neither is a total network/heap/CPU
budget. Redirect/private-host checks remain active. Only expected transport
failures become bounded notes; unexpected processing errors propagate after
response cleanup.
The explicit received-length check covers identity/unencoded, non-transfer-encoded
requests bodies too, including older optional dependency versions that do not
raise on a short stream. Decoded gzip/chunked sizes are not compared directly to
wire Content-Length; this is not full transport/encoding conformance validation.
`--max-sitemaps` bounds distinct file fetch attempts, including failures, recorded
as `sitemaps_attempted`; it is not a redirect-hop or whole-network request budget.
Remaining-file counts exclude already-visited and duplicate queued references.
Scan context, crawl and validator fallback discovery now share checked XML
extraction too: prefixes, gzip and XML character escaping work without treating
comments, HTML markers or bare loc tags as pages. Each discovery component has a
50-distinct-file attempt ceiling and the previous 5,000,000-byte response budget;
gzip decoded input retains the separate ceiling above. Crawl follows at most
five distinct syntax-usable child references per index and one index hop
(nested child indexes are noted, not expanded), retaining
anchor fallback and valid siblings within those limits. Already-visited entries
are skipped without retaining entire parsed-file buffers. These are component
budgets, not an aggregate audit/network/CPU/heap budget; validator traversal has
its separately selected `--max-sitemaps` budget.
Sitemap-file accounting drops literal `#fragment` values before deduplication,
child-slot selection and traversal/remaining counts, matching HTTP's fragment-free
request target. Aliases cannot repeatedly consume the same file budget or crowd
out later siblings. Query strings, encoded `%23`, path spelling and page-location
source values are not rewritten. This is not general URI canonicalization or
permission to bypass source/fetch validation.
HTTP `Content-Encoding: gzip`/`deflate` is checked separately from raw `.gz`
files: the fetch budget bounds both encoded wire bytes and decoded response
bytes. Short declared bodies, missing/corrupt compression trailers and decode
overflow contribute no XML prefix. Raw `.gz` files without HTTP encoding stay
raw for the sitemap decoder and its separate decoded-file budget. Raw fetches
advertise only supported HTTP encodings; unsolicited unsupported/stacked
encodings remain explicit fetch gaps rather than guessed complete bodies.
`sitemap_discovery` receipts record candidate scope, counts and active limits,
not whole-site URL totals. Unknown formats, incomplete fetches and limits are
explicit non-scoring notes/manual verification, not proof of missing/invalid
source. HTTP 404/410 on optional common paths remains distinct from unverified
fetches; unavailable explicitly declared roots/index children remain coverage
gaps, including when an earlier optional probe already checked that URL. If no
supported root was measured, relevant technical-score diffs and score-based
compare/brief verdicts remain unverified; focused non-technical scores and
missing legacy receipts are not guessed incomplete. Finding/scoring weights
are unchanged. The legacy pure marker/regex helpers remain compatibility hints,
not evidence used by these discovery paths.
The crawl graph's sitemap sample/count contains actual extracted candidates,
not an automatically added start URL or anchor-fallback URLs. Without verified
sitemap URL candidates the orphan check is skipped, not a sitemap-absence claim.
Unknown/legacy extraction receipts do not certify health. Planner coverage-gap
actions ask for manual verification, not rewriting an otherwise valid unsupported
format. Sampled URL success requires a successful 2xx response; gated/other
responses leave reachability unverified, and skipped sampling says so explicitly.
Positive health wording applies only to the checks performed, not unsampled URLs
or deployed indexing/search visibility.

In remediation plans, sitemap fetch failures, traversal caps, XML extraction
gaps and uncertain sampled responses become **manual verification**, not
instructions to create or rewrite a sitemap. Current `2.0` report counters must
be explicitly recorded and consistent for fetch/cap-specific context; missing,
malformed or future-schema evidence leaves notes unclassified. Notes are not
interpreted as commands or parsed for keywords. These actions have no guessed
source files and do not assume deployment is required. They ask for deployed
endpoint/status/limit checks, preserving private-host and budget boundaries.
They are excluded from shared source-edit groups, and Markdown labels their
owners deliberately unassigned for verification rather than missing.
Actual URL/lastmod problems and confirmed failing HTTP samples retain separate
source-repair advice. Gated/no-response/incomplete probes do not establish dead
URLs. Counter checks establish schema/count consistency, not authenticated
provenance or complete HTTP/XML conformance; planning remains read-only.

Crawl JSON records HTTP link-response `coverage` (successful 2xx, broken and
unverified checked targets, with no-response `request_failures` counted within
unverified) and `duplicate_coverage` (eligible SimHash fingerprints
within scanned pages). Known failed/partial pages do not enter duplicate
comparison. Zero checked links and fewer than two eligible fingerprints are
insufficient evidence, not green passes. Gated/non-success responses stay
unverified without being mislabeled dead links. Reports retain cap/omission
notes, scope clean observations to measured targets/pairs, and do not infer
coverage from legacy missing receipts. Combined audit headlines distinguish
checks not run from measured counts. These remain sampled measurements and a
near-duplicate heuristic, not exhaustive link or content health certification.
The legacy `links.broken` list retains unreachable status-0 entries for
compatibility; these are request failures, not observed broken HTTP responses.

### Track health over time (regression tracking, no database)

Narwhal stays stateless: instead of a database, save a scan as JSON and diff two
runs. Human-readable, git-friendly, and the agent can read the diff directly.

```bash
python skills/seo-scan/scripts/scan.py https://example.com --format json -o before.json
# ...after changes...
python skills/seo-scan/scripts/scan.py https://example.com --format json -o after.json
python skills/seo-scan/scripts/diff_scan.py before.json after.json
```

Diffs validate recorded auditor execution before calling findings resolved.
Use matching auditor selections that completed, and full HTML responses. Known
scope mismatches, incomplete execution, truncated responses or comparing a page
score with an audit overall score produce **Not comparable**, not a fabricated
improvement. `--fail-on-regression` exits **2** in those cases (ordinary measured
regressions exit **1**). Diagnostic diffs without the gate still exit 0.

Page scans also record `meta.scan_settings`: requested rendering, actual rendered
mode and whether image checks apply to the selected technical auditor. Known
differences block the comparison, so `--no-image-checks` cannot become a resolved
image fix and raw/rendered HTML cannot be treated as identical fix evidence.
An existing explicit boolean `rendered` field also records known actual mode.
`rule_config` is an opaque fingerprint of scoring weights, effective check
thresholds and normalized ignore categories/title patterns. A known fingerprint
change also blocks the comparison: suppressing findings or changing penalties
is not a page fix. Raw configuration values and source paths are not serialized.
Built-in rules are copied for each scan before page I/O; supplied threshold
overrides are copied on entry, and gathered overrides are copied when received.
Later caller mutations cannot change the current scan's checks or ignore policy.
This is ownership isolation, not an atomic transaction across concurrent writes:
keep inputs stable while the entry snapshot is being captured. Unsupported/custom
policies retain their behavior without a certified rule fingerprint.
Built-in rules are captured once for a crawl/audit too, so later page scans
cannot silently switch scoring or suppression when caller Config changes.
Gathered crawl threshold overrides are detached before discovery and workers;
the audit resolves its sitemap sample budget at entry. This does not freeze
remote site content or guarantee identical crawl samples between runs.
Audits retain these settings for crawled pages and check common exact URLs too;
different complete recorded crawl page samples block score/finding verdicts,
including changed URL multiplicities. Page order does not matter. Exact recorded
URL strings are compared without normalizing aliases or preview hosts; unknown
or malformed samples retain legacy comparisons and remain unverified.

JSON includes `comparison.status` (`comparable`, `incomparable`, `unknown`) and
reasons. Incomparable results have null `score_delta` and `regression`, empty
change lists, and `not_compared` finding counts. Legacy/malformed scope is
explicitly unverified: historical finding/score comparisons and gates remain
compatible with a visible warning, not proof of matching checks. Even matching
recorded auditor groups and known settings do not establish identical response
destinations, other configuration, rule versions or unrecorded site-wide crawl
samples; keep those controlled when using a diff to verify a fix.
Missing/malformed legacy settings are not guessed from findings or score changes;
the older scope-based diff behavior remains, with those settings unverified.

The diff shows the **score delta** and which findings are **new**, **resolved**,
**worsened**, or **improved** (dynamic titles like `Thin content (210 words)` are
matched across runs). Add `--fail-on-regression` as a **CI gate** — it exits
non-zero for a measured score drop, a new critical/high finding, an existing
finding escalating to critical/high severity, or known incomparable coverage.
Severe escalation fails even when other fixes offset its score cost; escalation
ending below high severity alone does not trigger the gate. Commit the
JSON snapshots alongside your repo to keep a lightweight history. Works on `audit`
JSON too.

Repeated findings use one representative per category/rule ID (or the existing
normalized-title fallback for legacy findings): the worst observed severity,
with equal-severity ties selected by sorted-key JSON lexical order. Reordering
repeated entries cannot invent a severity transition or hide a newly appearing
critical/high rule behind a later low entry. `finding_identity` records raw
entry, distinct-identity and repeated-entry counts; Markdown discloses repeats.
These are rule-level comparisons, not matches between individual nodes or
instances. Input report scores are retained without recalculation. Severity
transitions retain their rule IDs when available, and mixed/worsened headlines
remain visible even when the existing regression-gate criteria are not met.

Diffs require explicit finite numeric scores in the 0–100 range: `score` for a
scan, `overall_score` for an audit. A missing site score is not replaced by the
homepage score. Finding lists must be present, with object entries containing
a non-empty category, supported severity, string title and usable rule/title
identity. Invalid core evidence, ambiguous report kinds, malformed UTF-8/JSON
and decoder-limit failures exit **2** before comparison or output writes, even
without the regression flag. Errors identify the earlier/later field or decode
location without echoing report values. Python APIs and the MCP callable raise
`ValueError`.
Legacy missing rule IDs still use titles, and missing execution metadata stays
unknown; additive fields are preserved. This is a check of consumed evidence,
not full report-schema validation, score authentication or proof of matching
execution, URLs or source content.

Saving a diff with `-o` checks the opened output file against the OS identities
of both input snapshots captured while reading them. Direct, relative, symlink
and hard-link input aliases are refused with exit **2** before truncation,
regardless of the regression flag. Distinct regular output files retain normal
rendering, replacement and gate behavior; a symlink to a distinct output still
works. Write/encoding failures return a controlled error. This guards the input
files used for that invocation, not arbitrary snapshots or concurrent external
mutations. Separate output writes remain non-atomic; an interrupted write may
leave a partial diff file. Stdout and the read-only MCP callable are unchanged.

### Real Core Web Vitals (opt-in)

Everything above is local and honest about what it can measure — it will **never
fabricate** field metrics. When you want *real* Core Web Vitals (what actual Chrome
users experience), Narwhal can query Google's **Chrome UX Report (CrUX) API**. This
is the one feature that calls an external service, so it's **opt-in** and needs a
free API key.

> **CrUX vs. PageSpeed Insights.** Both surface Core Web Vitals, but they're
> different things. **PageSpeed Insights (PSI)** runs a Lighthouse *lab* test and
> historically also echoed CrUX *field* data — but as of 2026 Google is **removing
> CrUX field data from the PSI API**. So Narwhal talks to the **CrUX API directly**,
> which is the source of truth for real-user field data (LCP/INP/CLS at the 75th
> percentile). No Lighthouse lab score is fetched — our local `technical` auditor
> and the `narwhal-performance` agent already cover performance *hygiene*.

#### Get a free API key (one-time, ~2 minutes)

The CrUX API is **free** — no billing, no credit card. Quota is 150 queries/minute
per project (can't be paid to raise, but that's plenty for audits).

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and
   **create or select a project** (top bar).
2. **Enable the API:** go to
   [**Chrome UX Report API**](https://console.cloud.google.com/apis/library/chromeuxreport.googleapis.com)
   and click **Enable**.
3. **Create the key:** go to
   [**APIs & Services → Credentials**](https://console.cloud.google.com/apis/credentials)
   → **Create credentials** → **API key**. Copy the key.
   *(Optional but recommended: click the key → **Restrict key** → restrict it to the
   Chrome UX Report API.)*

Full details: [Google's CrUX API guide](https://developer.chrome.com/docs/crux/api).

#### Give Narwhal the key (three ways — you don't have to pass it every time)

Narwhal resolves the key in this order, so pick whichever fits — **you only set it
once**:

1. **`--crux-key` flag** — explicit, good for one-offs or CI secret injection:
   ```bash
   narwhal vitals https://example.com/page --crux-key YOUR_KEY
   ```
2. **`CRUX_API_KEY` environment variable** — best for a permanent/global setup
   (also inherited by Claude Code and CI). Add it to your shell profile:
   ```bash
   export CRUX_API_KEY=YOUR_KEY          # macOS/Linux (~/.bashrc, ~/.zshrc)
   $env:CRUX_API_KEY = "YOUR_KEY"        # Windows PowerShell ($PROFILE for persistence)
   ```
3. **A `.env` file** — the convenient project-local option. Copy
   [`.env.example`](.env.example) to `.env`, fill in the key, and Narwhal
   auto-loads it (from the working directory or any parent):
   ```bash
   cp .env.example .env      # then edit: CRUX_API_KEY=YOUR_KEY
   narwhal vitals https://example.com
   ```
   `.env` is **gitignored**, so the secret never gets committed. (Never put the key
   in `narwhal.toml` — that file *is* meant to be committed.)

```bash
narwhal vitals https://example.com --origin --form-factor phone
```

You get **LCP, INP, CLS** (the Core Web Vitals; INP replaced FID in 2024) at the
75th percentile, each rated good / needs-improvement / poor, plus a pass/fail
verdict (and FCP/TTFB as secondary). Flags: `--origin` aggregates across the whole
site, `--form-factor phone|desktop|tablet` narrows the device, `--format json`.

CrUX only has data for pages/origins with enough real traffic — low-traffic URLs
return "no data" (try `--origin` for the site-wide aggregate). Without a key,
`narwhal vitals` prints how to get one and exits; it never guesses field numbers.

#### No CrUX data? Use lab metrics (`--lab`)

CrUX is empty for pages below its traffic floor — most pages. For those, add
**`--lab`** to run a **PageSpeed Insights (Lighthouse)** test, which works for
**any URL** regardless of traffic:

```bash
narwhal vitals https://example.com/page --lab               # mobile (default)
narwhal vitals https://example.com/page --lab --strategy desktop
```

You get an overall **performance score** plus **LCP, TBT** (the lab proxy for INP),
**CLS**, FCP, Speed Index, and TTI. **Lab data is a synthetic single run — an
estimate for catching regressions, not real-user field data**, and Narwhal labels
it that way. The PSI key is *optional* (keyless works at a low, shared quota that's
often exhausted, so a key is recommended): set `PAGESPEED_API_KEY`, or **reuse your
CrUX key** by enabling *both* the Chrome UX Report API and the PageSpeed Insights
API on the same Google Cloud project.

**Which do I want?** CrUX (default) = *real users, popular pages*. PSI `--lab` =
*synthetic, any page*. Use CrUX when it has data; fall back to `--lab` when it
doesn't.

## Install

### Claude Code — plugin (recommended, one command)

Narwhal ships as a Claude Code plugin. Add the marketplace and install it:

```text
/plugin marketplace add aindong/narwhal
/plugin install narwhal@narwhal
```

That's it — the skill and its scripts load automatically. Then use the slash
command:

```text
/narwhal audit example.com      # full multi-agent audit (folds in CrUX vitals if a key is set)
/narwhal crawl example.com      # site-wide crawl (links + duplicates)
/narwhal sitemap example.com    # validate the XML sitemap(s)
/narwhal llms example.com       # generate a starter llms.txt
/narwhal vitals example.com     # real Core Web Vitals from CrUX (needs a key — see below)
/narwhal compare you.com rival.com   # side-by-side competitor gap analysis
/narwhal brief you.com/page rival.com/page   # data-driven content brief (GSC + gaps)
/narwhal plan before.json        # read-only finding-to-source remediation plan
```

`/narwhal <action> <site>` takes actions `scan`/`audit`, `fix`, `brief`,
`compare`, `plan`, `crawl`, `sitemap`, `llms`, `schema`, `gsc`, `vitals`, `diff`, and
`render`. You can also just ask Claude naturally:

> Run an SEO and GEO audit on https://example.com

**Using `vitals` from the plugin:** the slash command runs the same CrUX lookup, so
it needs the key too — set `CRUX_API_KEY` in your shell profile (Claude Code
inherits it) or drop a `.env` in your project (see *Real Core Web Vitals* above).
Then `/narwhal vitals example.com` just works, and `/narwhal audit` automatically
includes real field data when a key is present.

**`/narwhal audit` produces a shareable, branded report file.** It doesn't just
print in the chat — after the multi-agent synthesis it writes
`narwhal-audit-report.md` and renders a **self-contained, branded HTML report**
(`narwhal-audit-report.html`) — no extra tools needed, opens anywhere. Want a
**PDF**? Add `--format pdf` (needs a rendering engine — WeasyPrint or
Playwright/Chromium — else it stays HTML), or just open the HTML and *Print → Save
as PDF*. Under the hood that's the `render` action, which turns any Markdown into a
branded report:
```bash
narwhal render narwhal-audit-report.md -o report.html      # or --format pdf -o report.pdf
```

Named `-o` report/artifact outputs must be regular files across the CLI, including
comparison, brief, crawl, sitemap, llms.txt and opt-in data reports. Expected save
failures exit 2 without a success message, while successful saves retain each
command's analysis gate code. Their final writes remain non-atomic.

Scan, audit and render file outputs must be regular files. Expected delivery
failures exit 2 without a success message. PDF engines stage output first so an
incomplete engine write cannot replace the destination. UTF-8 encoding is checked
before truncation. Final writes remain non-atomic and can fail partway through;
use stdout without `-o` for shell pipelines.

Render output must be a regular file distinct from the file-backed Markdown
source, including link aliases. PDF output is staged before the identity check;
the actual HTML fallback destination is checked too. Separate final writes remain
non-atomic; shell stdout redirection can still truncate its input before Narwhal runs.

Inline code stays escaped and literal: Markdown markers, links and HTML inside
matching backtick runs are displayed as text, not interpreted. Equal-length
runs support literal shorter backticks inside a span; unmatched runs stay text.
Spans are single-line and retain their inner spaces/tabs. This is a limited
report renderer, not a full CommonMark implementation.

Markdown HTTP(S) links format their labels without interpreting destination
characters as Markdown. Underscores and asterisks in a path/query/fragment stay
part of the URL; code examples and unsupported URL schemes do not become links.

In pipe tables, use `\|` for a literal pipe in a header or cell (also inside
inline code). Empty edge cells are retained. An odd backslash run escapes the
pipe and loses only its final escaping backslash; other backslashes stay data.
Unescaped pipes remain column separators. This does not add general Markdown
backslash escapes or alter fenced/non-table text.

Generated crawl **Weakest pages** and broken-link tables encode URL/error text
as literal cells, so pipes do not create columns and Markdown-like URLs do not
create links or emphasis. A versioned `<!-- narwhal: escaped-table-cells-v1 -->`
comment immediately before these tables opts the branded renderer into ASCII
punctuation unescaping for that table only. Other Markdown readers understand
the standard backslash escapes directly. Legacy tables, ordinary text and code
remain unchanged; CR/LF line breaks in cell data become spaces without collapsing
other internal spaces or tabs. Literal tildes are escaped for GFM readers. JSON retains
the original evidence. URL autolink prefixes are escaped too, preventing GFM
URL links with escape backslashes in their targets. Third-party postprocessing,
such as GitHub's email autolinking, remains outside the encoder's control.
Other subreport sections are outside this table-only fix.

Branded Markdown tables have padded cells, aligned column headers and row guides.
Wide tables scroll within their own keyboard-focusable region on screen instead
of squeezing columns or widening the page. Print/PDF input uses compact wrapping
columns rather than a clipped scroll area. Native scan score breakdowns have a
separate keyboard-focusable horizontal scroll region, readable area labels and
accessible severity headers; narrow phones no longer widen the page or spill
the table outside its card. Print/PDF removes the scroll clipping and focus
outline. This is presentation only: scores, counts, JSON and Markdown stay the
same. Very large tables may still need manual print review.

Table separator markers set column alignment on both headers and body cells:
`:--` (or unmarked `--`) is left, `:--:` is centered, and `--:` is right.
This also keeps comparison score columns right-aligned on screen and in print.

The limited Markdown renderer preserves root fenced code (three or more matching
backticks or tildes, up to three leading spaces) as escaped literal text. Code
comments cannot become report titles, and Markdown inside a fence is not styled
as headings/lists/links. Code keeps whitespace after opening-indent removal and
CR/LF normalization; unclosed blocks extend to EOF. Screen blocks scroll for
long lines, while print/PDF input wraps them. Language labels are optional and
sanitized; there is no syntax-highlighting dependency or full CommonMark/nested-
container support.

To update later, run `/plugin marketplace update narwhal`; to remove, `/plugin
uninstall narwhal@narwhal`. (The first `narwhal` is the marketplace, the second is
the plugin.)

### Run instantly with `uvx` (no install, no PyPI)

If you have [`uv`](https://docs.astral.sh/uv/), run Narwhal straight from GitHub in
a throwaway environment — always the latest, nothing left behind:

```bash
uvx --from git+https://github.com/aindong/narwhal narwhal scan https://example.com
uvx --from git+https://github.com/aindong/narwhal narwhal crawl https://example.com --max-pages 25
uvx --from git+https://github.com/aindong/narwhal narwhal schema Article --field headline="…"
uvx --from git+https://github.com/aindong/narwhal narwhal sitemap https://example.com
uvx --from git+https://github.com/aindong/narwhal narwhal llms https://example.com
uvx --from git+https://github.com/aindong/narwhal narwhal plan before.json --repo .
```

The unified `narwhal` command includes `audit`, `scan`, `plan`, `crawl`, `schema`,
`sitemap`, `llms`, and `diff` (run any with `-h`). Prefer a stable command? Alias it:

```bash
alias narwhal='uvx --from git+https://github.com/aindong/narwhal narwhal'
narwhal scan https://example.com --fail-under 80
```

### Claude Code — manual (no plugin system)

Copy or symlink `skills/seo-scan/` into `~/.claude/skills/` (user-wide) or
`.claude/skills/` (per project), or run the installer:

```bash
bash install.sh        # macOS / Linux
```
```powershell
./install.ps1          # Windows
```

### Codex / Cursor / OpenCode / other agents

Point the agent at this repo — the root [`AGENTS.md`](AGENTS.md) documents the same
tools in the format those agents read. Then ask for an audit.

### MCP server (any MCP client)

Narwhal can also run as a [Model Context Protocol](https://modelcontextprotocol.io)
server, exposing every auditor as a native tool (`scan_page`, `crawl_site`,
`audit_site`, `validate_sitemap`, `generate_llms`, `generate_schema`,
`diff_reports`, `plan_remediation`) over stdio. The planner accepts a parsed report
object and only relative repository paths beneath the server working directory;
it is bounded and read-only. The server is a typed adapter over the same scripts — no
new analysis, so results match the CLI exactly.
Product/store evidence and `schema.ecommerce.*` findings flow through the existing
`scan_page`, `crawl_site`, and `audit_site` results; no separate network-capable
commerce tool or external merchant account is required.

```bash
pip install "narwhal-seo[mcp]"   # or: pip install "mcp>=1.12"
narwhal mcp                       # runs the stdio server
```

Register it with a client — e.g. Claude Desktop's `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "narwhal": { "command": "narwhal", "args": ["mcp"] }
  }
}
```

MCP is optional; the core toolkit stays zero-dependency.
Narwhal supports the MCP Python SDK 1.x and 2.x high-level server APIs; CI tests
both current major lines.

## Design principles

- **Local-first, with explicit network use.** Default scans fetch the requested
  site and related audit resources and write reports locally; they are not
  offline scans. External data integrations (such as GSC or PageSpeed/CrUX) are
  opt-in, and scans send no telemetry.
- **Graceful degradation.** Works with only the Python standard library; uses
  `requests`, `beautifulsoup4`/`lxml`, `trafilatura`, and `playwright`
  automatically when installed.
- **SSRF-safe.** URLs that resolve to private, loopback, or link-local addresses
  are blocked unless you explicitly pass `--allow-private`.
- **Fix-first output.** Reports lead with the highest-severity, highest-leverage
  changes — not a data dump.

<a id="tuned-against-the-real-web-and-we-publish-the-evidence"></a>

## Real-site tuning and its limits

Narwhal's deterministic checks are revised and specialist prompts refined using
maintainer investigations of public pages. Historical before/after report
snapshots are committed in [`docs/tuning/`](docs/tuning/README.md); new sensitive
source captures stay private. This is rule/prompt development, not model
training or an independently validated benchmark.

**A correction can raise or lower a tool score without improving or worsening
the page.** We fix extraction/detection errors and revise priority or advice
when their scope was overstated, documenting the reason and testing the affected
behavior. We do not target higher scores or assume a familiar site's findings
must be wrong. Historical work included fixing lost nested-link heading text,
counting anchor text as content, and making checks page-type-aware. The following
are historical **tool-score changes**, not demonstrated website improvements:

| Site (page type) | Before | After |
|:--|--:|--:|
| jvns.ca (personal blog) | 62 | **79** |
| news.ycombinator.com (link-hub) | 52 | **66** |
| docs.python.org (docs index) | 75 | **86** |
| theverge.com (news publisher) | 71 | **80** |

Historical specialist runs informed *Judgment rules* such as classifying the
page type, sampling an article and respecting deliberate AI-crawler opt-outs.
Those qualitative maintainer observations are not independent expert grading
or proof that every agent follows the prompts. See the
[methodology and historical reports](docs/tuning/README.md).

The offline maintainer [review-pack workflow](docs/tuning/REVIEW.md) separates
observation, priority and advice review against local snapshot versions. Its
counts describe annotation coverage, **not scanner accuracy**: historical
reports without frozen page evidence stay explicitly report-only, and accuracy
and recall remain unmeasured. Independent held-out validation is still needed.

For new cases, the opt-in maintainer [capture workflow](docs/tuning/REVIEW.md#capture-new-scan-inputs-explicit-network-opt-in)
preserves the same scan's decoded source/DOM, available response metadata and site
context in a fresh local bundle. It does not re-fetch evidence, overwrite old
captures, publish sensitive content or adjudicate findings. Missing network
evidence and partial/error scans remain explicit; captured files are not proof
of accuracy. Ordinary scans retain no additional raw-input handle.

## Reference guides

Deep-dive reasoning behind each check lives in
[`skills/seo-scan/references/`](skills/seo-scan/references/):
`technical-seo.md`, `content-eeat.md`, `schema.md`, `geo-llmo.md`.

## Configuration (optional)

Narwhal needs no config, but you can drop a **`narwhal.toml`** at your project root
to tune scoring weights, check thresholds, CLI defaults, and which findings to
ignore. It's auto-discovered; precedence is **CLI flag > `narwhal.toml` > default**.

```toml
[defaults]
fail_under = 85            # CI gate: fail below 85

[thresholds]
thin_content = 250         # our pages are intentionally concise

[ignore]
categories = ["geo"]       # hide all GEO findings
titles     = ["Open Graph"]# hide the social-preview nag
```

Full reference: **[docs/CONFIG.md](docs/CONFIG.md)** · commented template:
**[narwhal.example.toml](narwhal.example.toml)**. Use `--config PATH` or
`--no-config` to override discovery.

## Roadmap & docs

- **[docs/STATUS.md](docs/STATUS.md)** — current state & handoff snapshot.
- **[docs/ROADMAP.md](docs/ROADMAP.md)** — where Narwhal is headed (priorities,
  milestones), linked to tracking issues.
- **[CHANGELOG.md](CHANGELOG.md)** — release history.
- **[docs/](docs/README.md)** — documentation index.
- **[Issues](https://github.com/aindong/narwhal/issues)** — detailed tasks; see also
  [CONTRIBUTING.md](CONTRIBUTING.md).

## Requirements

Python 3.8+. Optional extras in
[`skills/seo-scan/requirements.txt`](skills/seo-scan/requirements.txt).

## License

MIT — see [LICENSE](LICENSE).
