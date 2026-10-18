"""Inspectable English-oriented formula inputs, not comprehension or citability."""
import math
import unicodedata

from . import text as textlib

LIMITS = ('English-oriented heuristic formula estimates, not measured reader comprehension, '
          'a verified school grade, content quality or ranking/AI-citation impact. ASCII-pattern '
          'matches are not multilingual words; punctuation fragments are not verified sentences '
          'and vowel-group estimates are not validated syllables. Short samples, headings, '
          'abbreviations, code and specialist vocabulary can distort results. Review actual '
          'audience and text; no universal formula target or minimum word count is established.')
_REASONS = {
    'declared_non_english': 'declared language is outside this English-oriented formula review',
    'non_ascii_letters_or_marks': 'selected text contains non-ASCII letters or combining marks',
    'link_hub': 'page has a link-hub hint rather than a prose sample',
    'no_formula_inputs': 'no usable ASCII-pattern matches or punctuation fragments',
}


def observe(text, *, language='', basis='visible text', hub=False):
    """Keep exact historical inputs; withhold interpretation of unsupported scope."""
    text = text or ''
    lang = (language or '').strip().lower()
    basis = str(basis)
    inputs = textlib.readability_measures(text)
    outside = (0 if text.isascii() else
               sum(not c.isascii() and unicodedata.category(c)[0] in 'LM' for c in text))
    reasons = []
    if lang and lang != 'en' and not lang.startswith('en-'):
        reasons.append('declared_non_english')
    if outside:
        reasons.append('non_ascii_letters_or_marks')
    if hub:
        reasons.append('link_hub')
    if inputs['flesch_reading_ease'] is None:
        reasons.append('no_formula_inputs')
    if reasons:
        inputs.update(flesch_reading_ease=None, flesch_kincaid_grade=None)
    return {'version': 1, 'basis': 'selected_text_ascii_english_formula',
            'word_pattern': textlib._WORD.pattern, 'sentence_pattern': textlib._SENT.pattern,
            'syllable_basis': 'vowel_groups_with_silent_e_adjustment',
            'source_basis': basis[:160], 'source_basis_clipped': len(basis) > 160,
            'declared_language': lang[:80], 'declared_language_clipped': len(lang) > 80,
            'text_characters': len(text), 'non_ascii_letters_or_marks': outside,
            'link_hub_hint': bool(hub), **inputs,
            'formula_status': 'uninterpreted' if reasons else 'computed',
            'uninterpreted_reasons': reasons, 'limits': LIMITS}


def recorded(value):
    """Check supported receipt shape/coherence, not source authenticity."""
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('basis') != 'selected_text_ascii_english_formula'
            or value.get('word_pattern') != textlib._WORD.pattern
            or value.get('sentence_pattern') != textlib._SENT.pattern
            or value.get('syllable_basis') != 'vowel_groups_with_silent_e_adjustment'):
        return None
    for key, bound in (('source_basis', 160), ('declared_language', 80)):
        if (type(value.get(key)) is not str or len(value[key]) > bound
                or key == 'source_basis' and not value[key].strip()
                or type(value.get(key + '_clipped')) is not bool
                or value[key + '_clipped'] and len(value[key]) != bound):
            return None
    keys = ('text_characters', 'non_ascii_letters_or_marks', 'ascii_pattern_matches',
            'sentence_fragments', 'estimated_syllables')
    if any(type(value.get(k)) is not int or not 0 <= value[k] < 2**63 for k in keys):
        return None
    characters, outside, words, fragments, syllables = (value[k] for k in keys)
    if (max(outside, words, fragments, syllables) > characters
            or syllables < words or not words and syllables != 0
            or type(value.get('link_hub_hint')) is not bool):
        return None
    reasons = value.get('uninterpreted_reasons')
    if (not isinstance(reasons, list) or len(reasons) > len(_REASONS)
            or any(type(r) is not str or r not in _REASONS for r in reasons)
            or len(set(reasons)) != len(reasons)
            or ('declared_non_english' in reasons) != bool(value['declared_language']
                and value['declared_language'] != 'en' and not value['declared_language'].startswith('en-'))
            or ('non_ascii_letters_or_marks' in reasons) != bool(outside)
            or ('link_hub' in reasons) != value['link_hub_hint']
            or ('no_formula_inputs' in reasons) != (not words or not fragments)):
        return None
    if value.get('formula_status') == 'uninterpreted':
        return value if reasons and all(value.get(k) is None for k in ('flesch_reading_ease', 'flesch_kincaid_grade')) else None
    if value.get('formula_status') != 'computed' or reasons or not words or not fragments:
        return None
    expected = {'flesch_reading_ease': round(206.835 - 1.015 * (words/fragments) - 84.6 * (syllables/words), 1),
                'flesch_kincaid_grade': round(0.39 * (words/fragments) + 11.8 * (syllables/words) - 15.59, 1)}
    for key, number in expected.items():
        if type(value.get(key)) not in (int, float) or value[key] != number or not math.isfinite(value[key]):
            return None
    return value


def note(meta):
    """Render validated counts with static limits, never untrusted source strings."""
    value = recorded(meta.get('readability')) if isinstance(meta, dict) else None
    if value is None:
        return None
    observed = (f"Formula inputs from selected extracted text: {value['ascii_pattern_matches']} ASCII-pattern matches; "
                f"{value['sentence_fragments']} punctuation-split fragments; {value['estimated_syllables']} "
                'estimated vowel-group syllables. ')
    if value['formula_status'] == 'computed':
        observed += (f"Flesch reading ease estimate {value['flesch_reading_ease']}; "
                     f"Flesch–Kincaid grade formula estimate {value['flesch_kincaid_grade']}. ")
    else:
        observed += 'Formula interpretation withheld: ' + '; '.join(_REASONS[r] for r in value['uninterpreted_reasons']) + '. '
    return observed + LIMITS + ' Extraction/language scope is recorded in JSON; no raw text is newly retained.'
