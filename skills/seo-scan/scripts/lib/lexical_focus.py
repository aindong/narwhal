"""Bounded witnesses for the existing frequency/overlap heuristic, not topics."""
import hashlib
from heapq import nsmallest

from . import text as textlib

MAX_BODY = 8
MAX_PHRASES = 3
MAX_FOCUS = 12
MAX_VALUE = 160
LIMITS = ('ASCII frequency and exact term overlap only, not dominant topics, semantic relevance, '
          'intent satisfaction, rankings or AI citations. Top-8 cutoff/ties, synonyms, inflections, '
          'stopwords and extraction can hide matches; overlap does not establish semantic coverage.')


def _stopwords():
    return hashlib.sha256('\n'.join(sorted(textlib.STOPWORDS)).encode('utf-8')).hexdigest()


def _term(term, count=None):
    value = {'term': term[:MAX_VALUE], 'clipped': len(term) > MAX_VALUE}
    if count is not None:
        value['count'] = count
    return value


def observe(doc, text=None):
    """Preserve original top-term, phrase, title/first-H1 and overlap decisions."""
    text = (doc.body_text or '') if text is None else text
    terms = textlib.top_keywords(text, MAX_BODY)
    phrases = textlib.top_bigrams(text, MAX_PHRASES) if terms else []
    focus = set(textlib.words((doc.title or '').lower()))
    h1s = [value for level, value in doc.headings if level == 1]
    if h1s:
        focus |= set(textlib.words(h1s[0].lower()))
    focus = {word for word in focus if len(word) >= 3 and word not in textlib.STOPWORDS}
    shared = len(focus & {term for term, count in terms})
    basis = str(doc.extraction)
    return {'version': 1, 'basis': 'selected_text_ascii_frequency_and_exact_overlap',
            'word_pattern': textlib._WORD.pattern, 'minimum_term_characters': 3,
            'stopwords_sha256': _stopwords(), 'tie_basis': 'first_selected_text_occurrence',
            'focus_basis': 'normalized_title_plus_first_h1',
            'source_basis': basis[:MAX_VALUE], 'source_basis_clipped': len(basis) > MAX_VALUE,
            'body_term_limit': MAX_BODY, 'phrase_limit': MAX_PHRASES,
            'focus_witness_limit': MAX_FOCUS,
            'body_terms': [_term(term, count) for term, count in terms],
            'phrases': [_term(term, count) for term, count in phrases],
            'focus_terms': [_term(term) for term in nsmallest(MAX_FOCUS, focus)],
            'focus_term_count': len(focus), 'shared_term_count': shared,
            'focus_witnesses_omitted': len(focus) > MAX_FOCUS,
            'status': ('no_body_terms' if not terms else 'no_focus_terms' if not focus else
                       'observed_overlap' if shared else 'zero_overlap'),
            'limits': LIMITS}


def recorded(value):
    """Validate supported bounded receipt shape/coherence, not source truth."""
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('basis') != 'selected_text_ascii_frequency_and_exact_overlap'
            or value.get('word_pattern') != textlib._WORD.pattern or value.get('stopwords_sha256') != _stopwords()
            or value.get('tie_basis') != 'first_selected_text_occurrence'
            or value.get('focus_basis') != 'normalized_title_plus_first_h1'
            or type(value.get('source_basis')) is not str or not value['source_basis'].strip()
            or len(value['source_basis']) > MAX_VALUE or type(value.get('source_basis_clipped')) is not bool
            or value['source_basis_clipped'] and len(value['source_basis']) != MAX_VALUE):
        return None
    for key, expected in (('body_term_limit', MAX_BODY), ('phrase_limit', MAX_PHRASES),
                          ('focus_witness_limit', MAX_FOCUS), ('minimum_term_characters', 3)):
        if type(value.get(key)) is not int or value[key] != expected:
            return None
    if (any(type(value.get(k)) is not int or not 0 <= value[k] < 2**63
            for k in ('focus_term_count', 'shared_term_count'))
            or type(value.get('focus_witnesses_omitted')) is not bool):
        return None
    for key, limit in (('body_terms', MAX_BODY), ('phrases', MAX_PHRASES), ('focus_terms', MAX_FOCUS)):
        items = value.get(key)
        if not isinstance(items, list) or len(items) > limit:
            return None
        for item in items:
            if (not isinstance(item, dict) or type(item.get('term')) is not str
                    or not 3 <= len(item['term']) <= MAX_VALUE or type(item.get('clipped')) is not bool
                    or item['clipped'] and len(item['term']) != MAX_VALUE):
                return None
            parts = (item['term'].rstrip(' ') if item['clipped'] else item['term']).split(' ')
            if (any(not textlib._WORD.fullmatch(part) or part != part.lower() for part in parts)
                    or (len(parts) not in (1, 2) if key == 'phrases' else len(parts) != 1)
                    or key == 'phrases' and not item['clipped'] and len(parts) != 2):
                return None
            if key != 'focus_terms' and (type(item.get('count')) is not int or not 1 <= item['count'] < 2**63):
                return None
        if key != 'focus_terms' and any(a['count'] < b['count'] for a, b in zip(items, items[1:])):
            return None
        full_terms = [item['term'] for item in items if not item['clipped']]
        if len(full_terms) != len(set(full_terms)):
            return None
    focus_count, shared = value['focus_term_count'], value['shared_term_count']
    if (len(value['focus_terms']) != min(MAX_FOCUS, focus_count)
            or value['focus_witnesses_omitted'] != (focus_count > MAX_FOCUS)
            or shared > min(focus_count, len(value['body_terms']))
            or not value['body_terms'] and value['phrases']):
        return None
    expected_status = ('no_body_terms' if not value['body_terms'] else 'no_focus_terms' if not focus_count else
                       'observed_overlap' if shared else 'zero_overlap')
    if value.get('status') != expected_status:
        return None
    complete = not value['focus_witnesses_omitted'] and not any(
        item['clipped'] for key in ('body_terms', 'focus_terms') for item in value[key])
    if complete and shared != len({item['term'] for item in value['body_terms']} & {item['term'] for item in value['focus_terms']}):
        return None
    return value


def witnesses(value):
    """Bounded literal focus witnesses for report evidence, never keyword quotas."""
    value = recorded(value)
    if value is None:
        return ''
    terms = ', '.join(item['term'] + (' [clipped]' if item['clipped'] else '') for item in value['focus_terms'])
    return (f"Title/first-H1 eligible terms: {value['focus_term_count']}; captured witnesses: {terms or '(none)'}. "
            + ('Additional focus witnesses omitted. ' if value['focus_witnesses_omitted'] else '')
            + f"Exact overlap with {len(value['body_terms'])} retained body term(s): {value['shared_term_count']}. "
            'Terms may still appear outside the top-8 cutoff; this is not semantic coverage.')
