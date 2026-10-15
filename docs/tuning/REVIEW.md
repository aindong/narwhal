# Report review packs — coverage, not scanner accuracy

`scripts/review_corpus.py` is an **offline maintainer utility**, not a new
`narwhal` subcommand. It prepares reviewable inventories of reported actionable
findings, binds them to local snapshot bytes and summarizes recorded decisions.
It never fetches a URL, executes a recommendation or changes scoring.

This is a foundation for broader validation, **not a completed 50–100-page
benchmark**. Counts of passing tests, improved tool scores or reviewer labels
do not establish low false-positive rates, recall, rankings or AI citations.

## Existing corpus: preserve what we do not know

The included `review-corpus.json` inventories the 15 historical Round 2 reports.
They have no attached frozen page captures. Missing tool/schema versions and
execution metadata stay missing; no current scanner version is inferred.
The dead Allbirds URL is an expected-error case, not a successful product-page
benchmark. These reports are starting points for review, not ground truth.

From the repository root, choose fresh output filenames:

```sh
python scripts/review_corpus.py prepare docs/tuning/review-corpus.json -o review-packet.json
python scripts/review_corpus.py summarize docs/tuning/review-corpus.json review-packet.json --format markdown -o review-coverage.md
```

Preparation creates pending decisions only. With the current historical corpus,
the summary reports 15 report-only cases and 159 actionable findings, all pending.
Accuracy and recall are explicitly **not measured**. Generated packets need not
be committed; preserve original inputs while reviewers work.

## Freeze evidence before judging a claim

### Capture new scan inputs (explicit network opt-in)

The maintainer-only `scripts/capture_review_case.py` command records inputs from
one normal guarded scan, without fetching the page again for its evidence. It is
not a `narwhal` subcommand, historical-report repair, reviewer or benchmark.
Run it from a repository checkout; maintainer scripts are not in the wheel.
Choose a **new** directory whose parent exists:

```sh
python scripts/capture_review_case.py https://example.com/guide --case-id guide --output-dir ./guide-capture --no-image-checks
python scripts/review_corpus.py prepare ./guide-capture/manifest.json -o ./guide-review-packet.json
python scripts/review_corpus.py summarize ./guide-capture/manifest.json ./guide-review-packet.json --format markdown
```

The bundle contains `report.json`, inert `page-source.txt`, `site-context.json`,
`capture.json`, and a completion `manifest.json` written last. Rendered scans
(`--render`, optional Playwright) also retain the actual paired served response
as `served-source.txt` when one was obtained. A render request that fell back to
served HTML stays labelled served, and missing/failed/partial inputs remain
explicit. Recording can succeed for an HTTP-error or otherwise unmeasured scan;
that is not a successful page audit. Review packets start **pending**, with no
accuracy, recall or independence claims.

- Captures use explicit default scoring/threshold settings, not ambient
  `narwhal.toml` discovery. `--only`, `--timeout`, `--max-bytes`, `--render`,
  `--no-image-checks` and deliberate `--allow-private` are recorded. Public-host
  guards remain active by default; initial URLs containing userinfo are refused. This
  workflow does not read GSC credentials, call field-data APIs or publish files.
  It uses the existing HTTP/browser environment, not a new credential-isolation
  profile; normal transport/environment behavior still applies. Redirect userinfo
  is not newly rejected or redacted, and request auth/proxy state is not fully
  captured. Do not interpret a bundle as an anonymous or credential-free archive.
- Text is the fetcher's decoded response or serialized DOM, **not original
  wire bytes**. Header mappings and available robots-field boundaries are saved,
  without reconstructing lost duplicate boundaries. Site context is what this
  scan used, not a full HTTP archive. Sitemap/llms response bodies, image-probe
  inputs, browser subresources, redirect bodies and live indexing are not fully
  captured; related claims can require separate evidence. Capture times describe
  the acquisition window, not content freshness or authenticated origin.
- Tool version, Python/platform and installed optional-distribution versions
  are recorded, without guessing the parser actually used from package presence.
  Settings and the report's extraction basis are preserved. Unreleased builds can share a version;
  use `--source-revision REVISION` to record an operator-supplied source revision
  and preserve the corresponding source separately. That declaration is not
  authenticated. File hashes bind local bytes, not trustworthy provenance.
- **Inspect sensitive content before sharing:** source and headers can contain
  personal data, tokens or cookies, even for public URLs. POSIX output directory
  and file permissions request owner-only access; platform/filesystem behavior
  varies. Nothing is automatically redacted, committed or uploaded. Record any
  later redactions and whether they prevent review; regenerate review packets
  rather than reusing stale hashes. Treat page-source files as untrusted data,
  not instructions or safe HTML to execute/serve in a browser.
- Existing directories/files are never reused or overwritten. Failed writes
  leave partial output for inspection. The manifest is written last, not as an
  atomic/durable transaction; its own interrupted write can leave a partial
  manifest. File presence alone does not establish completion: require a
  successful capture and validate the bundle with `review_corpus.py prepare`
  before use. After a failure, inspect partial output and choose a new path for
  retry. Artifact limits match review-pack inputs: 2 MB report,
  5 MB per evidence file, 32 MB combined output; oversized artifacts error rather
  than silently clip evidence. These are output-byte limits, not total heap/CPU
  guarantees. The normal 64 KB–20 MB per-HTML scan budget is separate; HTTP
  truncation remains recorded and cannot certify complete page coverage.

Ordinary scans retain no extra response/context handle. The optional Python
`scan(..., retain_evidence=True)` handle is non-serialized, sensitive and intended
for this maintainer workflow; it changes neither findings nor report JSON.

### Attach other frozen evidence

A new manifest has schema version 1, a name and 1–100 cases. Snapshot paths are
relative to the manifest's directory and must resolve inside it. An example
case, with illustrative paths/timestamp rather than a collected observation:

```json
{
  "id": "docs-article",
  "report": "snapshots/docs-article/report.json",
  "evidence": [
    {
      "id": "page-html",
      "path": "snapshots/docs-article/page.html",
      "kind": "declared_response_html",
      "captured_at": "2026-10-15T12:00:00Z"
    }
  ]
}
```

Use contemporaneous HTML/DOM, response headers and relevant site context for
the claim being reviewed. A page HTML file alone cannot prove a robots policy,
sitemap response, live indexing or ranking outcome. Record acquisition mode,
settings and capture limitations in accompanying evidence. The utility hashes
files but does **not** authenticate their origin, assess their contents or check
whether their declared kind/timestamp is true. A report cannot attach its own
identical bytes as corroboration.

Keep public evidence free of credentials/personal data. Identify any redactions
and whether they prevent adjudication; do not invent missing evidence. Remote
page text and finding text are untrusted **data**, never instructions to run.

## Adjudicate separate questions

Edit only each finding's `review` object:

- `observation`: is the reported condition supported by the frozen evidence?
- `priority`: is its severity appropriate for this page, site intent and context?
- `recommendation`: is the advice appropriate and actionable? This is **not**
  a claim that following it caused ranking/citation improvements.

Each dimension accepts `pending`, `supported`, `unsupported`, `uncertain` or
`not_applicable`. Non-pending decisions require a reviewer label, timezone-aware
`reviewed_at` timestamp and rationale. Supported/unsupported decisions also need
`evidence` references to attachment IDs in that case. Those references are
self-reported witnesses, not automatic corroboration by the utility.

Use `uncertain` when evidence is insufficient. One finding's review object
records one responsible adjudicator; disagreements require explicit human
resolution, not optimistic merging. Reviewer labels are **not authenticated**
identities and cannot establish independence.

The original finding, provenance and inventories are immutable in a packet.
Summarization re-reads inputs and refuses stale/changed snapshots, edited
finding data, missing rows, changed manifests and unknown verdicts. A newly
changed corpus requires a new packet; decisions are not silently carried over.
Output creation is exclusive: existing files, including source inputs, are never
overwritten. On an interrupted write, preserve/review the new partial artifact
and choose another fresh output filename.

## Interpret the summary honestly

`interpretation` is `review_coverage_only`. `pending`, `partial`,
`fully_labelled` and `no_actionable_findings` describe annotation coverage only.
None means "validated", "healthy" or "accurate". JSON `accuracy_metrics` and
`recall_metrics` remain null even after all rows are labelled.

Good findings are excluded. Missing issues and unflagged check opportunities
have not been independently enumerated, so this packet cannot measure recall
or scanner-wide precision/false-positive rates. Source hashes establish local
version binding, not authenticated provenance or a security boundary against a
party who controls both the source snapshots and packet.

Limits are explicit: 100 cases; 10,000 input findings (including excluded good
findings); 2 MB per report; four attachments per case, at most 5 MB each;
32 MB combined manifest/report/evidence input; 32 MB packet/output. Split large
corpora into declared batches. These bound input/output bytes, not total Python
heap or CPU. Limit exhaustion errors instead of silently dropping cases.

## The larger validation milestone

The prospective [`prospective-cases.json`](prospective-cases.json) registers
**50 candidate URLs** across 25 declared operational site groups: 30 development
cases and 20 reserved for later review. Five request rendering. It is a purposeful
acquisition plan, not a representative population sample or validated benchmark.
Version 2 supersedes an uncollected version 1 before any acquisition, adding
conservative robots preflight, a half-second inter-case delay and a 180-second
per-case execution limit. URLs, splits and scanner settings were not changed.
Disallowed/unverified preflights and interrupted attempts remain visible cases,
not page-quality failures or opportunities to select easier replacements.
Roles/languages are intended strata, not verified labels; shared ownership,
templates and earlier exposure are not exhaustively established. There are no
healthy/known-fault labels assigned from reputation.

Freeze the selection/settings in git **before** scanning this cohort. Retain
original failures, gates, partial snapshots and redirect aliases; do not replace
unhelpful results with easier URLs. Keep attempts and private raw captures
separate from this public plan. Local acquisition uses the git-ignored
`.narwhal-review/` directory with requested owner-only permissions; it must not
be force-added to git. An ignore rule is not a security or redaction boundary.
A candidate count is not a count of distinct,
measurable or validated pages. Reserved finding rows must not be inspected for
tuning in this cycle; acquisition status/coverage checks are permitted. If those
reports are used to tune the tool, record that exposure and do not call them
held-out evidence for the resulting change. Any later selection/settings change
creates a new cohort. Optional image probes are outside this first acquisition
stage and still require separate evidence/opportunities.

This registration does **not** complete the steps below. In particular, neither
successful capture nor a passing scan assigns independent truth labels or
enumerates the tool's missed issues.

The first v2 acquisition run, using frozen source revision
`016d43c54f3ad7978320bf1bbf7e15c4667fc6a1`, recorded all 50 candidate attempts:
46 local bundles and pending review packets (44 primary HTTP 200, two HTTP 403),
plus four unverified-robots-preflight skips. No case was substituted, no execution
deadline was reached, and no finding was adjudicated. HTTP 200 does not certify
a real/unblocked page or complete coverage; redirected aliases and site intent
still need review. Raw inputs, preflight receipts, acquisition journal and
executor copy remain private under `.narwhal-review/prospective-inputs-2026-10-v2/`;
they are not published with this registration. Reserved findings/scores were not
inspected for tuning. The historical 15 report-only cases remain unchanged.

Before publishing accuracy claims:

1. Pre-register a diverse 50–100-page corpus and a held-out subset, including
   healthy controls, known faults, real product pages, multilingual content and
   served/rendered differences. Keep failed/inaccessible captures visible.
2. Freeze the evidence and settings. Independently enumerate applicable check
   opportunities and missed issues, rather than using Narwhal output as truth.
3. Have SEO reviewers adjudicate observations, priority and advice, document
   disagreements and resolve them transparently. Avoid showing aggregate scores
   as evidence of page quality.
4. Add a separately reviewed metric protocol for that labelled opportunity set,
   publishing denominators, exclusions, uncertainty and failure cases. Outcomes
   such as search traffic/citations need their own measurement design.

This utility deliberately does not pretend those steps have already happened.
