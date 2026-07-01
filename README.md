<p align="center">
  <img src="assets/logo-512.png" alt="Narwhal logo" width="220">
</p>

<h1 align="center">Narwhal — SEO & GEO/LLMO scanning skills</h1>

A local-first toolkit that scans a web page or site for **SEO** and **GEO/LLMO**
(visibility in AI answer engines like ChatGPT, Claude, Perplexity, and Google AI
Overviews). It ships as an agent skill so Claude Code — and any agent that reads
`AGENTS.md` (Codex, Cursor, OpenCode, …) — can audit a URL and hand back a
prioritized, fix-first report.

No accounts, no API keys, nothing phones home. It runs on a bare Python install
and gets sharper when optional parsing/rendering libraries are present.

## Why "Narwhal"?

The narwhal is the perfect mascot for a search-and-AI-visibility tool:

- **The tusk is a sensor, not a weapon.** A narwhal's tusk is packed with millions
  of nerve endings that read tiny changes in the water around it. Narwhal the tool
  does the same for a page — it senses the subtle, easy-to-miss signals (meta,
  canonical, schema, passage citability, crawler access) that decide whether you're
  seen.
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
| **Content & E-E-A-T** | thin-content detection, readability, author/date signals, Open Graph / Twitter cards |
| **Structured data** | JSON-LD detection, required/recommended property validation, deprecated rich-result types, JSON-LD generation |
| **GEO / LLMO** | question-based headings, citable passage structure, evidence density, direct-answer intros, `llms.txt`, and **AI-crawler access** (GPTBot, ClaudeBot, PerplexityBot, Google-Extended…) |

## Quick start

```bash
# 1. (optional) install extras for better parsing + JS rendering
pip install -r skills/seo-scan/requirements.txt

# 2. audit a single page
python skills/seo-scan/scripts/scan.py https://example.com/page

# 3. audit a whole site (rolls up the issues that recur most)
python skills/seo-scan/scripts/crawl_site.py https://example.com --max-pages 25

# 4. generate valid schema.org JSON-LD
python skills/seo-scan/scripts/generate_schema.py Article \
  --field headline="How GEO works" --field author="Jane Doe"
```

Every report includes a 0–100 health score and findings grouped by severity, each
with what was observed and a concrete fix.

### Useful flags (`scan.py`)
- `--render` — render JavaScript via Playwright (for SPAs). Needs
  `python -m playwright install chromium`.
- `--format json [-o file]` — machine-readable output.
- `--only technical,content,schema,geo` — run a subset of auditors.
- `--allow-private` — permit localhost/staging targets (off by default; see below).

## Using it as an agent skill

- **Claude Code / Claude:** the skill lives at
  [`skills/seo-scan/SKILL.md`](skills/seo-scan/SKILL.md). Copy or symlink
  `skills/seo-scan/` into `~/.claude/skills/` (user-wide) or `.claude/skills/`
  (per project), or run the installer below. Then just ask Claude to "run an SEO
  and GEO audit on <url>".
- **Codex / Cursor / OpenCode / others:** the root
  [`AGENTS.md`](AGENTS.md) documents the same tools in the format those agents
  read. Point the agent at this repo and ask for an audit.

### Install into Claude Code
```bash
# macOS / Linux
bash install.sh
```
```powershell
# Windows
./install.ps1
```

## Design principles

- **Local-only by default.** No external services are called. Optional API
  integrations (PageSpeed/CrUX, SERP data) are intentionally *not* on the default
  path — the scan is honest about what it can and can't measure locally.
- **Graceful degradation.** Works with only the Python standard library; uses
  `requests`, `beautifulsoup4`/`lxml`, `trafilatura`, and `playwright`
  automatically when installed.
- **SSRF-safe.** URLs that resolve to private, loopback, or link-local addresses
  are blocked unless you explicitly pass `--allow-private`.
- **Fix-first output.** Reports lead with the highest-severity, highest-leverage
  changes — not a data dump.

## Reference guides

Deep-dive reasoning behind each check lives in
[`skills/seo-scan/references/`](skills/seo-scan/references/):
`technical-seo.md`, `content-eeat.md`, `schema.md`, `geo-llmo.md`.

## Requirements

Python 3.8+. Optional extras in
[`skills/seo-scan/requirements.txt`](skills/seo-scan/requirements.txt).

## License

MIT — see [LICENSE](LICENSE).
