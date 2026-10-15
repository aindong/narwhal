"""Declared indexing restrictions, not a live search-index or crawler test."""

import re

_PREFIX = re.compile(r'^\s*([A-Za-z*][A-Za-z0-9_.\-*]*)\s*:\s*(.*)$')
_PARAMETERS = {'max-snippet', 'max-image-preview', 'max-video-preview', 'unavailable_after'}


def restriction_names(value):
    """Recognize standalone names, never substrings or directive parameters."""
    names = set()
    for part in value.lower().split(','):
        tokens = part.split(':', 1)[0].split()[:-1] if ':' in part else part.split()
        names.update(token for token in tokens if token in ('noindex', 'nofollow', 'none'))
    return names


def expand(names):
    """Expand the none alias without interpreting unrelated serving rules."""
    rules = set(names) & {'noindex', 'nofollow'}
    if 'none' in names:
        rules.update(('noindex', 'nofollow'))
    return rules


def http_robots(fields, basis):
    """Keep named-agent scope within each transport-reported header field.

    A new field resets to generic scope. Known parameter names are never agent
    prefixes. Browser/legacy transports may already have combined fields; record
    that provenance rather than claiming original wire boundaries or indexability.
    """
    generic, scoped, witnesses = set(), {}, {}
    for number, value in enumerate(fields, 1):
        agent = None
        for part in value.split(','):
            prefix = _PREFIX.match(part)
            if prefix:
                name, value_part = prefix.groups()
                if name.lower() in _PARAMETERS:
                    continue
                agent = name.lower()
                part = value_part
            names = restriction_names(part)
            rules = expand(names)
            if not rules:
                continue
            if agent is None:
                generic.update(rules)
                for rule in rules:
                    witnesses.setdefault(rule, f'X-Robots-Tag field #{number}: ' + ', '.join(sorted(names)))
            else:
                scoped.setdefault(agent, set()).update(rules)
    notes = [f'Named crawler {agent[:160]} declares {", ".join(sorted(rules))}; '
             'scope-specific observation, not an all-crawler block or support/access test.'
             for agent, rules in sorted(scoped.items())]
    if basis != 'response_header_fields':
        notes.append('Header field boundaries are transport-reported or merged/unknown; '
                     'confirm original fields when crawler scope matters.')
    return {'version': 1, 'basis': basis, 'field_count': len(fields),
            'generic': sorted(generic),
            'scoped': [{'agent': agent, 'directives': sorted(rules)} for agent, rules in sorted(scoped.items())],
            'notes': notes}, witnesses
