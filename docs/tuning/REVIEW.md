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
