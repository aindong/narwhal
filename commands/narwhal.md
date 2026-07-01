---
description: Run a Narwhal SEO & GEO/LLMO audit, scan, crawl, or generator on a site
argument-hint: <scan|audit|crawl|sitemap|llms|schema> <site>
---

# Narwhal — SEO & GEO/LLMO

The user ran: `/narwhal $ARGUMENTS`

- **Action:** `$1`
- **Target:** `$2`

Run the matching Narwhal tool on the target, then read the report back to the user
**in your own words, leading with the highest-severity fixes**. Summarize — don't
just paste the whole report.

## How to run the tool

Prefer the plugin's local scripts:

```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/<script>" <args>
```

If that path isn't available, fall back to the published CLI (needs `uv`):

```
uvx --from git+https://github.com/aindong/narwhal narwhal <action> <args>
```

## Dispatch by action (`$1`)

| `$1` | Run |
|---|---|
| `audit` | `audit.py $2` — comprehensive: homepage audit + site crawl + sitemap in one report |
| `scan` | `scan.py $2` — full single-page audit report |
| `crawl` | `crawl_site.py $2 --check-links` — site-wide, with broken links + dupes |
| `sitemap` | `validate_sitemap.py $2` — validate XML sitemap(s) |
| `llms` | `generate_llms.py $2 -o llms.txt` — generate a starter llms.txt |
| `schema` | `generate_schema.py $2 …` — here `$2` is the schema **Type** (e.g. Article) |

Defaults & edge cases:
- If `$1` is empty or unrecognized, treat it as `audit` and use `$ARGUMENTS` as the URL.
- If `$2` (the site URL) is missing, ask the user for it before running.
- Pass through obvious extra options the user included in `$ARGUMENTS`.

## Guardrails
- Local-first and SSRF-safe by default; only add `--allow-private` for local/staging.
- Respect a `narwhal.toml` if the project has one.
- Report what was measured; don't invent metrics the tool doesn't produce
  (e.g. real Core Web Vitals field data).
