"""Literal extracted-text counts, not multilingual word or content-depth analysis."""
from decimal import Decimal
from fractions import Fraction
import math
import re
import unicodedata

# Preserve the historical content auditor's measurement for compatibility.
# Single-letter words and non-ASCII letters are not counted by this pattern.
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z'-]+")
LIMITS = ('ASCII-pattern matches are not universal word counts or a measure of '
          'content depth, usefulness, ranking or AI citations. Configured bounds '
          'are editorial defaults, not engine requirements.')
_REASONS = {
    'declared_non_english': 'declared language is outside this English-oriented review',
    'non_ascii_letters_or_marks': 'extracted text contains non-ASCII letters or combining marks',
}


def _bound(value):
    """Record numeric bounds without rounding or invoking custom conversions."""
    if type(value) is int:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else {'kind': 'nonfinite_float', 'value': str(value)}
    if type(value) is Decimal:
        return {'kind': 'decimal', 'value': str(value)}
    if type(value) is Fraction:
        return {'kind': 'fraction', 'value': str(value)}
    return {'kind': 'unrecorded_numeric_type'}


def observe(text, *, language='', basis='visible text', thresholds=None):
    """Count the selected text and conservatively scope its legacy threshold check.

    No language is inferred and no dictionary/Unicode word segmentation runs.
    Non-English declarations or non-ASCII letters/marks leave threshold review
    uninterpreted rather than claiming that excluded text contains zero words.
    """
    text = text or ''
    lang = (language or '').strip().lower()
    basis = str(basis)
    thresholds = thresholds or {}
    lower, upper = thresholds.get('thin_content', 300), thresholds.get('short_content', 600)
    count = len(WORD_PATTERN.findall(text))
    outside = (0 if text.isascii() else
               sum(not ch.isascii() and unicodedata.category(ch)[0] in 'LM' for ch in text))
    reasons = []
    if lang and lang != 'en' and not lang.startswith('en-'):
        reasons.append('declared_non_english')
    if outside:
        reasons.append('non_ascii_letters_or_marks')
    # Preserve the historical comparison order and programmatic numeric types.
    status = ('uninterpreted' if reasons else 'below_lower' if count < lower else
              'below_upper' if count < upper else 'no_below_range_match')
    return {'version': 1, 'basis': 'selected_extracted_text',
            'source_basis': basis[:160], 'source_basis_clipped': len(basis) > 160,
            'declared_language': lang[:80], 'declared_language_clipped': len(lang) > 80,
            'text_characters': len(text), 'ascii_pattern_matches': count,
            'non_ascii_letters_or_marks': outside, 'pattern': WORD_PATTERN.pattern,
            'word_segmentation': 'not_performed', 'threshold_status': status,
            'uninterpreted_reasons': reasons,
            'bounds': {'thin_content': _bound(lower), 'short_content': _bound(upper)},
            'limits': LIMITS}


def note(meta):
    """Render recognized count receipts without trusting arbitrary source strings."""
    value = meta.get('content_length') if isinstance(meta, dict) else None
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('basis') != 'selected_extracted_text'
            or value.get('pattern') != WORD_PATTERN.pattern
            or value.get('word_segmentation') != 'not_performed'):
        return None
    counts = [value.get(key) for key in ('text_characters', 'ascii_pattern_matches',
                                       'non_ascii_letters_or_marks')]
    if any(type(count) is not int or not 0 <= count < 2 ** 63 for count in counts):
        return None
    status = value.get('threshold_status')
    reasons = value.get('uninterpreted_reasons')
    if (status not in ('uninterpreted', 'below_lower', 'below_upper', 'no_below_range_match')
            or not isinstance(reasons, list) or len(reasons) > len(_REASONS)
            or any(not isinstance(reason, str) or reason not in _REASONS for reason in reasons)
            or len(set(reasons)) != len(reasons)
            or bool(reasons) != (status == 'uninterpreted')):
        return None
    characters, matches, outside = counts
    review = ('Threshold review was not applied: ' + '; '.join(_REASONS[reason] for reason in reasons) + '.'
              if reasons else 'Threshold review uses the configured ASCII-pattern counts only.')
    return (f'Reported selected text: {characters} Unicode code points; {matches} ASCII-pattern matches; '
            f'{outside} non-ASCII letter/mark code points. ' + review + ' ' + LIMITS
            + ' Extraction basis and configured bounds are recorded in JSON.')
