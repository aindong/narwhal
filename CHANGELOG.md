# Changelog

All notable changes to Narwhal are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

- Compare and content briefs retain each page's actual rendering flag in JSON
  and label served HTML versus JavaScript-rendered DOM in their reports. Missing
  legacy flags remain unknown; generic grounding text no longer calls rendered
  snapshots served HTML. Scores and gap/brief calculations are unchanged.

### Improved
- Invalid link/sitemap request caps are rejected before discovery or composite
  audit subscans. Negative link caps can no longer become Python slices that
  check almost all targets. CLI flags and consumed config defaults fail with
  exit 2 without replacing reports. Integer zero retains the corresponding
  optional-check skip; discovery has separate resource bounds.
- Remaining crawl/comparison/brief/sitemap/llms.txt and opt-in data report saves
  use the shared regular-file/UTF-8 writer. Expected save errors exit 2 without
  success messages or tracebacks; encoding preflight retains prior output.
  Existing report text, success messages and analysis gate codes remain.
  Final writes remain non-atomic; use stdout rather than named pipes/devices.
- Scan/audit report delivery now uses regular-file and UTF-8 preflight checks
  and stages PDF engine output before final writes, matching Markdown rendering.
  Expected delivery failures return exit 2 without a success message or
  traceback; incomplete engine output cannot replace an existing PDF. Fallback
  HTML uses the same writer. Separate final writes remain non-atomic.
- Crawl and audit reject nonpositive/noninteger page and worker budgets before
  URL resolution or any subscan. Invalid CLI flags/config defaults exit 2
  without replacing reports, instead of scanning despite a zero-page limit or
  silently selecting sequential mode for zero workers. Valid CLI/API limits
  remain uncapped; MCP retains its documented positive clamps.
- Crawl delay now spaces parallel page-scan starts instead of being ignored
  when concurrency exceeds one. Workers can still overlap, and late wakeups do
  not create catch-up bursts. Sequential pauses remain unchanged. Invalid
  delays fail before URL resolution/discovery; CLI errors are controlled.
  Discovery, site-resource and optional probe requests are outside this pacing.
- Audit diffs with different complete recorded crawl page samples now withhold
  score/finding verdicts and fail strict gates with exit 2. Exact URL
  multiplicities preserve average-score weighting; page ordering is irrelevant.
  Missing/malformed legacy samples remain unverified rather than guessed to
  match. This prevents a changed page mix from masquerading as a site fix.
- Invalid scan auditor selections now return CLI usage failure without a
  traceback or output artifact. API/CLI/MCP reject unknown names and empty
  comma-separated entries before fetching; MCP no longer silently drops them.
  Empty/default selection still runs all auditors. Diagnostics are bounded,
  and unrelated auditor exceptions remain visible for debugging.
- Markdown report rendering preserves its file-backed source when HTML, PDF or
  fallback HTML destinations alias the read input, including links and renamed
  sources. PDF engines stage output before the guarded write; invalid UTF-8
  input and output I/O failures return controlled errors. Distinct final writes
  remain non-atomic and cannot protect arbitrary files or concurrent writers.
- The default diff regression policy now catches existing findings escalating
  to critical/high severity, even when the total score stays flat or improves.
  CLI strict gates fail for these escalations; MCP returns the same verdict.
  New-finding identities and known-incomparable verdicts retain their semantics.
- Saved remediation plans now refuse aliases of their file-backed input report
  before truncation, retaining the scan/audit baseline needed for verification.
  Plan and diff saves share the existing identity-guarded writer, regular-output
  policy, cleanup and controlled write/encoding failures. Separate artifact
  writes remain non-atomic; ordinary plan contents and stdout/MCP planning stay
  unchanged. CLI home-relative report paths expand consistently in verification
  provenance instead of pointing at a literal `~` directory.
- Saved diffs check the opened output against the actual read-snapshot file
  identities before truncation, refusing direct/symlink/hard-link input aliases.
  Failed handles close, non-regular outputs are withheld without FIFO blocking,
  and UTF-8/write failures return controlled errors. Distinct regular output
  rendering and CI gate behavior remain; separate output writes are non-atomic.
- Diff inputs require explicit finite 0–100 scan/audit scores and supported
  finding structure/identity before comparison. Missing scores no longer become
  zero or borrowed homepage metrics; invalid fields and decoder/UTF-8 failures
  produce bounded, labeled errors without output writes or passing CI verdicts.
  Valid legacy identities and unrecorded execution metadata retain their paths.
- Scan/audit diffs compare repeated rule identities by worst observed severity
  with stable representatives and ordering. Later low entries cannot hide a new
  high rule or create order-only severity changes. Entry-count receipts disclose
  rule-level scope without instance matching or score recalculation. Severity
  transitions retain rule IDs; mixed/worsened changes get accurate headlines.
- Remediation source-edit groups exclude manual/external and ownerless actions.
  Their evidence and manual tasks remain, without instructions to implement
  them as shared template fixes or borrow another action's source owner.
- Remediation planning survives malformed or unsupported package manifests and
  dependency sections, disclosing unavailable evidence without echoing file
  contents. Valid sibling declarations and independent framework config signals
  remain; null/non-string dependency values no longer claim a framework.
- Remediation source suggestions omit traversal, ambiguous drive/stream paths
  and symlink components, including proposed files not yet present. Warnings
  disclose omissions; hidden route names retain their spelling. Ownerless
  structural actions require manual source verification instead of automation.
- Complete-byte resource downloads reject HTTP 206 and any Content-Range
  evidence before body reads or decoding in both HTTP backends. Ranged XML
  cannot become a verified sitemap root; ordinary complete/gzip and HTTP-error
  controls remain. Root llms.txt uses the same header-presence rule, including
  empty markers, retaining unverified state without publication/absence claims.
- Ranged primary HTML (HTTP 206 or any Content-Range evidence) no longer runs
  page auditors or produces missing-metadata/content verdicts from fragments.
  A bounded positive receipt explains unavailable full-page health, retained
  fail-safe scores and manual-only verification. Partial served baselines do
  not support rendering conclusions. Page/site notes and current/known-legacy
  diff/compare/brief gates preserve uncertainty; complete pages and intentional
  byte-limit scans keep their existing paths. No new requests or SEO gains.
- Terminal HTTP 3xx responses (including 304 without a cached representation)
  no longer count as successful page/resource bodies. Unresolved redirect HTML
  cannot receive measured page-health scores or become root text resources;
  normal redirects ending in a successful response still work. Successful 2xx
  remains transport status, not complete-body or SEO certification.
- Crawled hreflang responses now share bounded acquisition checks with optional
  probes: redirected identities, empty bytes, unknown media types and partial or
  unavailable snapshots cannot establish missing return tags or seed extra
  probes. Explicit source receipts preserve final-page scan facts and qualify
  sampled relationship output, without changing page scoring or fetch budgets.
- HTML hreflang extraction survives malformed URLs and retains supported source
  annotations without inventing absolute URLs from relative references. Explicit
  source counts, omission reasons and scoped relationship/probe receipts replace
  false clean-cluster verdicts under missing/partial coverage. Complete matching-
  identity HTML is required for production probes; already sampled pages and
  zero budgets do not trigger extra probes. Current/legacy and known-gap gates
  qualify technical score comparisons, briefs and manual-only remediation.
  Existing request caps/guards, weights and supported-presence rule ID remain;
  a new low source review can change scores, not measured site/SEO gains.
  Optional x-default advice is conditional; review title-based ignore filters.
  Dogfooding also fixed a read-only planner crash on empty static-directory hints;
  fallback file candidates remain explicitly marked as existing or hypothetical.
- Anchor collection, source checks and fallback discovery use the first declared
  non-template base href, retaining the document's internal-host boundary.
  Unsupported/malformed/CSP-restricted bases withhold dependent targets with
  explicit unscored coverage notes, not fabricated HTTP failures or source fixes.
  Current/legacy page/crawl policy and known-gap gates qualify diff/compare/brief
  claims. Base parsing ignores raw-text/RCDATA lookalikes; caps, fetch guards,
  required dependencies and scoring rules remain unchanged. Counts/scores may
  reflect corrected targets, not measured site gains or full browser conformance.
  Shared malformed-URL extraction warnings omit raw values/credentials while
  retaining bounded local-reference deduplication and warning caps.
- Relative anchor-path merging preserves repeated separators and semicolon path
  data instead of silently merging distinct link/crawl targets. Shared literal
  dot-segment handling keeps canonical comparison unchanged. Crawl policy receipts
  qualify audit diffs across this selection correction; existing fetch guards,
  caps and page scoring rules remain. This is not full browser URL conformance.
- Zero-edge crawl reports retain known unreachable/zero-inbound URLs, orphan
  candidates and sample limits rather than returning early. A recorded BFS
  scope separates measured depth from an absent start or unrecorded legacy
  coverage; low depth is not a health pass. Existing graph facts, display caps,
  crawl/fetch budgets and scoring remain; omitted list items are explicit.
- Crawl discovery, graph and hreflang URL identity preserve non-root slashes,
  semicolon path data and query literals instead of hiding distinct addresses.
  Fragment aliases still group; orphan candidates deduplicate by the same key.
  Graph policy receipts qualify legacy/current audit diffs and sampled counts;
  page/probe caps, fetch guards and per-page scoring rules stay unchanged.
- Page and near-duplicate canonical checks share HTTP component comparison,
  preserving scheme/path/query distinctions while handling standard URL
  normalizations, relative bases and explicit empty delimiters locally.
  Malformed candidates retain evidence and manual uncertainty across reports,
  plans, comparisons and diff gates; no target fetch or selection proof.
  Stable rule/cluster fields remain; corrected scores are not measured page gains.
- Configured filler-list and vocabulary-ratio findings expose literal ASCII
  numerator/denominator counts and extraction basis as low contextual reviews,
  not padding or thin/spun-content verdicts. Matching/cutoffs/IDs remain; the
  rate flag's medium-to-low correction can change scores, not measured SEO.
  Current/legacy plans preserve useful phrasing and consistent terminology.
- Native page/audit and Markdown-derived reports size header/footer logos with
  explicit CSS (46px/16px) and align the footer mark inline with its credit.
  WeasyPrint no longer falls back to the embedded image's 128px intrinsic size.
  Inline image bytes, report data, engine options and fetching stay unchanged;
  both PDF engines have geometry regressions in optional-engine CI.
- Page frequency/title-H1 checks expose bounded lexical receipts with exact
  overlap, filter/cutoff/tie basis and clipped/omitted witnesses rather than
  claiming dominant topics or semantic relevance. Existing counts, selection,
  priorities and score contributions remain. Current/legacy plans preserve
  accurate wording and avoid keyword stuffing or forced overlap; original plan
  labels stay in JSON. Missing legacy scope and ranking/citation effects remain
  unverified; review title-based filters for the updated observation labels.
- Long literal terms in Markdown-derived report lists wrap on narrow screens
  without changing source text or report data.
- Native page/site-audit HTML groups supplemental text-length/readability and
  attribution/date evidence behind keyboard-operable disclosure. Counts,
  unassessed scope and candidate uncertainty remain visible; priorities, quick
  wins and resource warnings stay expanded. Print/PDF includes every detail once
  whether open or closed, without JavaScript. JSON/Markdown, findings, scores and
  fetch behavior are unchanged; screen/print copies are presentation, not new facts.
- Readability checks expose historical ASCII-token/punctuation-fragment/vowel-group
  inputs and Flesch/FK estimates rather than comprehension, school-grade or AI-
  citability verdicts. Unsupported language/text scope stays unassessed; below-
  range reviews and current/legacy plans preserve useful concise/specialist text.
  Known coverage changes guard page/audit/crawl diffs. Formula results/IDs remain;
  priority/score corrections are not measured SEO gains or new word-count quotas.
- Page scans, comparisons and briefs share bounded date-related candidates and
  inspectable scope, not freshness/publication certificates. Modified metadata
  counts consistently; blanks and bare years alone do not. Article reviews and
  current/legacy plans keep dates conditional on real purpose/evidence; compared
  pages no longer prescribe date gaps or cosmetic updates. Legacy IDs remain,
  `date_signal` semantics are corrected, and old booleans do not backfill scope.
  Score changes are calibration corrections, not measured SEO improvements.
- Offline maintainer review packs can record one explicit adjudicator decision
  without hand-editing packet structure. Source bindings and full packets are
  validated before/after; existing decisions need explicit replacement into a
  fresh file, other reviews are preserved, and outputs request owner-only access.
  Verdicts/identity/time/witnesses are never inferred; accuracy/recall remain
  unmeasured. This is not a runtime scanner command or automatic adjudication.
- Served/rendered text comparisons now record selected-text equality, extraction
  bases and signed whitespace-token deltas instead of certifying server rendering
  from equal counts. Legacy numeric aliases remain, but net increases and metadata/
  block-count differences are low manual reviews, not JS-only shares, authenticated
  injection or AI-access verdicts. Plans verify before assigning SSR/markup edits.
  Priority/score corrections are not measured SEO gains; fetch/render/body guards
  and partial-pair diff gates remain intact. Empty pairs have a distinct manual
  verification rule, not a passing server-rendering ID. Review title/severity-based filters.
- JSON-LD errors distinguish decoder-reported syntax defects from tool decoding/
  node-processing failures. Actual syntax errors retain their high rule/repair
  path; recursion/numeric/Unicode handling gaps are low manual verification notes,
  not source-invalidity or engine-rejection verdicts. Error-stage counts are
  recorded without raw markup, original error tuple compatibility remains, and
  parser/body/global limits are unchanged. The auxiliary Product heuristic no
  longer crashes on decoder ValueError guards. The documented legacy absence ID
  also honors extraction uncertainty and conditional review.
- Long source URLs in native report findings and quick-win advice wrap within
  narrow screens instead of overflowing the page; text and JSON stay intact.
- Page schema absence advice (including Product) now requires no known extraction error/limit; observed
  syntax/property checks remain active. Clean-scan suggestions are conditional,
  preserve valid supported formats and no longer promise rich results/AI benefits.
  Plans treat extraction verification as manual-only without source edits or
  generation, including ignored/legacy/crawl evidence, while keeping actual
  observed repairs reviewable. Limits, rule IDs and healthy absence severities stay
  unchanged; removed false penalties are not measured SEO fixes.
- Brief subtopic suggestions are labelled compared-heading review candidates,
  not verified missing content. Typed term-match receipts expose exact counts and
  the existing lexical cutoff; synonym misses, unrelated word matches and topic/
  legacy limitations are explicit. Candidate selection/order, facts and scores
  remain unchanged; no semantic coverage, query demand or ranking claim is added.
- Known structured-data extraction errors/limits no longer become schema-absence
  gaps or exclusivity leads in comparisons. Typed coverage receipts keep observed
  types and scores while qualifying schema/overall comparisons; semantic brief
  candidates require reviewing unverified existing markup. Page/audit diff gates
  with known extraction uncertainty return incomparable/exit 2, including crawl
  contributions. Coverage metadata adds no score penalties or larger extractor
  budgets; missing legacy coverage is not certified or backfilled.
- Comparison and brief reports carry the page auditor's dated Google rich-result
  retirement context, including source links and scope for observed/suggested
  schema types. Semantic candidates/generation remain available; retired Google
  appearances are not schema.org invalidity or ranking penalties, and unlisted
  types are not certified eligible. Missing legacy provenance stays unverified.
  Page findings/scores/status dates and type/candidate sets remain unchanged;
  no runtime policy fetch or new required dependencies.
- Compare/brief question-heading heuristics use exact recorded counts rather
  than the preserved two-decimal `question_ratio`. An 8/41 fraction no longer
  becomes 20%; no eligible headings or legacy missing counts stay unassessed.
  Reports show literal fractions and optional contextual advice, not forced
  question rewrites or engine-matching claims. Brief candidates distinguish
  compared headings from supplied GSC queries via `source_kind`. Pattern counts,
  page scores and deduplication remain unchanged; this is not query/SEO validation.
- Comparison/brief statistic/citation counts are explicit lexical observations,
  not verified evidence density. Preserve `stats_cites` and add split-count/basis
  receipts with source validity unchecked. Remove evidence-density gaps and
  automatic brief `evidence_target`/`your_evidence` quotas, including zero in topic
  mode. Legacy bases/targets stay unverified. Both cue and length receipts require
  bounded nonblank extraction labels and boolean clipping flags before their
  basis is shown as recorded. No regex, page score or source
  verification change; real claims/sources still need contextual review.
- Comparisons and briefs keep literal whitespace-token/code-point receipts, not
  content-depth gaps/leads or automatically inferred word targets. Historical
  `words` counts stay unchanged with explicit units; briefs stop generating
  `structure.target_words`/`your_words`. Missing legacy bases stay unverified and
  old length verdicts are not re-rendered as recommendations. Explicit editorial
  goals remain separate; other heuristics and page scores are unchanged.
- The page content auditor labels its historical ASCII-pattern count accurately
  instead of certifying thinness/depth. Non-English declarations or non-ASCII
  letters/marks leave length-threshold review uninterpreted, with typed counts
  and explicit coverage notes. Applicable below-bound advisories are low priority;
  current/legacy plans do not prescribe padding. Stable IDs/default bounds remain,
  but titles and corrected scores can change without page improvements. This is
  not multilingual word segmentation or validation of other length heuristics.
  Known changes in length-threshold coverage also prevent false page/audit diff
  improvement/resolution claims; matching uninterpreted coverage remains usable.
- Low-priority page findings retain bounded, whitespace-normalized previews of
  their reported observation/evidence in Markdown and native HTML/PDF input.
  Markup stays literal, clipped fields are labelled and full values remain in
  unchanged JSON. Previews help inspect findings; they do not independently
  verify them. Scores, severity, IDs and recommendations are unchanged.
  Long URLs in Markdown-rendered report H1s also wrap within narrow screens.
- User-facing and tuning documentation distinguish observed findings, priority
  revisions, scanner-score changes and actual website outcomes. Historical score
  tables are retained without treating familiar sites, passing tests or agent
  agreement as ground truth. Rule/prompt refinement is not described as model
  training or independent validation. No scanner behavior or scores change.
- A prospective 50-URL acquisition plan records intended page-role/language
  diversity, operational site-family splits, reserved-output rules and bounded
  conservative collection policy before scans. Local evidence is git-ignored;
  failures are retained without replacement. The initial 46 pending bundles and
  four preflight skips are acquisition coverage only, not independent accuracy,
  healthy-page or ranking/citation evidence. Historical reports are untouched.
- An opt-in maintainer capture command freezes one scan's decoded response/DOM,
  paired served input when available, response metadata and site context into a
  fresh local review bundle. Existing files are never overwritten; manifests are
  written last and byte-limit failures do not silently clip evidence. Pending
  review compatibility, missing-network-evidence limits and sensitive-content
  warnings are explicit. Ordinary scans retain nothing extra; findings, scoring
  and report JSON are unchanged. Captures are not independent accuracy validation.
- Native page-report score tables scroll within a labelled keyboard-focusable
  region on narrow screens, with readable area labels and accessible severity
  headers. This prevents the observed 320/360px page overflow and 390px card
  spill. Print/PDF removes scroll clipping and focus outlines; scores, counts,
  JSON and Markdown are unchanged. A dedicated browser regression covers
  320–1100px layouts, keyboard access, multi-digit counts and print input.
- Content scans and comparisons share bounded attribution-cue observations:
  nonempty author metadata, declared author links and short leading byline-like
  blocks, independent of main-content extraction. Bare prose words/blank metadata
  no longer pass. JSON receipts and literal page-report witnesses state the
  unverified identity/visibility/expertise scope. Missing article cues prompt low
  contextual review, not an anonymity verdict or blanket author-addition advice. Stable rule IDs
  and comparison `author_signal` remain; renamed title filters need review.
  Priority/detection corrections can change tool scores without page changes;
  current/legacy remediation plans keep edits conditional and review-required.
- Native page-report HTML/PDF headlines describe medium/low findings or the
  absence of flags instead of promoting a numeric band to an "Excellent"
  quality verdict. Critical/high and unmeasured precedence stay intact; the
  secondary band explicitly refers to reported findings, not page quality.
  Scores, severity, JSON, Markdown and other report types are unchanged.
- GEO question-heading, sentence-group size, statistic/citation and introductory
  term checks report literal cue counts and limitations, not semantic judgments
  or measured citation outcomes. Their editorial advisories are low priority,
  including on articles; new count receipts and compact-report caveats preserve
  uncertainty. Programmatic numeric bounds use JSON-safe receipts without
  rounding their comparisons. Plans keep edits conditional. Algorithms, thresholds and rule IDs
  remain; priority corrections can raise scores without page changes. Review
  title-based ignore filters for the new labels.
- Common-phrase matches are contextual, low-priority editorial review prompts,
  not AI-authorship or helpful-content/ranking verdicts. Examples and limits
  remain visible in compact reports; a low-match pass no longer certifies clean,
  specific writing. Matching logic, helper keys and stable rule IDs remain;
  four-plus-distinct-phrase priority changes from medium to low, so scores may rise without
  any page change. Plans keep edits conditional. Update title-based ignore filters.
- An offline maintainer review-pack utility inventories reported actionable
  findings with source hashes and separate observation/priority/advice labels.
  Stale snapshots, dropped/edited claims and confident labels without attached
  evidence are rejected. The 15-case historical manifest remains explicitly
  report-only and pending; review coverage never becomes an accuracy/recall claim.
- Stdlib terminal HTTP-error responses retain the actual guarded destination
  and observed redirect chain instead of attributing the error to the starting
  URL. Failed-page reports and root-resource receipts now identify that response
  correctly; status/body limits, stream closure and redirect/private-host guards
  are unchanged. Origin Content-Location headers do not set fetch identity.
- RDFa module initialization happens when HTML helpers load, before parallel
  crawl workers begin. This prevents cold-start partially-initialized-module
  failures observed on bare Python 3.9 while keeping per-document extraction
  lazy and cached, without optional parser imports or scoring changes.
- Robots wildcard matching finds ordered literal pieces instead of enumerating
  regex wildcard partitions. Short repeated-star rules no longer stall candidate
  filtering; prefix/end-anchor behavior, encoded literals and rule precedence
  are preserved. This is not a whole-crawl CPU or request-budget guarantee.
- An optional initial UTF-8 BOM no longer hides the first robots.txt user-agent
  group or Sitemap declaration. Crawl leaf filtering, GEO root-policy checks
  and sitemap discovery now read the same directives as their unmarked forms;
  literal markers inside paths and the explicit crawl-base override are unchanged.
- Root llms.txt observations retain HTTP/type/completeness evidence rather than
  treating every nonempty response as publication or every failure as absence.
  HTML/soft-error/gated/empty/partial/truncated candidates stay unverified and
  non-scoring; complete observed 404/410 retains the optional low advisory. Root-only
  wording, legacy-flag labels, crawl receipts, score-comparison guards and
  manual-only verification plans preserve the limits of this proposal check.
- Site-graph rankings break equal inbound-link and click-depth ranks by URL
  before display caps. Identical sampled graphs no longer choose different
  tied top-five JSON / top-three Markdown entries across Python process seeds.
  Counts, depths, scoring, URL identities and orphan coverage are unchanged.
- Crawl weakest-page and broken-link tables retain literal URL/error text:
  pipes stay in one cell and Markdown-like data cannot create table links or
  emphasis/strikethrough. CR/LF breaks become spaces without collapsing other
  internal spaces or tabs; GFM URL autolink prefixes are escaped as data.
  Generated tables use a versioned, table-local punctuation-escape
  marker; legacy Markdown, ordinary text and code keep their prior behavior.
  Original JSON, scores and crawl calculations are unchanged. Chromium CI
  verifies desktop/mobile/print table content and literal-output safety.
- Crawl summaries preserve each successful sampled page's HTTP/named-meta
  indexing receipts, with bounded non-scoring observations in crawl Markdown
  and comprehensive audit reports. Leaf-page policy evidence is no longer lost
  behind score-only summaries. JSON retains all collected receipts; display
  omissions, partial snapshots and sample-only scope are explicit. Scores and
  recurring-issue counts are unchanged; missing/failed-page evidence is not inferred.
- Documented `googlebot` and `googlebot-news` HTML meta restrictions now appear
  as non-scoring report observations and additive `meta.crawler_meta_robots`
  evidence. Active repeated tags accumulate exact noindex/nofollow/none rules;
  template content, directive parameters and unsupported names cannot create
  generic blocking findings. Scores/IDs are unchanged; this is not effective
  cross-source policy, preview/date handling or proof of indexing.
- Final HTML-response `X-Robots-Tag` restrictions are audited with separate
  header findings and manual hosting remediation. Repeated raw fields retain
  scope boundaries; named-crawler policies remain non-scoring notes with
  additive `meta.http_robots` provenance. Browser/legacy boundary limits,
  unsupported preview/date rules and unverified actual indexing are explicit.
  Post-load cross-document browser navigation now fails explicitly instead of
  pairing an earlier response's headers with a replacement DOM. Ordinary HTTP
  redirects and same-document History API changes remain supported.
- Branded Markdown tables have scoped cell/header styling, semantic column
  headers and labelled keyboard-focusable scroll regions. Screen columns retain
  readable minimum widths; print/PDF input uses compact wrapping styles without
  scroll clipping or focus rings. Native scan score-table styling is unchanged.
  A Chromium regression now runs in CI for desktop/mobile/keyboard/print behavior.
- Non-passing page findings link to reference-guide sections in Markdown/HTML
  and PDF input, with additive `reference_url` JSON metadata. Unmapped rules use
  general category context; unknown categories and passing checks get no link.
  Destinations are static, never fetched by scans, and do not validate findings
  or change scores, severity, identities, suppression or diff classifications.
- Compare and brief CLI, Python and MCP interfaces accept a bounded per-snapshot
  `max_bytes` option, allowing deliberate retries of large-page coverage failures.
  The default remains 5MB; 64KB–20MB bounds apply uniformly to all compared pages
  and paired served/rendered inputs. Incomplete-input and private-host guards
  remain active; this is not a total network/browser memory budget.
- Reports lead with high/critical findings rather than an unqualified numeric
  grade. HTML/PDF heroes distinguish urgency from the explicitly labelled score
  band, and Markdown/HTML summaries put findings needing attention first.
- Numeric scoring, JSON finding data, execution-scope caveats and unavailable
  scores are unchanged. A high score does not hide a high-priority finding;
  heuristic findings still need source verification.

### Fixed

- llms.txt metadata is serialized as literal single-line Markdown text, preventing supplied headings/links/HTML from changing starter structure. URL destinations escape parentheses/entity-like text separately; raw URL whitespace/control errors are bounded and preserve CLI output files. Underlying metadata remains unchanged.

- llms.txt generation rejects invalid page/worker budgets before requests or output writes, fixing zero-page requests that still fetched a page. MCP candidate-page work is clamped to 1–100 (default 40); explicit larger positive core/CLI page budgets remain supported.

- Schema generation preserves native MCP/Python JSON field types and returns detached results, preventing caller/template mutations from changing later outputs. Nonfinite/nonserializable fields and invalid UTF-8 fail before CLI output; unsupported MCP template types are recoverable tool errors. Legacy string/CLI interpretation is retained.

- llms.txt discovery follows the successful homepage response URL and its origin, including destination robots rules and entry path, rather than mixing destination metadata with the original alias's resources. Redirect/private-host guards and ordinary no-redirect output are unchanged.

- llms.txt starters remove URL userinfo from candidate links and the host-name fallback while preserving authenticated fetches. Build coverage and CLI/MCP notes disclose removal without claiming public access; path/query/fragment text and ordinary output remain unchanged.

- The llms.txt generator stops before discovery/output when homepage metadata comes from a failed, ranged, truncated, empty or explicitly non-HTML response. Unusable selected pages are omitted with selected-fetch counts in build coverage and CLI/MCP curation notes; healthy starter text is unchanged.

- Generated JSON-LD script blocks escape literal less-than characters so supplied closing-script text cannot break into HTML. JSON values round-trip unchanged, including nested keys/values; bare JSON and MCP objects retain their original representation.

- Remediation planning rejects malformed consumed finding/report evidence with field-specific errors before repository inventory or output writes, rather than silently dropping findings or emitting invalid action fields. Legacy omissions remain supported; invalid UTF-8 and JSON parser-limit failures produce bounded CLI errors.

- Planner page-scan verification templates preserve valid recorded auditor selections, requested rendering and disabled image checks. Scan handoffs explicitly require restoring unrecorded configuration/access/resource limits; page receipts do not fabricate a full site-audit invocation.

- Markdown remediation plans retain every verification step in order, including prerequisite reviews, after-scan commands and deployment scope. Shell commands use literal-safe fenced blocks in both action and shared audit sections; the baseline-saving reminder appears once.

- Remediation plans reserve viewport automation candidates for the supported missing-tag rule with an existing source candidate and no known relevant source-coverage gap. Unknown viewport findings and convention-only owners require review; JSON and Markdown explain eligibility and require source inspection before editing.
- Optional BeautifulSoup parsing preserves document heading order instead of
  grouping headings by level. Heading-jump evidence and brief H2/H3 subtopics
  now follow the selected parser's document order, matching the existing stdlib
  behavior for the tested inputs. Counts, text normalization, rule IDs and
  severity are unchanged; order-sensitive findings and scores can be corrected
  without any page change. This does not promise malformed-HTML or visibility
  parity between parsers, or independent SEO accuracy.
- Generic robots-meta checks combine all active tags, recognize `none` as
  `noindex,nofollow`, and match exact names instead of substrings/parameter
  values. Standalone restrictions before a parameter are retained; later tags
  are no longer hidden by an earlier allowing tag.
  Passing wording now says only that no generic meta noindex was detected, not
  that the page is indexable. Existing rule IDs remain; affected restriction
  findings/scores are corrected. This generic-meta observation excludes headers
  and crawler-specific meta; response headers are handled by the separate check above.
- Markdown tables honor left/center/right separator markers on both headers
  and body cells, including comparison score columns. Only static alignment
  classes are emitted; unmarked/missing/invalid markers retain default left
  alignment, and cell values, column counts and native score tables are unchanged.
- Markdown report tables honor escaped pipes in headers/body, including inline
  code, and retain empty first/last cells. Only the backslash escaping a pipe is
  removed; other backslashes and non-table content retain existing behavior.
- Markdown link destinations remain literal escaped data: underscores and
  asterisks in paths, queries and fragments no longer become emphasis tags in
  `href` values. Labels and surrounding text keep their supported formatting;
  existing HTTP(S)-only link recognition and literal-code guards remain.
- Inline code retains literal Markdown, links and escaped HTML rather than
  formatting its contents. Equal-length backtick runs allow embedded shorter
  runs; surrounding formatting still works. Code cannot become an href value,
  and internal span protection cannot collide with user text. Single-line spans
  retain inner whitespace; this remains a limited report Markdown subset.
- Branded Markdown rendering preserves root fenced code as escaped literal
  content, including whitespace, comments and Markdown-looking examples. Shared
  fence rules keep code headings out of title extraction; screen blocks scroll
  and print/PDF input wraps long lines. Existing non-code rendering and scan
  scoring are unchanged; this is a limited subset, not a full Markdown engine.
- In-memory/Python and parsed-object MCP plans explicitly require preserving the
  original report before verification diffs; read-only planning never saves it.
  Markdown keeps that prerequisite outside shell blocks. File-backed, measurement-
  check-only and empty plans do not receive invented save/diff tasks; actual manual
  hosting fixes retain their requested deployed verification. Coverage is unchanged.
- Sitemap-file discovery/traversal deduplicates literal fragment aliases before
  counting attempts, child slots and remaining files. Repeated `file.xml#…`
  references no longer crowd valid siblings out of bounded samples or multiply
  fetched-file URL entries. Query strings, encoded delimiters and page-location
  source values remain distinct/unchanged; fetch policies and limits remain.
- Planner verification templates avoid known baseline basename collisions for
  both scan and audit workflows, including local page checks. Alternate output
  names stay aligned with diff targets and Markdown, preserving an `after.json`
  or `page-after.json` baseline instead of creating a self-comparison. File aliases
  still require caller checks; the read-only planner does not inspect them.
- Audit-based remediation plans no longer suggest diffing a page scan against
  an audit overall score. Local page checks use a separate artifact; final
  verification reruns an audit after deployment and asks callers to restore the
  original settings and limits. Scan workflow semantics and diff eligibility guards remain.
- Planner verification commands use literal POSIX-shell quoting and an explicit
  option separator for report paths/URLs. Pasted dollar signs, substitutions and
  apostrophes remain data; leading dashes cannot become CLI options. Templates
  are labelled POSIX-specific and never executed by the read-only planner.
- Raw sitemap fetches verify bounded HTTP gzip/deflate wire bodies before
  decoding, including on older optional transports. Short Content-Length and
  incomplete/corrupt compression trailers cannot expose a complete-looking XML
  prefix. Both wire and HTTP-decoded bytes obey the response budget; raw `.gz`
  files retain the separate sitemap decode path. Unsupported HTTP encodings
  remain explicit fetch gaps, and network guards are unchanged.
- Sitemap discovery across scan context, crawl and site validation uses complete
  bounded namespace-aware XML instead of marker/loc regex guesses. Prefixed and
  gzip roots and XML-escaped URLs work consistently; unverified files cannot
  contribute crawl candidates. Candidate scopes/limits are explicit, uncertain
  availability is a non-scoring note/manual check rather than a missing-source
  verdict, and affected technical-score comparisons stay unverified.
- Remediation plans separate sitemap fetch/traversal/sample coverage gaps from
  recorded source defects. Uncertain and legacy-unclassified notes receive manual
  verification without guessed source owners or sitemap-creation instructions;
  consistent current counters add scoped fetch/cap context. Actual invalid URL/
  lastmod and failing sampled HTTP findings retain targeted repair advice.
- Raw sitemap fetches withhold failed HTTP bodies, oversized prefixes and known
  incomplete transfers consistently across requests/urllib. Exact-limit bodies
  remain valid; fetch failures are separate from XML extraction notes and cannot
  contribute URL totals or samples. Explicit failed-file counts label mixed totals
  incomplete. Responses and urllib redirect/error handles
  close on handled paths; unrelated processing errors propagate. Numeric header
  comparisons avoid unbounded integer conversion. Failed file attempts consume
  the sitemap traversal cap, and remaining counts deduplicate visited references.
  Network guards are unchanged.
- Short, unencoded requests streams below the raw byte limit are explicitly
  checked against Content-Length, including older supported optional dependency
  combinations. Encoded/transfer-decoded body sizes are not mistaken for wire
  lengths; complete and encoded controls remain usable.
- Sitemap gzip decoding uses sized streaming reads and a shared per-file
  decoded-byte ceiling of 52,428,800 bytes, including concatenated members.
  Oversized or corrupt/truncated gzip files contribute no XML prefix, URL entries
  or HTTP samples; fixed extraction notes distinguish budget/integrity gaps and
  retain verified siblings. The legacy decode helper is also bounded. This is
  not a total process-memory, CPU or transport budget.
- Crawl and combined audit reports distinguish zero link checks, gated/unknown
  HTTP responses and insufficient duplicate-comparison inputs from clean results.
  Additive coverage counts retain successful, broken and unverified checks;
  no-response request failures stay unverified while legacy unreachable entries
  remain available, distinct from observed broken HTTP responses;
  duplicate scope counts eligible fingerprints, excluding known failed/partial
  pages. Missing legacy receipts stay unrecorded. Headlines label observed/sample
  results rather than presenting disabled checks as zero. Scoring is unchanged.
- Sitemap validation and combined audits record bounded XML extraction coverage
  instead of treating markers, malformed prefixes or unsupported roots as measured
  URL lists. Namespace-aware extraction decodes XML escaping; incomplete files
  contribute no entries, while verified siblings remain usable. Coverage gaps
  get manual verification advice, not instructions to rewrite unsupported formats.
  Sample success requires a successful 2xx response; gated/other responses no
  longer count as OK, and skipped samples explicitly leave reachability unverified.
- Malformed/non-absolute discovered sitemap references no longer abort site
  context, anchor-independent crawl discovery or sitemap validation. Robots
  directives, index children and page locations are syntax-checked before use;
  valid siblings/fallbacks remain available. Bounded source counts distinguish
  rejected references from HTTP failures, preserve raw entry/problem totals,
  and do not echo invalid URLs. Sitemap health is not declared after rejections,
  fetch errors or a reached file cap. User-input errors and fetch guards are unchanged.
- Malformed anchor hrefs no longer crash technical checks, link collection or
  anchor-based crawl discovery. Valid later links remain usable. A low source
  finding and conditional page/crawl omission counts distinguish parser-known
  URL syntax issues from network-dead links, without retaining raw hrefs or
  exception messages. Direct user URL errors and actual-fetch host/redirect
  protections remain unchanged; this is not complete URI or sitemap validation.
- Image-only links with descriptive image alternatives, and otherwise-empty
  links with title fallbacks, no longer receive the empty-anchor-text heuristic.
  Both parser backends retain image alternatives separately from visible text;
  blank/generic fallbacks and independent missing-alt checks remain active.
  This is documented source fallback handling, not a full accessibility-name or
  visibility computation. Existing finding identities and severities remain.
- Robots full-URL matching retains semicolon path parameters, so path-specific
  exclusions and more-specific allowances agree with direct path checks.
  Queries, fragment exclusion and encoded reserved-delimiter distinctions remain.
- Robots matching treats equivalent unreserved ASCII escapes and UTF-8 URI
  spellings consistently, preventing encoded candidates from evading crawl
  exclusions. Encoded reserved delimiters remain distinct, literal encoded
  wildcard/end characters stay literal, and normalized equivalent rules retain
  Allow-on-tie precedence. Path case, explicit robots overrides and existing
  checked-path scopes are unchanged; no complete conformance claim is added.
- AI-crawler scoring distinguishes documented search/retrieval agents from
  training/data-use choices, nonbinding user-fetch directives and unverified
  roles. The latter stay visible as non-scoring policy notes, not blanket
  visibility penalties or instructions to enable training. Page JSON includes
  dated primary-source roles and robots-only `/` scope; current retrieval agents
  are covered without claiming live access, indexing or citations. The existing
  high finding identity/title ignores and planner ownership remain compatible.
- Unknown and non-text HTTP charset names produce bounded failed-fetch
  diagnostics rather than crashing optional `requests` scans or guessing an
  encoding. Supported decoding and malformed-byte replacement are unchanged;
  unrelated processing errors still propagate on the requests path.
- Optional `requests` connection/TLS/timeout and interrupted-body failures now
  return failed-fetch responses instead of aborting scans. Failed streams do
  not expose a received prefix as usable HTML; acquired responses close even
  when decoding or unexpected processing errors propagate. Successful fetches,
  HTTP error status/body diagnostics, and SSRF checks are unchanged.
- Served-HTML baselines use the same selected byte budget as rendered snapshots.
  JS-dependence metrics require two eligible HTML inputs; unavailable, partial or
  explicitly non-HTML baselines yield a visible unverified receipt, not invented
  percentages or cached results. Known missing JS measurements block relevant
  score/finding diffs, including crawl contributions, and compare/brief score
  benchmarks; focused non-JS scores remain comparable. Primary coverage is kept
  distinct from auxiliary baseline coverage. Legacy receipts are not inferred.
- Rendered HTML snapshots now obey the primary HTML byte budget in UTF-8, with
  explicit truncation metadata and no broken final code point. Partial rendered
  snapshots do not produce JS-dependence measurements. Smaller complete snapshots,
  errors, SSRF checks and browser cleanup retain their behavior. This caps retained
  analysis input, not Chromium DOM memory or subresource downloads.
- Origin response headers cannot forge Narwhal's internal truncation marker;
  raw and rendered coverage reflects the client's byte-count calculation.
- Comparisons and content briefs exclude reports explicitly marked as truncated,
  rather than turning unseen HTML into missing-feature gaps or full-page scores.
  Partial targets return errors; partial rivals are skipped with diagnostics.
  Brief requests without any usable page are errors, not page-grounded briefs.
  Standalone partial scans remain available with their coverage warnings; missing
  or malformed legacy flags are not inferred to prove truncation/completeness.
- Content-brief headings, recommendations, CLI help and plugin guidance describe
  supplied comparison pages rather than unverified ranking "winners." Own-page
  Search Console data does not establish competitor rankings. Facts, scoring,
  JSON data and recommendation generation remain unchanged.
- Content briefs retain one supported built-in rule policy across own-page and
  competitor scans, including topic mode and failed competitors. Mid-run caller
  updates no longer switch later pages' scoring/suppression; future briefs still
  see updates. Custom policies stay live; remote content/context is not frozen.
- A failed first URL in competitor comparisons cannot promote a rival to "You"
  or produce a successful target/competitor verdict. HTTP failures, host-policy
  rejection and non-HTML targets yield error diagnostics and CLI exit 2; failed
  competitors remain skippable when the requested target and another rival load.
- Competitor comparisons retain one supported built-in rule policy across page
  scans, including when a failed competitor fetch mutates caller configuration.
  Future comparisons still see caller updates; custom callbacks stay compatible
  and unverified. Remote content and per-site context are not frozen.
- Site-wide human-readable rollups prioritize severity before frequency, so a
  rare critical/high finding is not hidden by more common lower-priority types.
  Ties are deterministic and capped lists disclose omitted types. JSON retains
  its full frequency-ordered counts; scoring and finding generation are unchanged.
- Crawls and audits retain one built-in rule policy across their component/page
  scans instead of mixing configurations after mid-run caller updates. Gathered
  crawl threshold overrides are owned before discovery/worker I/O; audit sitemap
  sampling is resolved at entry. Future operations still see caller changes;
  custom policies stay compatible and unverified.
- Built-in rule inputs and context threshold overrides are owned per scan, so
  caller mutations during page/render I/O or between auditors cannot invalidate
  recorded rule provenance or silently change suppression. Completed reports keep
  their ignore policy; future scans see updated inputs. Custom policies/shapes
  preserve their behavior and remain unverified without invoking copy hooks.
- Diffs no longer count skipped image checks or changed raw/rendered page modes
  as verified fixes when those settings are recorded. Scans serialize requested
  and actual rendering plus effective image-check selection; audits preserve
  crawl-page settings and compare shared exact URLs. Known differences block
  score/finding verdicts and return gate exit 2. Missing legacy settings are not
  inferred, and matching flags do not prove identical configuration or samples.
  Visible scope notes identify disabled images and served/rendered HTML, including
  render requests that produced no measured rendered DOM.
- Recorded fingerprints of scoring weights, effective thresholds and normalized
  ignore rules block fake fixes caused by suppressing findings or changing their
  penalties. Fingerprints expose no raw configuration values or paths; unknown
  custom/unserializable shapes remain unverified. Ignore ordering/case/duplicates
  and equivalent integral numeric weights do not cause spurious mismatches.
  Reports retain their scoring-weight snapshot, so later Config mutations cannot
  silently change a saved report's score while leaving its provenance unchanged.

## [1.30.19] — 2026-10-12

### Fixed
- Native numeric zero is present merchant evidence, not a missing price. Zero
  Offer prices retain the high nonpositive-price finding and can be compared
  against explicit matching-currency page amounts; they are not replaced by
  a positive priceSpecification fallback. Missing/positive prices and boolean
  handling retain their existing behavior.

## [1.30.18] — 2026-10-12

### Fixed
- JSON-LD value objects and their opaque JSON literal payloads are not entity
  nodes. Tutorial examples no longer create Product/Offer merchant evidence, and
  value datatypes no longer appear in the entity-type coverage summary.
- Literal payloads preserve arrays, datatype IRIs, context data and exact JSON
  content through normalization and deduplication. Real graph/list entities and
  independent merchant cues remain active. This is not full JSON-LD expansion
  or datatype/value validation; scalar value interpretation remains bounded.
- Product classification also excludes context definitions and value objects.
  Literal-valued offers are not counted as purchase/Offer evidence.

## [1.30.17] — 2026-10-12

### Fixed
- Point Offer prices and multi-Offer consensus use exact bounded decimal parsing:
  scientific notation is not digit-stripped, and long unequal prices are not
  rounded equal by the caller's Decimal context.
  JSON decimal number tokens retain their lexemes rather than rounding through
  binary floats before comparison.
- Point-price comparisons, like ranges, require explicit matching currency units
  and parseable observed amounts. Supported localized display forms remain;
  prose, malformed separators and conflicting units are not guessed. Other
  currency/stock/identity and completeness checks remain active.
- Unsupported declared price text produces a low extraction/verification note,
  not a schema.org invalidity verdict. Known nonpositive merchant prices retain
  their high finding. JSON exposes exact point-comparison evidence and limits.

## [1.30.16] — 2026-10-12

### Fixed
- Diffs no longer classify omitted auditor groups as resolved fixes. Known
  mismatched or incomplete execution, truncated HTML and page/audit score-kind
  mismatches produce an explicit incomparable diagnostic with no change verdict.
- `--fail-on-regression` exits 2 for known incomparable coverage. JSON records
  comparison status/reasons and null score delta/regression for unmeasured
  comparisons; matching completed full/focused scopes retain normal diff gates.
- Legacy/malformed execution scope remains unknown, not inferred from findings.
  Compatible legacy comparisons now warn visibly; matching auditor scope alone
  does not prove identical configuration, rendering, rules or site-wide samples.

## [1.30.15] — 2026-10-12

### Fixed
- Scan, audit, crawl, llms and sitemap CLI boundaries report expected URL syntax,
  DNS/host-policy rejections as bounded single-line diagnostics with exit 2,
  rather than tracebacks or successful-looking scan reports. Programming errors,
  interrupts and argparse behavior remain visible; core APIs still raise.
- URL normalization validates lazy host/port syntax and classifies expected
  failures without weakening SSRF checks. Explicit private previews remain
  opt-in; no output is written or overwritten on rejection. Syntax diagnostics
  do not echo parser errors containing URL credentials or query values.
- Initial sitemap targets are validated before discovery/walking, so a blocked
  direct XML target does not emit an error report with exit 0. Crawl/llms entry
  URLs normalize before parsing site context; supported bare hosts and valid
  ports remain usable.

## [1.30.14] — 2026-10-12

### Fixed
- Focused scans identify requested, completed and unselected auditor groups in
  JSON, Markdown and HTML/PDF. Selected-check scores are no longer presented as
  overall page health; full selections remain page-level, not exhaustive audits.
- Failed/non-HTML responses record no completed auditors and show a fail-safe
  zero as not measured, without fabricated area grades. Truncated response
  coverage stays explicit; legacy reports do not infer scope from finding counts.
- Duplicate auditor selections run only once. Custom report titles remain;
  accessible gauges and threshold failures use the correct scope label. Normal
  unique-selection score weights and findings are unchanged.

## [1.30.13] — 2026-10-12

### Fixed
- Recipe base-field checks now follow Google's name/image requirements.
  Ingredients and instructions are recommended, not mandatory; absent/blank
  required name/image values are high findings instead of passing as complete.
- Recipe reports expose dated primary-source policy and unverified conditional,
  nested, image and datatype/reference scope. Recommendations never ask for
  invented authors or ratings, and are not full rich-result eligibility verdicts.
- Recipe generators align required/recommended fields while preserving useful
  scaffolds and explicit fields. Legacy ingredient/instruction-only ignores stay
  field-scoped; other schema types and existing name/recommendation IDs remain.

## [1.30.12] — 2026-10-12

### Fixed
- Article, NewsArticle and BlogPosting no longer treat headline as a mandatory
  rich-result property. Missing applicable headline/author/datePublished/image
  values are grouped low recommendations, with Google's no-required-properties
  scope and dated source metadata, not invalidity or eligibility verdicts.
- Absent/blank Article values are detected without inventing authors/dates or
  claiming full datatype/reference validation. Other types retain their existing
  checks; legacy headline-only ignores do not suppress unrelated recommendations.
- Article-family generators label headline recommended, not required; the
  no-recommended mode does not inject mandatory placeholders. Explicit fields
  and useful default scaffolds remain. Reference and specialist guidance align.

## [1.30.11] — 2026-10-12

### Fixed
- Google rich-result retirement notices now use source-checked current status:
  FAQ appearances ended in May 2026; ClaimReview and SpecialAnnouncement support
  ended in 2025. ClaimReview's Fact Check Explorer use is explicitly preserved.
- Notices distinguish Google visual appearances from schema.org validity or
  ranking, with dated primary-source provenance in JSON and recommendations.
  Historical finding IDs, low severity and legacy title-substring ignores remain
  stable. Sources are not fetched during scans; valid FAQ generation remains.
- Schema reference and specialist guidance no longer describe retired FAQ and
  ClaimReview appearances as merely restricted. Feature-specific Course Info
  retirement is not generalized to all Course markup or Course list support.

## [1.30.10] — 2026-10-12

### Fixed
- Product H1/name comparisons now use the selected Product name, never an
  Offer's sale/seller label. Offer names cannot create false Product mismatches,
  mask genuine name disagreements or fill a missing Product name.
- Existing variant selection, range/price/currency/stock comparisons and
  non-name field source precedence are unchanged. Local references and all
  supported structured-data formats retain their original node names.

## [1.30.9] — 2026-10-12

### Fixed
- Inert source templates no longer supply JSON-LD, metadata, canonical links,
  headings, links, images or language to the normalized page view. A cached
  stdlib projection is shared by HTML backends, main-content extraction and lazy
  Microdata/RDFa/merchant consumers; original HTML remains available as evidence.
- Nested/unclosed templates and non-void template slash syntax are consistent
  across backends. Script/style text and textarea/title literals cannot open or
  close templates; comments and entities are preserved. Ordinary hidden JSON-LD
  remains readable. Malformed marked declarations do not abort projection.
- Chromium smoke coverage checks inert Product examples are ignored and
  JavaScript-cloned active Product schema is detected exactly once. This source
  projection is not a complete HTML5, foreign-integration or shadow-root parser.

## [1.30.8] — 2026-10-12

### Fixed
- A single AggregateOffer compares the displayed amount against its inclusive
  lowPrice/highPrice range, not the lower bound as an exact seller price. Valid
  numeric bounds and matching explicit currencies are required; outside-range
  amounts remain high mismatches. JSON records range-compatibility evidence,
  not proof of a selected seller or an Offer at every interior amount.
- Missing, unsupported or incomparable range evidence gets a verification note
  while completeness/currency findings remain. Known negative or inverted
  numeric bounds get a high range finding. Decimal comparisons do not round
  quoted amounts; ordinary Offer and multi-Offer consensus behavior is preserved.

## [1.30.7] — 2026-10-12

### Fixed
- Multiple Offers no longer select the first price/currency/stock value for page
  comparisons. Non-unique or incomplete fields get a low verification note;
  agreed fields and Product identity checks remain active.
- Numeric price consensus requires matching declared and observed currencies;
  any AggregateOffer in a multi-Offer comparison blocks Offer-based price
  consensus, including homogeneous sets. Per-field
  `offer_comparison_status` is explicit in JSON. All-offer validity/completeness
  checks and existing single-Offer behavior are preserved.

## [1.30.6] — 2026-10-12

### Fixed
- Microdata, RDFa and merchant-source warning output is bounded: 64 retained
  details per extraction plus one explicit omission notice, with 512-character
  detail limits and visible truncation markers. Valid extraction continues.
- Warning deduplication is bounded and constant-time; repeating a retained
  warning at the cap does not incorrectly claim additional details were omitted.
- Omission/truncation summaries remain visible in HTML quick-win recommendations.

## [1.30.5] — 2026-10-12

### Fixed
- Non-string Offer references and non-object price-specification members no
  longer crash merchant scans. Malformed IDs are field-specific findings;
  unsupported price-specification shapes produce a bounded-coverage note.
- Supported object members survive mixed arrays; null members remain ignored.
  Local string Offer references, completeness checks and real price mismatches
  remain intact. No remote reference or JSON-LD context is fetched.

## [1.30.4] — 2026-10-12

### Fixed
- Multi-Product page comparisons no longer choose the first schema variant.
  A unique visible identifier, exact name or unambiguous name match is required;
  ambiguous identity produces a low-severity verification note instead of a
  guessed mismatch. All Product/Offer completeness and validity checks remain.
- Comparison status and selection method are explicit in JSON; no selected
  Product is reported when identity is ambiguous. SKU punctuation and Unicode
  characters remain significant in selection and mismatch checks.

## [1.30.3] — 2026-10-12

### Fixed
- Malformed Product and Offer URLs produce field-specific findings instead of
  crashing scans. Missing hosts, invalid ports, embedded whitespace/control
  characters and backslashes are rejected by local syntax validation.
- Valid IPv6, Unicode hosts, encoded paths and non-default ports remain accepted.
  Validation does not resolve DNS, fetch offer URLs or claim reachability.

## [1.30.2] — 2026-10-12

### Fixed
- Merchant evidence now uses one cached, bounded source parse instead of regex
  matches over HTML. Templates, comments, escaped examples and explicitly hidden
  subtrees cannot supply price, identity, labels or purchase controls.
- Inactive OpenGraph examples cannot classify articles as Product pages; the
  first active type declaration retains preference order.
- Active itemprop values support multi-name properties, exact schema.org URLs
  and element-specific values. Linked brand names use their visible label.
- Partial merchant-source coverage and invalid URL warning limits are explicit
  in JSON and a stable verification finding. No browser visibility is claimed.
- RDFa tests support both root and skill-directory test discovery.

## [1.30.1] — 2026-10-12

### Fixed
- Merchant classification now requires Product evidence and a selling signal;
  documentation and SKU-only editorial reviews no longer enable store checks.
- Prose-label fallback requires an explicit separator rather than interpreting
  schema vocabulary definitions as brand, SKU or availability facts.
- Crawl merchant rollups reject contradictory legacy non-product flags.
- Purchase-action fallback requires an enabled control or same-origin purchase
  link; prose, inert/hidden controls and external affiliate links are excluded.

## [1.30.0] — 2026-10-11

### Added
- Bounded, stdlib-only schema.org RDFa extraction: scoped vocabularies/prefixes,
  nested entities, local subject references, resource URLs and scalar literals.
  Unsupported relations/lists/copying/markup literals and resource limits are
  explicit partial-coverage warnings; no referenced resources are fetched.
- Shared JSON-LD/Microdata/RDFa schema and merchant checks, three-format
  deduplication, RDFa provenance and coverage metadata, and comparison facts.

### Fixed
- Valid supported RDFa no longer receives missing-structured-data penalties.
  Inert examples, foreign namespaces and vocabulary rebinding do not create
  product false positives. Remediation guidance preserves valid RDFa.

## [1.29.0] — 2026-10-11

### Added
- Stdlib-only schema.org Microdata extraction: nested scopes, repeated and
  multi-name properties, typed values, relative URLs, item IDs, and bounded local
  `itemref` resolution. Extraction limits and invalid references remain visible.
- Shared JSON-LD/Microdata schema and merchant validation, format provenance in
  scan JSON, equivalent-node deduplication, and Microdata-aware comparison facts.

### Fixed
- Product/Offer Microdata no longer receives missing-JSON-LD penalties. Inert
  templates, escaped examples, and lookalike namespaces do not classify articles
  as product pages. Remediation guidance preserves existing valid markup.

## [1.28.0] — 2026-10-11

### Added
- Full Markdown, JSON, and self-contained HTML report golden snapshots from a
  fixed offline fixture, plus a one-command regeneration script.
- Evidence-gated e-commerce checks within the schema auditor: Product and
  ProductGroup detection, per-variant identity completeness, Offer and
  AggregateOffer merchant properties, nested `priceSpecification`, expired
  price validity, and explicit visible-vs-schema price, currency, availability,
  SKU, brand, and name comparisons. Crawl/audit JSON exposes sampled merchant
  pages for conditional orchestration.
- Conditional `narwhal-ecommerce` deep-audit specialist plus dedicated
  remediation-planner ownership and guidance for `schema.ecommerce.*` rules.
- Product, non-product, malformed, AggregateOffer, variant, stale, missing, and
  mismatch fixtures with parser-backend parity coverage.

### Changed
- Package metadata, CLI, and report provenance now share one canonical release
  version. A stdlib synchronization command updates plugin manifests, and CI
  rejects drift instead of relying on manual edits across six files.
- Split the 2,095-line smoke-test monolith into focused parser, auditor,
  report, tool, and integration modules while preserving zero-config discovery.
- Product schema generation now emits explicit TODOs for merchant currency,
  availability, URL, condition, and seller instead of assuming USD/InStock.

## [1.27.0] — 2026-08-10

### Added
- **`narwhal plan REPORT.json --repo PATH`** — a deterministic, read-only
  remediation planner for scan and comprehensive-audit JSON. It detects plain
  HTML, Next.js, Astro, Nuxt, Hugo, and Jekyll; maps stable finding IDs to likely
  route/layout/static owners; classifies automation safety and deploy-only
  verification; groups shared-template work; and reports conflicts, coverage,
  warnings, and provenance in Markdown or a versioned JSON contract.
- MCP tool **`plan_remediation`**, bounded to relative repository descendants of
  the server working directory and accepting report objects rather than file
  paths.
- MCP Python SDK 2.x compatibility (while retaining 1.x support) and a two-major
  CI contract matrix; this prevents `mcp>=1.12` from resolving to an SDK whose
  renamed high-level server cannot start.
- Formal remediation-plan JSON Schema, six representative framework fixtures,
  and golden Markdown coverage.

## [1.26.0] — 2026-07-03

### Added
- **`narwhal brief` — data-driven content briefs** (closes
  [#26](https://github.com/aindong/narwhal/issues/26)). Turns "what should we
  write?" into a plan grounded in data Narwhal already has — no keyword APIs,
  no fabricated search volumes:
  - **Target queries** from the page's own GSC **striking-distance** rows
    (positions 8–20), plus its CTR-laggard / decay / cannibalization status —
    real Search Console data only. Without credentials the brief degrades to a
    clearly labeled **structure-only** brief (queries omitted, never invented).
  - **Competitor gaps** via the `compare` engine (schema types, meta strategy,
    OG/social packaging), deduplicated against the structure section.
  - **Missing subtopics** — competitor H2/H3 sections whose topic words don't
    appear in your page text (inflection-tolerant matching; nav/footer
    boilerplate and one-word column labels filtered out).
  - **Questions to answer** — competitors' question-shaped headings you don't
    cover + your own question-shaped striking queries.
  - **Schema suggestions** (`narwhal schema <Type>` for each) and **structure
    targets** (depth/evidence benchmarks vs the compared pages; hub pages
    excluded as benchmarks).
  - **`--topic` mode** plans a page that doesn't exist yet from competitor
    pages; `--gsc-site` folds in real adjacent queries site-wide.
  - Wired everywhere: `narwhal brief` CLI, **`/narwhal brief`**
    (agent-orchestrated editorial synthesis: outline, metadata drafts, branded
    HTML via `narwhal render`), and MCP tool **`content_brief`**.

### Fixed
- **`compare`: false "Content depth" lead when every rival is a hub page**
  (found live while building the brief). The lead check's `all()` over non-hub
  rivals was vacuously true, so a 138-word page "led" a 521-word competitor.
  Depth gap/lead now compares only non-hub rivals, with a regression test.

12 new tests (191 total), green stdlib-only and with bs4/lxml/trafilatura.

## [1.25.1] — 2026-07-02

### Fixed
- **`<noscript>`-fallback content is now measured** (corpus addition:
  openskyelabs.xyz). JS-shell sites that serve their entire content inside
  `<body><noscript>…</noscript>` scanned as **"~0 words"** with empty
  headings/links — while non-rendering crawlers and AI fetchers read that
  fallback just fine. Both parser backends now capture noscript into a separate
  channel: `body_text` falls back to it when the page has no regular body text
  (labeled `measured on noscript fallback`), headings/links inside noscript keep
  their text, and tiny noscript blocks (font loaders) change nothing.

### Added
- New technical finding: **"Content served only as a `<noscript>` fallback"**
  (medium) — rendering and non-rendering crawlers see different documents;
  SSR/SSG recommended. 3 new tests (179 total), green with and without extras
  (with trafilatura installed the same content is isolated by trafilatura —
  covered by the tests).

## [1.25.0] — 2026-07-02

Tuning Round 2 (documented with raw snapshots in `docs/tuning/2026-07-round-2/`):
corpus grown 8 → 14 pages by adding page *types* — product URL, real articles, a
Recipe-schema page, a French site, an international hreflang site, and a
deliberately dead URL. Two live specialist runs graded (schema: validated the
full Recipe graph beyond the script; performance: measured real wire sizes and
caught a caveat in our own image check).

### Fixed
- **Unfetchable pages now score 0** — a 404 used to score 88/100 (one critical
  finding = −12), which read as "healthy". New `Report.hard_fail`.
- **og:image behind a rate-limiting CDN is no longer "broken"** — gated codes
  (429/403/…) now report "could not be verified" (low), reusing the broken-link
  checker's UNDETERMINED semantics.
- **Non-English pages skip English-calibrated checks** (Flesch readability,
  filler/AI-writing patterns) — and claim nothing, instead of mislabeling
  French prose "very hard to read".

### Changed
- **Readability severity is article-scoped** — terse marketing homepages get
  low, not medium.
- **"No structured data" is low on hub/index pages** (no single entity to mark
  up); articles/products/homepages keep medium.
- **Heavy-image findings are srcset-aware** — when every heavy image carries
  srcset, the finding is framed as *fallback weight* (what scrapers and
  srcset-unaware clients download) and capped at low. Lesson credited to the
  graded performance-agent run; also encoded in the agent's prompt.

6 new regression tests (176 total), green with and without parser extras.

## [1.24.0] — 2026-07-02

### Added
- **Cross-page hreflang validation** (closes #25 — the last P1 of the next
  wave; `lib/hreflang.py`). When a crawled site uses hreflang, the crawl now
  verifies the *relationships*, not just per-page syntax:
  - **Missing return tags** reported as exact `A → B (lang)` pairs — one-way
    hreflang is ignored by Google, so this is the killer check.
  - **Missing self-references** (each page must list itself) and **invalid
    language codes** (BCP-47 subset: lang / optional script / optional region).
  - **Sample-wide x-default** presence check.
  - **Capped alternate probe**: up to 5 same-host alternates the crawl didn't
    reach are fetched (link tags only) so reciprocity is actually verifiable.
  - **Cap-aware honesty**: targets outside the crawled/probed sample are
    counted *unverified* — never reported broken.
  - Verified live on a 137-locale international site: probe verified 5
    alternates reciprocal, correctly flagged the missing x-default, and labeled
    786 outside-sample targets unverified. 7 new tests (170 total), green with
    and without parser extras.

## [1.23.0] — 2026-07-02

### Added
- **Image weight/format checks + og:image validation** (closes #24,
  `lib/images.py`). Single-page scans now check, within a strict budget (up to
  10 HEAD requests — headers only — plus one ~64 KB ranged GET):
  - **Heavy images**: >200 KB flagged with real sizes as evidence (≥500 KB or
    3+ heavy escalates to medium) — a top LCP cause.
  - **Legacy formats worth converting**: JPEG/PNG over 100 KB → AVIF/WebP
    candidates.
  - **Missing width/height** on >30% of images → CLS risk (pure, no network).
  - **og:image validation**: reachability (broken → high) and **real
    dimensions** parsed from partial bytes — a stdlib PNG/GIF/JPEG/WebP header
    prober (`probe_dimensions`), no imaging library. Under 200px → medium;
    under 1200px wide → low; healthy gets a passing note with the dimensions.
  - `--no-image-checks` to skip; crawls skip automatically (per-page HEADs
    would multiply). New SSRF-guarded `http.head_info` and `http.fetch_range`.
  - Verified live: real og:images probed correctly (1200×630 and 2048×1024) and
    genuine heavy/legacy findings on two major sites. 4 new tests (163 total),
    green with and without parser extras.

## [1.22.0] — 2026-07-02

### Added
- **JS-dependence check** (closes #23, `lib/jsdiff.py`): scans run with
  `--render` now diff the **served HTML against the rendered DOM** and report —
  the **JS-only share of the content** ("1 word served vs 407 after JavaScript —
  100% JS-only", tiered: ≥30% high / ≥10% medium), **headings that only exist
  post-JS** (as evidence), and **client-injected head metadata**
  (title/description/canonical high; JSON-LD medium). A GEO finding fires on
  heavy dependence — most AI answer-engine fetchers don't execute JavaScript.
  - Honest by design: without Playwright there is no rendered DOM, so the check
    is silent — it never guesses. Server-rendered pages get a passing note.
  - Verified end to end with real Chromium: a local CSR fixture (100% JS-only
    detected) and a real SSR site (0% + a genuine client-injected JSON-LD
    finding). 5 new tests (159 total), green with and without parser extras.

## [1.21.0] — 2026-07-02

### Added
- **Site-structure analysis in every crawl** (closes #22, `lib/sitegraph.py`):
  the crawler now builds the internal-link graph from pages it already parsed
  (zero extra requests) and reports — **click depth** from the start URL (buried
  pages flagged past 3 clicks), pages **unreachable** from the start within the
  sample, **zero-inbound** pages (weak link equity), **most-linked** pages, and
  sitemap **orphan candidates** (sitemap URLs no crawled page links to; crawled
  pages are excluded — they're covered by zero-inbound with more certainty).
  - **Sample-aware honesty**: every claim carries the crawl-sample size; orphan
    detection only runs when a sitemap was actually found.
  - In `crawl` and `audit` Markdown/JSON automatically (`graph` block); the
    `narwhal-links` specialist is pointed at it.
  - Link collection is now always on during crawls (pure parsing, no extra
    network), so the graph needs no flag.
  - Verified live on a real 12-page crawl (correctly surfaced unlinked taxonomy
    pages and an unlinked content section as orphan candidates). 5 new tests
    (154 total), green with and without the optional parser extras.

## [1.20.0] — 2026-07-02

### Added
- **`narwhal compare <you> <rival…>` — side-by-side competitor comparison**
  (closes #21). Runs the same auditors on your page and 1–3 competitor pages,
  extracts comparable facts (per-area scores, schema types, title/meta strategy,
  depth, structure, question headings, evidence, social packaging), and reports:
  a **scoreboard**, a **side-by-side fact table**, **"Gaps to close"** (what they
  have that you don't, each with the action), and **"Where you lead"**.
  - **Local-first by design**: it only fetches the pages you name — no rank or
    keyword APIs — and the report says explicitly that a gap is an on-page
    difference, *not proof of why anyone ranks*.
  - Resilient: a dead/unresolvable competitor URL is skipped with a note instead
    of sinking the run (found via live testing).
  - Plugin-native (`/narwhal compare`), MCP tool (`compare_pages`), documented in
    SKILL/AGENTS/README; Markdown/JSON output; schema-type gaps grouped into one
    actionable entry.
  - Verified live: vercel.com vs stripe.com and jvns.ca vs blog.cloudflare.com
    (the latter independently re-found the OG/Twitter gap our content specialist
    had reported). 6 new tests (149 total).

## [1.19.0] — 2026-07-02

Real-world tuning round (#19, #20): scans of 8 diverse live sites (SaaS,
e-commerce, news, docs, blog, wiki, link-hub) + 3 live specialist-agent runs,
then every false positive fixed at the source. Average score change on well-run
sites: jvns.ca 62→79, HN 52→66, docs.python.org 75→86, The Verge 71→80 — all
from removing *wrong* findings, not loosening checks.

### Fixed
- **Stdlib parser lost headings that wrap links** (`<h1><a>…</a></h1>` recorded no
  H1 — false "No H1" on most real blogs) and **dropped all anchor text from the
  visible text** (link-heavy pages looked falsely thin). Captures are now a stack
  and captured text flows into the page text; `<title>` stays out of body copy.
- **Month names counted as "dominant topics"** on date-heavy archive pages
  (`dec (78), jan (74)…`) — now stopworded.

### Changed — page-type-aware checks
New shared helpers (`htmlx.is_hub_page` / `looks_article` / `is_homepage` /
`link_text_share`) scope checks to the page's role:
- Brand-only **homepage titles** are a low note, not "Title very short (high)".
- **Link-hub/index pages** get "hub with little prose (low)" instead of "Thin
  content (high)"; readability isn't judged on nav fragments.
- **Byline/author** is only expected on article pages.
- GEO **question-headings** and **evidence-density** are medium on articles, low
  elsewhere (they used to fire on ~90% of real sites).
- The schema auditor's "article-like page" now uses the shared heuristic instead
  of raw text length (no more Article-schema nags on text-heavy homepages).
- Depth findings state their **extraction basis** (trafilatura main-content vs
  visible text), and the trade-off is documented (#20).

### Changed — specialist agents (tuned from graded live runs)
All 10 `agents/narwhal-*` prompts gain **Judgment rules**: classify the page type
first and discount type-mismatched script findings; sample a representative inner
page when auditing a domain root; respect deliberate owner choices (e.g.
intentional AI-crawler opt-outs — split advice by intent, never "fix" an opt-out).
GEO adds the training-vs-answer-engine distinction (GPTBot ≠ AI-answer
visibility); technical verifies surprising negatives in raw HTML. Specialists now
return a **Discounted script findings** section, and the audit orchestrator
honors it (discounts are never re-added to the action plan).
`${CLAUDE_PLUGIN_ROOT}` confirmed to resolve for subagents in the field.

## [1.18.0] — 2026-07-02

### Added
- **Google Search Console integration (`narwhal gsc <site>`)** — opt-in, real
  query data for your verified property: **striking-distance** queries
  (positions 8–20 with impressions), **CTR laggards** (top-10 rankings far below
  the expected-CTR curve — title/meta rewrite candidates; the curve is a labeled
  heuristic), **decaying pages** (clicks down ≥25% vs the prior window), and
  **keyword cannibalization** (several pages splitting one query). Markdown/JSON
  output; `--days`, `--min-impressions`.
- **Stdlib-only OAuth** (GSC has no API-key path): `GSC_ACCESS_TOKEN`
  passthrough, or the durable `GSC_CLIENT_ID`/`GSC_CLIENT_SECRET`/
  `GSC_REFRESH_TOKEN` trio — obtained once with **`narwhal gsc --auth`**
  (loopback browser consent; `--write-env` stores the credentials in `.env`).
  Read-only scope; only fixed Google hosts are contacted. Service-account auth
  deliberately deferred (would need a crypto dependency).
- **`narwhal audit --gsc`** folds the same data into the audit (new
  "Search performance (GSC)" section in Markdown/HTML, `gsc` block in JSON, and
  a clicks headline in the metrics strip), mirroring `--vitals`; degrades to a
  one-line note without credentials. `/narwhal audit` now prioritizes the action
  plan by real queries when the block is present, and `/narwhal fix` fixes pages
  with actual search opportunity first.

### Changed
- The audit's conditional report sections (Core Web Vitals, Search performance)
  are now numbered dynamically instead of hardcoding "4."

## [1.17.0] — 2026-07-02

### Added
- **`/narwhal fix <site>` — close the audit → fix loop.** When the site's source
  is in the current workspace, the agent maps each scan/audit finding to the file
  that owns it (title/meta, canonical, OG/Twitter, JSON-LD via
  `generate_schema.py`, alt text, robots.txt, `llms.txt` via `generate_llms.py`),
  applies minimal framework-idiomatic edits, then **re-scans and runs
  `diff_scan.py`** to prove what resolved and the score delta. Honest by design:
  localhost re-scans verify page-level fixes only (site-level signals are labeled
  *verify after deploy*), "applied, pending deploy" when there's no local preview,
  no edits + a per-finding fix plan when the source isn't in the workspace, and a
  "needs manual action" list for findings unreachable from the repo. Fix-loop
  guidance also added to `SKILL.md` and `AGENTS.md` for non-Claude agents.

## [1.16.1] — 2026-07-02

### Changed
- **`/narwhal audit` delivers HTML by default again** (needs no extra tools). PDF is
  now opt-in — the Chromium/WeasyPrint engines and `--format pdf` remain available
  for anyone who wants a PDF, and the self-contained HTML can be Printed → Saved as
  PDF from any browser.

## [1.16.0] — 2026-07-02

### Added
- **Second PDF engine: headless Chromium (Playwright).** `pdf_from_html` now tries
  WeasyPrint, then Chromium print-to-PDF — which renders our exact CSS (pixel-perfect
  branded PDF) and installs cleanly cross-platform (it also powers `--render`).
  Verified end to end (real branded PDF generated via Chromium).

### Changed
- **`/narwhal audit` delivers a PDF by default.** Step 4 now renders
  `narwhal-audit-report.pdf`; with no PDF engine it falls back to a self-contained
  HTML (and the message lists both install options + the "Print to PDF from your
  browser" escape hatch).

## [1.15.0] — 2026-07-02

### Added
- **`/narwhal audit` now delivers a branded report file** — not just chat output. It
  writes `narwhal-audit-report.md`, then renders a self-contained, branded **HTML**
  report (`narwhal-audit-report.html`) of the synthesis and offers a **PDF**.
- **`narwhal render <file.md>`** (`render_report.py`) — turns any Markdown report
  into a branded HTML/PDF (inline CSS + logo, same look as scan/audit reports).
  Reuses the report renderer; `--format html|pdf`, first `# heading` becomes the
  title, reads stdin with `-`.
- The Markdown→HTML converter now renders `[text](https://…)` **links**.

## [1.14.0] — 2026-07-01

### Added
- **Branded HTML/PDF reports** — the Narwhal logo now appears in the report header
  (next to the title) and footer. It's embedded **inline as a base64 data URI**
  (`lib/brand.py`), so reports stay fully self-contained (no external request,
  works offline and in the pip/uvx package where `assets/` isn't shipped).
  Regenerate with `assets/make-brand-logo.py`. Applies to `scan` and `audit`
  HTML/PDF output.

## [1.13.0] — 2026-07-01

### Added
- **Core Web Vitals in the audit report** — `narwhal audit <site> --vitals` now runs
  CrUX **field** data (origin-level, when `CRUX_API_KEY` is set) and falls back to
  PageSpeed Insights **lab** data for low-traffic sites, then includes a **Core Web
  Vitals** section in **every** output format: Markdown, **HTML, PDF**, and JSON
  (plus a headline in the report's metrics strip). Field vs lab is clearly labeled.
  ```bash
  narwhal audit https://example.com --vitals --format pdf -o audit.pdf
  ```
- The `/narwhal audit` command passes `--vitals` in its baseline step, folds the
  verdict into the report, and offers a shareable HTML/PDF that includes it.

### Fixed
- The Markdown→HTML converter now renders `_italic_` (so the honest field/lab notes
  in HTML/PDF reports no longer show literal underscores); word-boundary-guarded so
  `snake_case` and paths are untouched.

## [1.12.0] — 2026-07-01

### Added
- **PageSpeed Insights (Lighthouse) lab data** via `narwhal vitals <url> --lab`
  (`psi.py`) — the companion to CrUX field data. Works for **any URL regardless of
  traffic**, so it fills the gap when CrUX has no field data (most pages). Returns
  an overall performance score plus LCP, **TBT** (the lab proxy for INP), CLS, FCP,
  Speed Index, and TTI, each rated.
  - Clearly labeled **lab/synthetic** (an estimate for catching regressions), never
    conflated with real-user field data. Lab has no INP.
  - PSI key optional (keyless runs at a shared, easily-exhausted quota, so a key is
    recommended): `PAGESPEED_API_KEY`, or reuse the CrUX key with the PageSpeed
    Insights API also enabled. `--strategy mobile|desktop`.
  - The CrUX "no data" message now points to `--lab`; verified against the live
    PSI v5 API contract.

## [1.11.0] — 2026-07-01

### Added
- **`vitals` and `diff` are now plugin-native** — wired into the `/narwhal <action>
  <site>` command and documented in the skill, not just the CLI. `/narwhal vitals
  example.com` runs the real CrUX Core Web Vitals lookup (resolving the key from the
  env or a `.env`, which Claude Code inherits), and `/narwhal diff old.json new.json`
  compares two saved reports.
- **The multi-agent `audit` now folds in real Core Web Vitals** when a `CRUX_API_KEY`
  is available (runs `crux.py --origin` and merges the field verdict into the
  performance section); otherwise it stays honest and points at `/narwhal vitals`.

## [1.10.0] — 2026-07-01

### Added
- **`.env` support for the CrUX key** so you don't have to pass `--crux-key` every
  time. `narwhal vitals` now resolves the key as **`--crux-key` > `CRUX_API_KEY`
  env var > `.env` file** (auto-loaded from the working directory or a parent).
  Zero-dependency loader (`lib/env.py`); `.env` is gitignored, so secrets never get
  committed. Added [`.env.example`](.env.example); the "key required" message now
  lists all three options. (Never put the key in `narwhal.toml` — that's committed.)

## [1.9.0] — 2026-07-01

### Added
- **Dark-mode logo** (`assets/logo-dark.png` + `-512`): the navy structure and
  "NARWHAL" wordmark are recolored to light icy-blue so the mark reads on dark
  backgrounds, while the teal/aqua stays vivid. The README auto-swaps to it via a
  `<picture>` element (`prefers-color-scheme: dark`). Derived deterministically
  from the light logo (`assets/make-dark-logo.py`, luminance fold) — same artwork,
  regenerable in one command.

This release also marks the **P2 roadmap backlog (#13–#18) fully cleared.**

## [1.8.0] — 2026-07-01

### Added
- **Real Core Web Vitals** (`narwhal vitals <url>`): opt-in field data from Google's
  Chrome UX Report (CrUX) API — **LCP, INP, CLS** at the 75th percentile, each rated
  good/needs-improvement/poor, with a pass/fail verdict, plus FCP/TTFB as secondary.
  Origin- or URL-level, per form factor. Verified against the current CrUX API.
  - The only feature that calls an external service — **opt-in**, gated behind an API
    key (`--crux-key` / `CRUX_API_KEY`); never on the default scan path.
  - Honest: no key → clear message; low-traffic URL with no CrUX data → says so
    (suggests `--origin`); never fabricates field metrics.
  - Built against the CrUX API directly, since PageSpeed Insights is dropping CrUX
    field data in 2026 (and INP replaced FID in 2024).
- The `narwhal-performance` agent now points at `narwhal vitals` for real field data.

## [1.7.0] — 2026-07-01

### Changed
- **Hardened the `--render` (Playwright) path.** Verified against Playwright 1.61:
  - Missing Chromium binary now yields an actionable one-line fix
    (`python -m playwright install chromium`) instead of a raw error.
  - Navigation waits on `domcontentloaded` then a **capped** `networkidle` settle
    (5s max) — `networkidle` alone could hang on analytics/long-polling sites.
  - Browser is always closed via `try/finally` (no leak on error); container-safe
    launch (`--disable-dev-shm-usage`, sandbox kept on for untrusted pages).
  - A render that can't run reports an honest error rather than silently degrading
    to raw HTML.
- `pdf_from_html` now also handles WeasyPrint being installed without its native
  libraries (`OSError`), falling back to HTML instead of crashing.

### Added
- CI **`render-smoke`** job: installs Playwright + Chromium and asserts the
  `--render` path executes JavaScript end to end (serves a JS page, checks the
  post-JS DOM). Bumped `actions/checkout` to v5.

## [1.6.0] — 2026-07-01

### Added
- **MCP server** (`narwhal mcp`): exposes the auditors as Model Context Protocol
  tools over stdio — `scan_page`, `crawl_site`, `audit_site`, `validate_sitemap`,
  `generate_llms`, `generate_schema`, `diff_reports`. A thin, typed adapter over the
  existing scripts (results match the CLI). Built on the MCP Python SDK's `FastMCP`;
  verified against the current release. Optional `mcp` extra
  (`pip install "narwhal-seo[mcp]"`) + `narwhal-mcp` console script; the core
  toolkit stays zero-dependency and prints a friendly hint when `mcp` is absent.

## [1.5.0] — 2026-07-01

### Added
- **Scan diffing / regression tracking** (`narwhal diff old.json new.json`): compare
  two saved JSON reports — score delta plus **new / resolved / worsened / improved**
  findings. Deliberately database-free (diff the JSON we already emit): human-readable,
  git-friendly, and directly readable by the agent.
  - Dynamic finding titles (e.g. `Thin content (210 words)`) are normalized so the
    same issue matches run-to-run.
  - `--fail-on-regression` exit code for CI gating (score dropped, or a new
    critical/high finding appeared).
  - Accepts both `scan` and `audit --format json` output; Markdown + JSON output.

## [1.4.0] — 2026-07-01

### Added
- **HTML report export** (`--format html`): a self-contained, styled report —
  inline CSS, an SVG score gauge, a per-area breakdown with score bars, and
  severity-coloured finding cards. No external resources, so it renders offline
  and is easy to share. Available on both `scan.py` and the flagship `audit.py`.
- **PDF export** (`--format pdf`): renders the HTML to PDF via WeasyPrint when it's
  installed, and gracefully falls back to writing HTML (with a clear note) when it
  isn't — no crash, no hard dependency.
- Sample HTML report in [`docs/samples/`](docs/samples/sample-report.html); new
  optional `pdf` extra (`pip install narwhal-seo[pdf]`).

### Changed
- Report output writing is unified through `report.deliver()`, shared by `scan.py`
  and `audit.py`, so all four formats behave consistently.

## [1.3.0] — 2026-07-01

### Added
- **Filler / AI-writing content-quality scorer** (`lib/content_quality.py`, stdlib):
  detects padding/filler phrases, telltale AI-writing patterns, and low lexical
  diversity — surfaced as hard-data findings (with example matches) in the content
  auditor and the `narwhal-content` specialist.

## [1.2.1] — 2026-07-01

### Fixed
- Multi-agent `/narwhal audit` synthesis now uses plain GitHub-flavored Markdown
  (pipe tables + lists) instead of Unicode box-drawing tables, which corrupted in
  terminals.

## [1.2.0] — 2026-07-01

### Added
- **Multi-agent deep audit**: `/narwhal audit` runs the deterministic baseline, then
  fans out ~10 specialist subagents in parallel (`agents/`: technical, content,
  schema, geo, performance, links, duplication, sitemap, sxo, + conditional local)
  and synthesizes an SEO Health Score + prioritized action plan.
- **`/narwhal <action> <site>` command** dispatching audit/scan/crawl/sitemap/llms/schema.
- **Comprehensive `audit` action** combining homepage + site crawl + sitemap.
- **Audit-style report**: executive summary, per-area subscores, quick wins.

### Changed
- Plugin renamed `seo-scan` → **`narwhal`** (install: `narwhal@narwhal`).
- Link checking uses a shorter HEAD timeout + more workers; audit uses lighter
  sub-limits — link-heavy sites went from hanging to ~25s.

## [1.1.0] — 2026-07-01

### Added
- GitHub Actions **CI** (Python 3.8–3.12 + Windows, with/without extras).
- **`--fail-under N`** CI quality gate on `scan` and `crawl`.
- Unified **`narwhal` CLI** + **`uvx`** (git-based, no install, no PyPI).
- **Polite crawler** (robots.txt-aware, `--concurrency`, `--delay`, cached signals).
- **RFC 9309 robots.txt matcher** (`lib/robots.py`).
- **Broken-link checker** (`crawl --check-links`).
- **Sitemap validation** (`narwhal sitemap`): indexes, lastmod, 404 sampling, gzip.
- **`narwhal.toml` config** (weights, thresholds, CLI defaults, ignore rules).
- **`llms.txt` generator** (`narwhal llms`).
- **Readability** (Flesch) + keyword/entity extraction + topical-focus check.
- **Near-duplicate detection** (SimHash) with canonical checks.

## [1.0.0] — 2026-07-01

### Added
- Initial release: four auditors (technical, content/E-E-A-T, schema, GEO/LLMO),
  `scan` / `crawl` / `schema` tools, SSRF-safe fetching, Markdown/JSON reports,
  Claude Code plugin install, and the offline test suite.

[1.3.0]: https://github.com/aindong/narwhal/releases/tag/v1.3.0
[1.2.1]: https://github.com/aindong/narwhal/releases/tag/v1.2.1
[1.2.0]: https://github.com/aindong/narwhal/releases/tag/v1.2.0
[1.1.0]: https://github.com/aindong/narwhal/releases/tag/v1.1.0
[1.0.0]: https://github.com/aindong/narwhal/releases/tag/v1.0.0
