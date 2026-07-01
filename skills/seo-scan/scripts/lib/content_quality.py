"""Content-quality heuristics: filler language, AI-writing patterns, density.

Pure, stdlib-only signals that approximate what Google's helpful-content and
Search Quality Rater guidance penalize: hollow padding, generic AI-sounding prose,
and low information density. These are *signals*, not proof — they flag pages worth
a human read, and the content auditor reports them with example matches.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
_SENT = re.compile(r"[.!?]+")

# Padding / low-information phrases (regex fragments, matched case-insensitively).
FILLER = [
    r"in today's (?:fast-paced|digital|modern|competitive|ever-changing) world",
    r"in this day and age",
    r"when it comes to",
    r"at the end of the day",
    r"it (?:is|'s) important to (?:note|remember|understand) that",
    r"needless to say",
    r"as a matter of fact",
    r"the fact of the matter is",
    r"for all intents and purposes",
    r"last but not least",
    r"first and foremost",
    r"each and every",
    r"there is no denying",
    r"without a doubt",
    r"it goes without saying",
    r"at this point in time",
    r"in order to",
]

# Telltale LLM/marketing-generated phrasings.
AI_PATTERNS = [
    r"it(?:'s| is) worth noting",
    r"delv(?:e|ing) into",
    r"in the realm of",
    r"navigat(?:e|ing) the (?:landscape|complexities|world|challenges)",
    r"in the ever-evolving",
    r"a testament to",
    r"plays? a (?:crucial|vital|significant|pivotal|key) role",
    r"in conclusion",
    r"in summary",
    r"unlock(?:ing)? the (?:power|potential|secrets)",
    r"harness(?:ing)? the power",
    r"a (?:myriad|plethora) of",
    r"embark(?:ing)? on (?:a|your|the) journey",
    r"elevate your",
    r"seamless(?:ly)?",
    r"cutting-edge",
    r"game[- ]chang(?:er|ing)",
    r"in the fast-paced world of",
    r"tapestry",
    r"the world of",
    r"foster(?:ing)? a",
    r"underscor(?:e|es|ing)",
]

_FILLER_RE = [re.compile(p, re.I) for p in FILLER]
_AI_RE = [re.compile(p, re.I) for p in AI_PATTERNS]


def _matches(text, patterns):
    """Return {matched_phrase_lower: count} across the compiled patterns."""
    hits = {}
    for rx in patterns:
        for m in rx.finditer(text):
            key = " ".join(m.group(0).lower().split())
            hits[key] = hits.get(key, 0) + 1
    return hits


def analyze(text: str) -> dict:
    text = text or ""
    words = [w.lower() for w in _WORD.findall(text)]
    wc = len(words)
    filler = _matches(text, _FILLER_RE)
    ai = _matches(text, _AI_RE)
    filler_count = sum(filler.values())
    ai_count = sum(ai.values())
    diversity = round(len(set(words)) / wc, 3) if wc else 0.0
    per100 = (lambda n: round(n / (wc / 100), 2) if wc >= 100 else 0.0)
    return {
        "word_count": wc,
        "lexical_diversity": diversity,          # unique/total (type-token ratio)
        "filler_count": filler_count,
        "filler_per_100w": per100(filler_count),
        "filler_examples": _top(filler),
        "ai_pattern_count": ai_count,
        "ai_distinct": len(ai),
        "ai_examples": _top(ai),
    }


def _top(hits, n=5):
    return [k for k, _ in sorted(hits.items(), key=lambda kv: -kv[1])[:n]]
