"""Dated Google appearance notices, not schema.org validity or eligibility."""

# Existing offline snapshot, shared with the page auditor. No runtime policy I/O.
FEATURE_STATUS_CHECKED = '2026-10-12'
DEPRECATED = {
    'HowTo': 'HowTo rich results were retired from Google Search in September 2023.',
    'FAQPage': 'FAQ rich results stopped appearing in Google Search on May 7, 2026; the former government/health restriction is no longer current.',
    'SpecialAnnouncement': 'SpecialAnnouncement rich-result support was retired from Google Search in 2025.',
    'ClaimReview': "ClaimReview rich-result support was retired from Google Search in 2025. The markup remains supported by Google's Fact Check Explorer tool.",
}
DEPRECATED_SOURCES = {
    'HowTo': 'https://developers.google.com/search/blog/2023/08/howto-faq-changes',
    'FAQPage': 'https://developers.google.com/search/updates',
    'SpecialAnnouncement': 'https://developers.google.com/search/blog/2025/06/simplifying-search-results',
    'ClaimReview': 'https://developers.google.com/search/blog/2025/06/simplifying-search-results',
}
DEPRECATED_ADDITIONAL_SOURCES = {
    'ClaimReview': ['https://developers.google.com/search/docs/appearance/structured-data/factcheck'],
}
SCOPE = 'Google Search rich-result appearance, not schema.org validity or ranking'
BASIS = 'dated_google_retirement_snapshot'
LIMITS = ('This is a dated offline snapshot, not a live Google eligibility test or a complete '
          'feature registry. Types without a listed retirement notice are not certified supported, '
          'eligible or valid. Retain accurate markup when useful for semantic meaning or other '
          'consumers; retirement alone does not invalidate schema.org or establish a ranking '
          'penalty. Only mark up actual content; AI citation impact is not measured.')


def notice(typ):
    """Fresh, source-backed metadata with the page auditor's existing shape."""
    if type(typ) is not str or typ not in DEPRECATED:
        return None
    return {'type': typ, 'status': 'retired', 'scope': SCOPE,
            'checked_on': FEATURE_STATUS_CHECKED, 'source': DEPRECATED_SOURCES[typ],
            'additional_sources': list(DEPRECATED_ADDITIONAL_SOURCES.get(typ, []))}


def observe(types):
    """Annotate observed/suggested types without changing their types or scores."""
    return {'version': 1, 'basis': BASIS, 'checked_on': FEATURE_STATUS_CHECKED,
            'notices': [notice(typ) for typ in sorted(DEPRECATED) if typ in types], 'limits': LIMITS}


def recorded(value, types):
    """Recognize this dated snapshot and its links; never infer missing receipts.

    Inspect existing type strings without copying/joining them. Only four known
    notice kinds can be retained; these are note bounds, not total input budgets.
    """
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('basis') != BASIS or value.get('checked_on') != FEATURE_STATUS_CHECKED
            or not isinstance(types, list) or any(type(typ) is not str for typ in types)
            or not isinstance(value.get('notices'), list) or len(value['notices']) > len(DEPRECATED)):
        return None
    expected = observe(types)
    return expected if value['notices'] == expected['notices'] else None


def lines(value, types):
    """Render only canonical static notices/links, not arbitrary receipt strings."""
    receipt = recorded(value, types)
    if receipt is None:
        return ['Google appearance snapshot unrecorded or unsupported; verify separately.']
    if not receipt['notices']:
        return [f'No listed retirement notice in the snapshot checked {FEATURE_STATUS_CHECKED}; '
                'this is not a supported/eligible/validity verdict.']
    output = []
    for item in receipt['notices']:
        typ = item['type']
        sources = '; '.join('[Google source](' + url + ')' for url in [item['source']] + item['additional_sources'])
        output.append(f'{typ}: retired Google Search rich-result appearance '
                      f'(snapshot checked {FEATURE_STATUS_CHECKED}). {DEPRECATED[typ]} '
                      'Accurate semantic markup may still be useful; no ranking/citation gain is implied. '
                      + sources + '.')
    return output


def summary(you, rivals):
    """Label page context without rendering supplied names, URLs or policy links."""
    output = [LIMITS]
    pages = ([('Your page', you)] if you is not None else [])
    if not isinstance(rivals, list) or len(rivals) > 100:
        return output + ['Compared-page appearance snapshots unrecorded or unsupported.']
    pages += [(f'Compared page {i + 1}', facts) for i, facts in enumerate(rivals)]
    for label, facts in pages:
        facts = facts if isinstance(facts, dict) else {}
        output += [label + ' — ' + line for line in lines(facts.get('schema_search_features'), facts.get('schema_types'))]
    return output
