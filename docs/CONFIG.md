# Configuring Narwhal (`narwhal.toml`)

Narwhal runs great with zero configuration. When you want to standardize scans
across a team or CI, drop a `narwhal.toml` at your project root to tune scoring,
thresholds, defaults, and which findings you care about.

## Quick start

```bash
# copy the fully-commented example and edit it
cp narwhal.example.toml narwhal.toml
```

The tools **auto-discover** `narwhal.toml` by walking up from the current
directory, so a single file at the repo root applies to every scan run there.

**Precedence** (highest wins):

```
CLI flag   >   narwhal.toml   >   built-in default
```

So `--fail-under 90` always overrides a config value, and a config value always
overrides the built-in default.

### Pointing at a specific file / disabling
- `--config path/to/narwhal.toml` — use an explicit file.
- `--no-config` — ignore any `narwhal.toml` for this run.

### Requirements
Parsing uses stdlib `tomllib` (Python 3.11+). On 3.8–3.10 install `tomli`
(`pip install tomli`) to enable config; otherwise the file is silently ignored
(config is a convenience, never required).

## Sections

### Per-scan ownership (Python API)

Each scan owns a copy of built-in scoring weights, thresholds and ignore rules.
Caller-provided `ctx["thresholds"]` is copied at entry; thresholds returned by
context gathering are copied before later rendering I/O or auditors run. Updating
the original Config affects the next scan, not a scan already using its snapshot.
Completed reports keep their original scoring and ignore policy.

Crawls and comprehensive audits capture the built-in rule policy for the whole
operation, before context/page I/O. Crawl-level gathered threshold overrides are
owned before discovery and worker scans. An audit captures its sitemap sample
budget at entry (calling any custom default resolver once). Caller updates affect
future operations rather than later pages within an active operation. The sample
budget stays fixed; remote content and sitemap data do not. This is rule-input
consistency, not a snapshot of the remote site or a guarantee of identical samples.

Competitor comparisons also capture supported built-in rules once, before scanning
the first URL. A caller update during one page fetch (even a failed competitor)
cannot change later pages' scoring or suppression. Future comparisons pick up
caller changes; each page still gathers its own site context, and custom policies
remain live and unverified. This does not guarantee identical remote content,
page kinds, site context or extraction across compared pages.

Content briefs capture the same supported built-in rules before their first page
scan, including topic mode without an own-page URL. Caller updates during an own
page or competitor fetch cannot change later pages' scoring or suppression;
future briefs see the updates. Custom policies remain live and unverified.
Remote content, per-site context and optional Search Console data are not frozen.

Do not mutate inputs concurrently while the snapshot itself is being captured;
capture is not a multi-field atomic transaction. Custom policies, custom values
and unsupported deep shapes are not rewritten or copied through user hooks, and
do not claim verified rule-configuration provenance. Fingerprints are consistency
diagnostics, not authenticated attestations of report contents.

### `[weights]` — scoring
Penalty subtracted from the 0–100 health score per finding of each severity.
Raise a value to make that severity hurt more.

```toml
[weights]
critical = 12
high     = 6
medium   = 3
low      = 1
```

### `[thresholds]` — check tuning
The numbers behind individual checks.

| Key | Default | Meaning |
|---|--:|---|
| `title_min` | 15 | below → "title very short" |
| `title_max` | 65 | above → "title may be truncated" |
| `meta_desc_min` | 70 | below → "meta description short" |
| `meta_desc_max` | 165 | above → "meta description truncated" |
| `thin_content` | 300 | lower bound for contextual ASCII-token review, not a word-count/SEO target |
| `short_content` | 600 | upper bound for the same review; language/character coverage can leave it uninterpreted |
| `passage_min` | 40 | GEO synthetic sentence-group lower bound (ASCII-word matches; not an engine requirement) |
| `passage_max` | 120 | GEO synthetic sentence-group upper bound (ASCII-word matches; not a citability measurement) |

```toml
[thresholds]
thin_content = 250
title_max    = 60
```

### `[defaults]` — CLI flag defaults
Used when the corresponding flag isn't passed.

| Key | Default | Applies to |
|---|--:|---|
| `timeout` | 20 | all tools |
| `fail_under` | 0 | `scan`, `crawl` (0 disables the gate) |
| `concurrency` | 4 | `crawl`, `audit` (positive integer) |
| `max_pages` | 15 | `crawl`, `audit` (positive integer) |
| `max_links` | 200 | `crawl --check-links` |
| `delay` | 0.0 | `crawl`: finite, nonnegative seconds between parallel page-scan starts; sequential post-scan pause |
| `sample` | 10 | `sitemap` |
| `max_sitemaps` | 50 | `sitemap` |
| `dup_threshold` | 90.0 | `crawl` (near-duplicate % similarity) |

```toml
[defaults]
fail_under  = 80     # CI gate: fail below 80 unless --fail-under overrides
concurrency = 8
```

### `[ignore]` — suppress findings
Silence findings you've decided are acceptable. Suppressed findings are removed
entirely (they don't affect the score).

- `categories` — drop whole auditors: `technical`, `content`, `schema`, `geo`.
- `titles` — drop any finding whose title **contains** one of these substrings
  (case-insensitive).

```toml
[ignore]
categories = ["geo"]                       # hide all GEO/LLMO findings
titles     = ["Open Graph", "Twitter/X"]   # hide social-preview nags
```

## Example: a CI-focused config

```toml
[defaults]
fail_under = 85          # break the build below 85

[ignore]
titles = ["No llms.txt"] # we've decided llms.txt isn't a priority

[thresholds]
thin_content = 250       # our docs pages are intentionally concise
```

Run in CI:

```bash
narwhal scan https://staging.example.com/page   # uses fail_under=85 from config
# override for a one-off stricter check:
narwhal scan https://staging.example.com/page --fail-under 95
```

See [`narwhal.example.toml`](../narwhal.example.toml) for a complete, commented
template.
