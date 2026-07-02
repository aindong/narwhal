# Round 1 results — per-site before/after (v1.18.0 → v1.19.0)

Raw scan JSONs are in [`before/`](before/) and [`after/`](after/); both were
produced by `scan.py <url> --format json` on 2026-07-02. Sites are public
pages chosen for *diversity of page type*; every score change below comes from
removing findings that were **wrong**, not from loosening checks.

| Site | Before | After |
|:--|--:|--:|
| allbirds.com (e-commerce) | 79 | **83** |
| news.ycombinator.com (link-hub) | 52 | **66** |
| jvns.ca (personal blog) | 62 | **79** |
| docs.python.org/3 (docs index) | 75 | **86** |
| stripe.com (SaaS) | 89 | **90** |
| theverge.com (news publisher) | 71 | **80** |
| vercel.com (SaaS) | 83 | **89** |
| en.wikipedia.org/wiki/Narwhal (wiki) | 74 | **79** |

## allbirds.com (e-commerce) — 79 → 83
- ❌ removed: **medium** · No visible author/byline
- ❌ removed: **medium** · Few question-based headings
- ✅ now: **low** · No visible date signal
- ✅ now: **low** · Few question-based headings

## news.ycombinator.com (link-hub) — 52 → 66
- ❌ removed: **low** · No visible date signal
- ❌ removed: **high** · Thin content
- ❌ removed: **medium** · No statistics or citations
- ❌ removed: **high** · Title is very short
- ✅ now: **low** · Content is on the short side
- ✅ now: **low** · Homepage title is just the brand

## jvns.ca (personal blog) — 62 → 79
- ❌ removed: **low** · Content is fairly hard to read
- ❌ removed: **medium** · Few self-contained, citable passages
- ❌ removed: **medium** · No statistics or citations
- ❌ removed: **high** · No H1 heading
- ❌ removed: **high** · Title is very short
- ✅ now: **low** · Heading levels skip a level
- ✅ now: **low** · Homepage title is just the brand

## docs.python.org/3 (docs index) — 75 → 86
- ❌ removed: **low** · Content is fairly hard to read
- ❌ removed: **medium** · No visible author/byline
- ❌ removed: **high** · Thin content
- ❌ removed: **medium** · Few question-based headings
- ❌ removed: **medium** · No statistics or citations
- ✅ now: **low** · Content is on the short side
- ✅ now: **low** · No visible date signal
- ✅ now: **low** · Few question-based headings
- ✅ now: **low** · No direct answer up top
- ✅ now: **low** · No statistics or citations

## stripe.com (SaaS) — 89 → 90
- ❌ removed: **medium** · Few question-based headings
- ✅ now: **low** · Repetitive vocabulary
- ✅ now: **low** · Few question-based headings

## theverge.com (news publisher) — 71 → 80
- ❌ removed: **medium** · No visible author/byline
- ❌ removed: **medium** · Few question-based headings
- ❌ removed: **high** · Title is very short
- ✅ now: **low** · Content is fairly hard to read
- ✅ now: **low** · Few question-based headings
- ✅ now: **low** · Homepage title is just the brand

## vercel.com (SaaS) — 83 → 89
- ❌ removed: **high** · Thin content
- ❌ removed: **medium** · Few question-based headings
- ✅ now: **low** · Content is on the short side
- ✅ now: **low** · Few question-based headings
- ✅ now: **low** · Article-like page without Article schema

## en.wikipedia.org/wiki/Narwhal (wiki) — 74 → 79
- ❌ removed: **medium** · No visible author/byline
- ❌ removed: **low** · Repetitive vocabulary
- ❌ removed: **medium** · Few question-based headings
- ✅ now: **low** · Content is fairly hard to read
- ✅ now: **low** · Few question-based headings

