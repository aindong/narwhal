---
description: Run a Narwhal SEO & GEO/LLMO audit, scan, crawl, or generator on a site
argument-hint: <audit|scan|crawl|sitemap|llms|schema> <site>
---

# Narwhal — SEO & GEO/LLMO

The user ran: `/narwhal $ARGUMENTS`

- **Action:** `$1`
- **Target:** `$2`

## How to run the deterministic tools
Prefer the plugin's local scripts:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/<script>" <args>
```
Fallback (needs `uv`): `uvx --from git+https://github.com/aindong/narwhal narwhal <action> <args>`.
They are local-first, SSRF-safe, and need no API keys. Respect any `narwhal.toml`.

---

## If `$1` is `audit` → run the parallel multi-agent deep audit

This is the flagship. Produce a comprehensive, prioritized SEO + GEO audit by
combining deterministic measurement with specialist reasoning.

**Step 1 — Deterministic baseline (hard data, fast).** Run:
```
python "${CLAUDE_PLUGIN_ROOT}/skills/seo-scan/scripts/audit.py" $2 --format json -o narwhal-audit.json
```
This gives homepage + site-wide + sitemap data, per-area subscores, broken links,
and duplicate clusters. Skim it to detect the **business type** (SaaS, publisher,
e-commerce, local/brick-and-mortar, directory/people-search…).

**Step 2 — Fan out specialists IN PARALLEL.** In a *single message*, spawn these
subagents with the Task tool (pass each the URL `$2` and the path `narwhal-audit.json`):
- **Always:** `narwhal-technical`, `narwhal-content`, `narwhal-schema`,
  `narwhal-geo`, `narwhal-performance`, `narwhal-links`, `narwhal-duplication`,
  `narwhal-sitemap`, `narwhal-sxo`
- **Conditional:** `narwhal-local` — only when Step 1 indicates a local / service-area
  business.

Each returns a domain score + prioritized findings with exact fixes.

**Step 3 — Synthesize one report.** Merge the specialists into:
- **SEO Health Score (0–100)** — reconcile the deterministic scores with the
  specialists' judgment; explain the number in one sentence.
- **Executive summary** — business type, biggest risks, and the 3 highest-leverage moves.
- **Prioritized action plan** — Critical → High → Medium → Low, each with the fix and
  a rough effort tag. Call out fixes that resolve several findings at once.
- **Quick wins** — low-effort, high-impact.
- **Per-area detail** — one concise section per specialist.
Offer to write it to `narwhal-audit-report.md`.

**Formatting (important):** write the report in plain **GitHub-flavored Markdown**
— `#`/`##` headings, `|`-delimited pipe tables, `-` bullet lists, `**bold**`. Do
**NOT** draw Unicode/ASCII box tables (`┌─┬─┐│└┘`) or fixed-width column art: they
corrupt in terminals and when streamed. Keep any table to ≤4 **narrow** columns; if
it would be wide, use a list instead. Produce one clean report — don't paste each
specialist's raw output verbatim.

Guardrails: never fabricate metrics (real Core Web Vitals need CrUX/PageSpeed);
be honest where a claim needs an external tool. Keep the synthesis tight, not a
wall of raw output.

---

## Otherwise → run the matching tool and report back

| `$1` | Run | Then |
|---|---|---|
| `scan` | `scan.py $2` | full single-page audit report |
| `crawl` | `crawl_site.py $2 --check-links` | site-wide (broken links + dupes) |
| `sitemap` | `validate_sitemap.py $2` | validate XML sitemap(s) |
| `llms` | `generate_llms.py $2 -o llms.txt` | generate a starter llms.txt |
| `schema` | `generate_schema.py $2 …` | here `$2` is the schema **Type** (e.g. Article) |

Read the report back **in your own words, leading with the highest-severity fixes** —
summarize, don't paste everything.

Edge cases: if `$1` is empty/unrecognized, treat it as `audit`. If `$2` (the site) is
missing, ask for it. Only add `--allow-private` for local/staging targets.
