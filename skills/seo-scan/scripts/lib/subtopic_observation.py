"""Lexical compared-heading candidates, not measured semantic coverage gaps."""
import hashlib

BASIS = 'ascii_english_stopword_prefix_term_overlap'
LIMITS = ('Candidates come from compared H2/H3 labels, not verified section content. '
          'The filter uses ASCII-letter terms (including apostrophes/hyphens), lowercased, '
          'at least three characters, excluding built-in English stopwords. Matching uses '
          'equality, a prefix when both terms have at least four characters, or the same '
          'first six characters when both have at least seven. Own-page inputs are selected '
          'extracted text plus all recorded heading labels. The half-term cutoff is an '
          'unvalidated review heuristic, not semantic coverage: synonyms can be missed and '
          'unrelated word occurrences can match. Topic mode has no own page to assess. '
          'Review relevance and existing coverage; candidates are not required sections, '
          'verified query demand, ranking gaps or measured SEO gains. Keep deliberate '
          'editorial choices separate.')


def context(has_own_page):
    return {'version': 1, 'basis': BASIS, 'mode': 'own_page' if has_own_page else 'topic',
            'interpretation': 'editorial_review_only', 'limits': LIMITS}


def _heading_hash(heading):
    return hashlib.sha256(heading.encode('utf-8', 'surrogatepass')).hexdigest()


def observe(heading, level, examined, matched, has_own_page):
    return {**context(has_own_page), 'heading_sha256': _heading_hash(heading),
            'heading_level': level, 'terms_examined': examined, 'matched_terms': matched,
            'review_cutoff': (examined + 1) // 2}


def recorded(value, has_own_page):
    return (isinstance(value, dict) and type(value.get('version')) is int and value['version'] == 1
            and value.get('basis') == BASIS and value.get('interpretation') == 'editorial_review_only'
            and value.get('mode') == ('own_page' if has_own_page else 'topic'))


def candidate_note(candidate, has_own_page, known_context):
    value = candidate.get('term_match')
    heading = candidate.get('heading')
    valid = (known_context and recorded(value, has_own_page) and isinstance(heading, str)
             and value.get('heading_sha256') == _heading_hash(heading)
             and 'matched_terms' in value
             and type(value.get('heading_level')) is int and value['heading_level'] in (2, 3)
             and type(value.get('terms_examined')) is int and 0 < value['terms_examined'] < 2 ** 63
             and type(value.get('review_cutoff')) is int
             and value['review_cutoff'] == (value['terms_examined'] + 1) // 2)
    if valid and has_own_page:
        matched = value.get('matched_terms')
        valid = type(matched) is int and 0 <= matched < value['review_cutoff']
        if valid:
            return (f"{matched}/{value['terms_examined']} heading terms matched the recorded own-page inputs; "
                    f"below the {value['review_cutoff']}-term review cutoff, not proof of missing content.")
    elif valid and value.get('matched_terms') is None:
        return (f"{value['terms_examined']} eligible heading terms; topic mode has no own-page match measurement.")
    return 'Term-match counts/basis unrecorded or unsupported; treat this as an unverified review candidate.'
