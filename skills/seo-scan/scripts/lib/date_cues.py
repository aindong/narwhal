"""Bounded date-related candidates, never verified publication or freshness."""
from itertools import islice
import re

MAX_FIELDS = 1000
MAX_PREFIX = 2000
MAX_INPUT = 4096
MAX_VALUE = 160
MAX_CANDIDATES = 5
_MONTH = (r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
          r'Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)')
_DATE = re.compile(r'\b(?:[12][0-9]{3}-[0-9]{2}-[0-9]{2}|' + _MONTH
                   + r'\.?\s+(?:[0-9]{1,2}(?:,?\s+[12][0-9]{3})?|[12][0-9]{3}))\b', re.I | re.ASCII)
_YEAR = re.compile(r'\b20[0-9]{2}\b', re.ASCII)
LABELS = {'published_metadata': 'article:published_time metadata',
          'modified_metadata': 'article:modified_time metadata',
          'date_metadata': 'name=date metadata', 'text_pattern': 'Selected-text date-like pattern'}
LIMITS = ('Date-related candidates only, not validated dates, publication/update ownership, '
          'rendered visibility, content freshness, accuracy or ranking/citation impact. '
          'Metadata values and English-month/ISO-like text patterns can be unrelated or invalid. '
          'Bare years alone are not publication evidence. Non-observation in these bounded checks '
          'does not establish that the page lacks dates; structured-data date graphs are not inspected.')


def _text(value):
    if type(value) is not str:
        return ''
    return ' '.join(''.join(c if ord(c) >= 32 and not 0xD800 <= ord(c) <= 0xDFFF else ' '
                            for c in value[:MAX_INPUT]).split())


def observe(doc, text=None):
    """Project normalized metadata and a selected-text prefix without fetching."""
    text = (doc.body_text or '') if text is None else text
    text = text if type(text) is str else ''
    prefix = text[:MAX_PREFIX]
    basis = str(doc.extraction)
    candidates, seen = [], set()
    fields = 0
    flags = {'metadata_limited': False, 'metadata_value_limited': False,
             'candidates_omitted': False, 'text_prefix_limited': len(text) > MAX_PREFIX}

    def add(kind, value, position):
        normalized = _text(value)
        if not normalized:
            return
        key = kind, normalized[:MAX_VALUE]
        if key in seen:
            return
        seen.add(key)
        if len(candidates) == MAX_CANDIDATES:
            flags['candidates_omitted'] = True
            return
        candidates.append({'kind': kind, 'value': key[1], 'position': position,
                           'truncated': len(value) > MAX_INPUT or len(normalized) > MAX_VALUE})

    for index, tag in enumerate(islice(getattr(doc, 'meta', []), MAX_FIELDS + 1)):
        if index == MAX_FIELDS:
            flags['metadata_limited'] = True
            break
        fields += 1
        attrs = getattr(tag, 'attrs', {})
        if not isinstance(attrs, dict):
            continue
        for attr, name, kind in (('property', 'article:published_time', 'published_metadata'),
                                 ('property', 'article:modified_time', 'modified_metadata'),
                                 ('name', 'date', 'date_metadata')):
            selector = attrs.get(attr)
            if type(selector) is not str or len(selector) > MAX_INPUT or selector.strip().lower() != name:
                continue
            value = attrs.get('content')
            if type(value) is str:
                flags['metadata_value_limited'] |= len(value) > MAX_INPUT
                add(kind, value, index + 1)
    for match in _DATE.finditer(prefix):
        add('text_pattern', match.group(), match.start())
    return {'version': 1, 'basis': 'normalized_metadata_and_selected_text_prefix',
            'interpretation': 'date_related_candidates_only',
            'source_basis': basis[:MAX_VALUE], 'source_basis_clipped': len(basis) > MAX_VALUE,
            'metadata_fields_checked': fields, 'text_prefix_characters': len(prefix),
            'text_pattern': _DATE.pattern, 'year_pattern_matches': len(_YEAR.findall(prefix)),
            'candidate_count': len(candidates), 'candidates': candidates, 'coverage': flags,
            'limits': LIMITS}


def recorded(value):
    """Validate supported receipt shape/limits, not source truth or date validity."""
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('basis') != 'normalized_metadata_and_selected_text_prefix'
            or value.get('interpretation') != 'date_related_candidates_only'
            or value.get('text_pattern') != _DATE.pattern
            or type(value.get('source_basis')) is not str or not value['source_basis'].strip()
            or len(value['source_basis']) > MAX_VALUE or type(value.get('source_basis_clipped')) is not bool):
        return None
    for key, limit in (('metadata_fields_checked', MAX_FIELDS), ('text_prefix_characters', MAX_PREFIX),
                       ('year_pattern_matches', MAX_PREFIX), ('candidate_count', MAX_CANDIDATES)):
        if type(value.get(key)) is not int or not 0 <= value[key] <= limit:
            return None
    flags = value.get('coverage')
    if (not isinstance(flags, dict) or set(flags) != {'metadata_limited', 'metadata_value_limited',
            'candidates_omitted', 'text_prefix_limited'} or any(type(flag) is not bool for flag in flags.values())):
        return None
    if (value['year_pattern_matches'] > value['text_prefix_characters']
            or flags['metadata_limited'] and value['metadata_fields_checked'] != MAX_FIELDS
            or flags['text_prefix_limited'] and value['text_prefix_characters'] != MAX_PREFIX
            or flags['candidates_omitted'] and value['candidate_count'] != MAX_CANDIDATES
            or value['source_basis_clipped'] and len(value['source_basis']) != MAX_VALUE):
        return None
    candidates = value.get('candidates')
    if not isinstance(candidates, list) or len(candidates) != value['candidate_count']:
        return None
    for item in candidates:
        if (not isinstance(item, dict) or type(item.get('kind')) is not str or item['kind'] not in LABELS
                or type(item.get('value')) is not str or not item['value'].strip() or len(item['value']) > MAX_VALUE
                or type(item.get('truncated')) is not bool or type(item.get('position')) is not int):
            return None
        position = item['position']
        lower, upper = ((0, value['text_prefix_characters'] - 1) if item['kind'] == 'text_pattern'
                        else (1, value['metadata_fields_checked']))
        if not lower <= position <= upper:
            return None
    return value


def evidence_lines(meta):
    """Bounded one-line literal witnesses, never evidence links or instructions."""
    value = recorded(meta.get('date_cues')) if isinstance(meta, dict) else None
    if value is None:
        return []
    lines = [LABELS[item['kind']] + ': ' + _text(item['value'])
             + (' (clipped)' if item['truncated'] else '') for item in value['candidates']]
    if not lines:
        lines.append('No candidate observed in the checked metadata and selected-text prefix; dates may exist elsewhere.')
    lines.append(f"Checked {value['metadata_fields_checked']} normalized metadata field(s) and "
                 f"{value['text_prefix_characters']} selected-text prefix code points ({_text(value['source_basis'])}).")
    lines.append('Year-pattern matches in selected prefix: ' + str(value['year_pattern_matches']) + ' (not publication evidence on their own).')
    if any(value['coverage'].values()):
        lines.append('Bounded/omitted input or candidate details are recorded in JSON; inspect original sources.')
    return lines


def cell(facts):
    value = recorded(facts.get('date_cues'))
    return str(value['candidate_count']) + ' captured' if value is not None else 'Unrecorded'


def summary(you, rivals):
    if not isinstance(rivals, list) or len(rivals) > 100 or any(not isinstance(p, dict) for p in rivals):
        return [LIMITS, 'Compared-page date-cue scope is unrecorded or unsupported.']
    pages = ([you] if isinstance(you, dict) else []) + rivals
    unknown = sum(recorded(page.get('date_cues')) is None for page in pages)
    lines = [LIMITS]
    if isinstance(you, dict):
        lines.append('Your page: ' + cell(you) + '.')
    counts = [value['candidate_count'] for page in rivals if (value := recorded(page.get('date_cues'))) is not None]
    if counts:
        lines.append(f'Compared pages with recorded scope: {min(counts)}–{max(counts)} captured candidate(s); '
                     f'{len(counts)} of {len(rivals)} compared page(s). Not a publication-date requirement or freshness ranking.')
    if unknown:
        lines.append(f'{unknown} compared page(s) have unrecorded/unsupported date-cue scope; legacy booleans do not supply missing evidence.')
    return lines
