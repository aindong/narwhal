# Narwhal docs

Documentation index for the Narwhal SEO & GEO/LLMO scanning toolkit.

## Planning
- **[STATUS.md](STATUS.md)** — current state & handoff snapshot (architecture,
  what's done, what's next, dev/release workflow).
- **[ROADMAP.md](ROADMAP.md)** — where the project is headed, grouped by priority
  and release milestone, linked to tracking issues.
- **[../CHANGELOG.md](../CHANGELOG.md)** — release history.
- **[Issues](https://github.com/aindong/narwhal/issues)** — detailed tasks and
  acceptance criteria (the source of truth for individual work items).

## Configuration
- **[CONFIG.md](CONFIG.md)** — how to use `narwhal.toml` (weights, thresholds,
  CLI defaults, ignore rules). Template: [`narwhal.example.toml`](../narwhal.example.toml).

## Using the tool
- **[Project README](../README.md)** — what it is, install (Claude Code plugin or
  manual), and quick start.
- **[SKILL.md](../skills/seo-scan/SKILL.md)** — the Claude Code skill entry: when to
  use it, how to run each script, guardrails.
- **[AGENTS.md](../AGENTS.md)** — the same toolkit for Codex / Cursor / OpenCode and
  other agents.

## How the checks work (deep-dive guidance)
The reasoning, thresholds, and *why* behind each auditor:
- **[Technical SEO](../skills/seo-scan/references/technical-seo.md)**
- **[Content & E-E-A-T](../skills/seo-scan/references/content-eeat.md)**
- **[Structured data / schema](../skills/seo-scan/references/schema.md)**
- **[GEO / LLMO](../skills/seo-scan/references/geo-llmo.md)**

## Contributing
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — setup, project layout, design
  principles, and how to add a new check or auditor.
- **[Brand assets](../assets/README.md)** — logo files and usage.
