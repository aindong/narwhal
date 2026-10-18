"""Shared literal text-length observations for comparisons and content briefs."""

LIMITS = ('Whitespace-separated tokens are not universal word counts or content depth. '
          'Longer text is not inherently better. Language, formatting and extraction affect '
          'counts; counts alone do not establish a writing target. Ranking and citation '
          'impact are not measured.')


def _count(value):
    """Accept recorded, printable counts without coercing booleans/custom values."""
    return type(value) is int and 0 <= value < 2 ** 63


def observe(text, source_basis):
    """Keep the historical whitespace measurement, with its actual unit/basis."""
    text = text or ''
    basis = str(source_basis)
    return {'version': 1, 'basis': 'python_str_split', 'whitespace_tokens': len(text.split()),
            'code_points': len(text), 'source_basis': basis[:160],
            'source_basis_clipped': len(basis) > 160, 'limits': LIMITS}


def recorded(facts):
    """Read a recognized receipt; missing/conflicting legacy units stay unknown."""
    value = facts.get('text_length') if isinstance(facts, dict) else None
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('basis') != 'python_str_split'
            or type(value.get('source_basis')) is not str or len(value['source_basis']) > 160
            or not value['source_basis'].strip() or type(value.get('source_basis_clipped')) is not bool
            or not _count(value.get('whitespace_tokens')) or not _count(value.get('code_points'))
            or value['whitespace_tokens'] > value['code_points']):
        return None
    if 'words' in facts and (not _count(facts['words']) or facts['words'] != value['whitespace_tokens']):
        return None
    return value


def cell(facts, *, code_points=False):
    """Display known units or label a retained legacy value without inferring it."""
    value = recorded(facts)
    if value is not None:
        return str(value['code_points']) if code_points else str(value['whitespace_tokens']) + ' whitespace tokens'
    legacy = facts.get('words') if isinstance(facts, dict) else None
    return (str(legacy) + ' (basis unrecorded)' if not code_points and _count(legacy) else 'Unrecorded')


def comparison(you, rivals):
    """Record counts in either direction, including hubs, without gap/lead claims."""
    own = recorded(you)
    compared = []
    for facts in rivals:
        value = recorded(facts)
        compared.append({'url': facts.get('url'),
                         'count': value['whitespace_tokens'] if value is not None else None,
                         'status': 'recorded' if value is not None else 'unrecorded'})
    return {'version': 1, 'unit': 'whitespace_tokens', 'interpretation': 'observation_not_target',
            'your_count': own['whitespace_tokens'] if own is not None else None,
            'your_status': 'not_supplied' if you is None else 'recorded' if own is not None else 'unrecorded',
            'compared': compared, 'limits': LIMITS}


def summary(value):
    """Render typed numeric observations, never arbitrary receipt text or URLs.

    CLI inputs have at most three rivals. The 100-row read cap bounds this note
    for supplied JSON, not total report input, CPU or heap.
    """
    unknown = ['Length measurement basis is unrecorded or unsupported. ' + LIMITS]
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('unit') != 'whitespace_tokens'
            or value.get('interpretation') != 'observation_not_target'):
        return unknown
    status, own, rows = value.get('your_status'), value.get('your_count'), value.get('compared')
    if (status not in ('not_supplied', 'recorded', 'unrecorded')
            or (not _count(own) if status == 'recorded' else own is not None)
            or not isinstance(rows, list) or len(rows) > 100):
        return unknown
    counts = []
    for row in rows:
        if not isinstance(row, dict):
            return unknown
        count = row.get('count')
        if row.get('status') == 'recorded' and _count(count):
            counts.append(count)
        elif row.get('status') != 'unrecorded' or count is not None:
            return unknown
    lines = [LIMITS]
    if status == 'recorded':
        lines.append(f'Your page: {own} whitespace tokens in selected extracted text.')
    elif status == 'unrecorded':
        lines.append('Your page: text-length measurement basis unrecorded.')
    if counts:
        lines.append(f'Compared pages: recorded range {min(counts)}–{max(counts)} whitespace tokens '
                     f'({len(counts)}/{len(rows)} pages with a recorded basis).')
    else:
        lines.append(f'Compared pages: no recorded whitespace-token measurements ({len(rows)} pages supplied).')
    return lines
