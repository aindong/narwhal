"""Literal statistic/citation-pattern receipts, not evidence-quality judgments."""

LIMITS = ('These are configured statistic-pattern and English-oriented citation-cue '
          'matches in selected extracted text, not verified statistics, citations or sources. '
          'Other numbers, links and references may exist. More matches do not establish '
          'better evidence or a writing target. Review actual claims and relevant sources '
          'in context; do not invent statistics or citations to satisfy a count. '
          'Factual support, source validity, ranking and citation impact are not measured.')


def _count(value):
    return type(value) is int and 0 <= value < 2 ** 63


def observe(statistics, citations, source_basis):
    """Record the existing two regex match counts without changing algorithms."""
    basis = str(source_basis)
    return {'version': 1, 'basis': 'audit_geo_stat_and_cite_hint_v1',
            'statistic_matches': statistics, 'citation_cue_matches': citations,
            'total_matches': statistics + citations, 'source_validity_checked': False,
            'source_basis': basis[:160], 'source_basis_clipped': len(basis) > 160,
            'limits': LIMITS}


def recorded(facts):
    """Missing, malformed or conflicting legacy measurements stay unverified."""
    value = facts.get('evidence_cues') if isinstance(facts, dict) else None
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('basis') != 'audit_geo_stat_and_cite_hint_v1'
            or value.get('source_validity_checked') is not False
            or type(value.get('source_basis')) is not str or len(value['source_basis']) > 160
            or not value['source_basis'].strip() or type(value.get('source_basis_clipped')) is not bool
            or not all(_count(value.get(key)) for key in
                       ('statistic_matches', 'citation_cue_matches', 'total_matches'))
            or value['total_matches'] != value['statistic_matches'] + value['citation_cue_matches']):
        return None
    if 'stats_cites' in facts and (not _count(facts['stats_cites']) or facts['stats_cites'] != value['total_matches']):
        return None
    return value


def cell(facts):
    """Display actual units; never relabel an old scalar as verified evidence."""
    value = recorded(facts)
    if value is not None:
        return (f"{value['statistic_matches']} statistic-pattern + "
                f"{value['citation_cue_matches']} citation-cue matches")
    legacy = facts.get('stats_cites') if isinstance(facts, dict) else None
    return str(legacy) + ' (basis unrecorded)' if _count(legacy) else 'Unrecorded'


def summary(you, rivals):
    """Produce only static limits and typed counts, not input labels or URLs.

    The 100-page limit bounds this note for supplied JSON, not total input/heap.
    Ordinary CLI inputs have at most three rivals.
    """
    lines = [LIMITS]
    if you is not None:
        lines.append('Your page: ' + cell(you) + '.')
    if not isinstance(rivals, list) or len(rivals) > 100:
        return lines + ['Compared-page cue measurement basis is unrecorded or unsupported.']
    values = [recorded(facts) for facts in rivals]
    totals = [value['total_matches'] for value in values if value is not None]
    if totals:
        lines.append(f'Compared pages: {min(totals)}–{max(totals)} combined pattern matches '
                     f'({len(totals)}/{len(rivals)} pages with a recorded basis).')
    else:
        lines.append(f'Compared pages: no recorded cue measurements ({len(rivals)} pages supplied).')
    return lines
