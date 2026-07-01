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
| `thin_content` | 300 | below → "thin content" |
| `short_content` | 600 | thin…this → "on the short side" |
| `passage_min` | 40 | GEO citable-passage lower bound (words) |
| `passage_max` | 120 | GEO citable-passage upper bound (words) |

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
| `concurrency` | 4 | `crawl` |
| `max_pages` | 15 | `crawl` |
| `max_links` | 200 | `crawl --check-links` |
| `delay` | 0.0 | `crawl` |
| `sample` | 10 | `sitemap` |
| `max_sitemaps` | 50 | `sitemap` |

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
