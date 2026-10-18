"""Exact lexical heading counts and conditional, non-semantic review guidance."""
import math

LIMITS = ('Heading cues match configured English first tokens or a terminal ASCII "?". '
          'They do not establish real user queries, query relevance or engine matching. '
          'The one-in-five review threshold is an unvalidated heuristic, not an engine '
          'requirement. Keep useful descriptive headings; questions are optional when '
          'helpful. Ranking and citation impact are not measured.')
BASIS = 'english_first_token_or_terminal_ascii_question_mark'
REVIEW_LABEL = 'Question-heading cue difference (review)'


def _count(value):
    return type(value) is int and 0 <= value < 2 ** 63


def _ratio(value):
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def observe(headings, starters):
    """Preserve the historical match rule over nonempty parsed level>=2 headings."""
    matched = examined = 0
    for level, text in headings:
        if level >= 2 and text:
            examined += 1
            matched += bool((text.lower().split() or [''])[0] in starters or text.rstrip().endswith('?'))
    return {'version': 1, 'basis': BASIS, 'matched': matched, 'examined': examined,
            'interpretation': 'editorial_review_only', 'limits': LIMITS}


def fraction(value):
    """The legacy floating fraction, for its preserved rounded JSON alias only."""
    return value['matched'] / value['examined'] if value['examined'] else 0.0


def recorded(facts):
    """Recognize explicit exact counts; a rounded legacy ratio is not a receipt."""
    value = facts.get('question_cues') if isinstance(facts, dict) else None
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('basis') != BASIS
            or value.get('interpretation') != 'editorial_review_only'
            or not _count(value.get('matched')) or not _count(value.get('examined'))
            or value['matched'] > value['examined']):
        return None
    if 'question_ratio' in facts and (not _ratio(facts['question_ratio'])
                                     or facts['question_ratio'] != round(fraction(value), 2)):
        return None
    return value


def at_threshold(facts):
    """Use exact integers, not a rounded float; no headings/basis is unassessed."""
    value = recorded(facts)
    if value is None or not value['examined']:
        return None
    return value['matched'] * 5 >= value['examined']


def review_difference(you, rivals):
    """Optional comparison review, never a measured query/intent requirement."""
    return ((you is None or at_threshold(you) is False)
            and any(at_threshold(facts) is True for facts in rivals))


def cell(facts):
    value = recorded(facts)
    if value is not None:
        return (f"{value['matched']}/{value['examined']} heading-pattern matches"
                + (' (no eligible headings)' if not value['examined'] else ''))
    legacy = facts.get('question_ratio') if isinstance(facts, dict) else None
    return (f'{legacy} rounded legacy ratio (counts/basis unrecorded)' if _ratio(legacy) else 'Unrecorded')


def summary(you, rivals):
    """Only typed counts/static limits, not supplied labels/URLs/receipt text.

    The 100-page read cap bounds this note only, not total input/CPU/heap.
    """
    lines = [LIMITS]
    if you is not None:
        lines.append('Your page: ' + cell(you) + '.')
    if not isinstance(rivals, list) or len(rivals) > 100:
        return lines + ['Compared-page heading counts/basis are unrecorded or unsupported.']
    lines += [f'Compared page {i + 1}: {cell(facts)}.' for i, facts in enumerate(rivals)]
    return lines
