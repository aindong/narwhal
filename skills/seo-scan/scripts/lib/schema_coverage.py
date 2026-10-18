"""Known structured-data extraction problems are not evidence of absence."""

BASIS = 'supported_structured_data_extraction'
COUNTS = ('jsonld_blocks', 'jsonld_errors', 'microdata_warning_details', 'rdfa_warning_details')
LIMITS = ('Counts describe the supported extractor only, not complete JSON-LD/RDFa conformance, '
          'schema.org validity, visible-content ownership or Google eligibility. Warning-detail '
          'counts include retained omission notices, not all underlying errors. No known problem '
          'is not proof of exhaustive extraction. Known problems leave schema/overall score '
          'comparisons unverified; observed types remain observations, not evidence of absence.')


def observe(doc, errors):
    """Use the same collection pass and cached bounded warning lists; no raw text."""
    counts = {'jsonld_blocks': len(doc.scripts_ld), 'jsonld_errors': len(errors),
              'microdata_warning_details': len(doc.microdata_warnings),
              'rdfa_warning_details': len(doc.rdfa_warnings)}
    return {'version': 1, 'basis': BASIS,
            'source_basis': 'document_html' if doc.html else 'provided_doc_fields',
            'status': 'unverified' if any(counts[key] for key in COUNTS[1:]) else 'no_known_problem',
            **counts, 'limits': LIMITS}


def recorded(value):
    """Recognize explicit counts/coverage; old/malformed receipts stay unknown."""
    if (not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1
            or value.get('basis') != BASIS or value.get('source_basis') not in ('document_html', 'provided_doc_fields')
            or any(type(value.get(key)) is not int or not 0 <= value[key] < 2 ** 63 for key in COUNTS)
            or value['jsonld_errors'] > value['jsonld_blocks']):
        return None
    expected = 'unverified' if any(value[key] for key in COUNTS[1:]) else 'no_known_problem'
    return value if value.get('status') == expected else None


def state(value):
    receipt = recorded(value)
    return receipt['status'] if receipt else 'unknown'


def fact_state(facts):
    return state(facts.get('schema_extraction')) if isinstance(facts, dict) else 'unknown'


def absence_review(facts):
    """A conditional supported-subset review, never certified schema absence."""
    return fact_state(facts) == 'no_known_problem'


def comparison(you, rivals):
    own = fact_state(you) if you is not None else 'not_supplied'
    compared = [fact_state(facts) for facts in rivals]
    states = ([own] if you is not None else []) + compared
    status = ('unverified' if 'unverified' in states else 'unknown' if 'unknown' in states or not states
              else 'no_known_problem')
    return {'version': 1, 'basis': BASIS, 'status': status,
            'your_status': own, 'compared_statuses': compared, 'limits': LIMITS}


def describe(value):
    receipt = recorded(value)
    if receipt is None:
        return 'Extraction coverage unrecorded or unsupported; absence and score comparisons are unverified.'
    counts = (f"{receipt['jsonld_errors']}/{receipt['jsonld_blocks']} JSON-LD blocks with processing errors; "
              f"{receipt['microdata_warning_details']} retained Microdata warning details; "
              f"{receipt['rdfa_warning_details']} retained RDFa warning details.")
    source = ('Parsed document HTML.' if receipt['source_basis'] == 'document_html' else 'Caller-provided Doc fields.')
    return (('Known extraction problems; schema/overall score comparisons unverified. '
             if receipt['status'] == 'unverified' else 'No known extraction problem in the supported subset. ')
            + counts + ' ' + source)


def summary(you, rivals):
    """Static scope/count notes only; 100-page cap is not a total input budget."""
    lines = [LIMITS]
    if you is not None:
        lines.append('Your page — ' + describe(you.get('schema_extraction') if isinstance(you, dict) else None))
    if not isinstance(rivals, list) or len(rivals) > 100:
        return lines + ['Compared-page extraction coverage unrecorded or unsupported.']
    lines += [f'Compared page {i + 1} — ' + describe(facts.get('schema_extraction') if isinstance(facts, dict) else None)
              for i, facts in enumerate(rivals)]
    return lines


def meta_receipt(meta):
    data = meta.get('structured_data') if isinstance(meta, dict) else None
    return data.get('extraction_coverage') if isinstance(data, dict) else None
