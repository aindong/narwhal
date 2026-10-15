"""Root llms.txt response evidence, not full proposal or engine validation."""

import re
from . import http

SOURCE = 'https://llmstxt.org/'
SOURCE_CHECKED = '2026-10-15'
_TEXT_TYPES = ('', 'text/plain', 'text/markdown', 'text/x-markdown')
_REASONS = {
    'candidate_text': 'a complete text response with an initial Markdown H1 was observed',
    'http_absence': 'the root request returned HTTP 404 or 410',
    'request_failed': 'the root request failed',
    'http_unverified': 'the root response was gated, unsuccessful or otherwise unverified',
    'truncated': 'the root response exceeded its body budget',
    'partial_response': 'the root endpoint returned partial content',
    'html_response': 'the root endpoint returned HTML, possibly an application fallback',
    'unsupported_media_type': 'the root endpoint did not return a supported text media type',
    'empty_body': 'the root response had no usable text',
    'heading_not_observed': 'an initial Markdown H1 candidate was not observed',
}
_SCOPE = ('Root /llms.txt request only; independent subpath files and rel=describedby discovery were not checked. '
          'Redirect destinations are recorded. '
          'This is not full proposal validation, linked-resource verification, engine adoption or evidence of ranking/citation impact.')


def _heading(text):
    """Recognize initial ATX or simple Setext H1 evidence, not full Markdown."""
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'\A(?:[ \t]*\n)*', '', text)
    lines = text.split('\n', 3)
    if not lines:
        return False
    if re.match(r'^ {0,3}#[ \t]+\S', lines[0]):
        return True
    return (len(lines) > 1 and bool(re.match(r'^ {0,3}\S', lines[0]))
            and not lines[0].lstrip().startswith(('<', '#', '`', '~'))
            and bool(re.fullmatch(r' {0,3}=+[ \t]*', lines[1])))


def assess(response):
    """Classify an already bounded fetch without retaining remote body text."""
    status = response.status if type(response.status) is int else 0
    mime = (response.headers.get('content-type') or '').split(';', 1)[0].strip().lower()[:120]
    truncated = response.headers.get('x-narwhal-truncated') == 'true'
    partial = status == 206 or bool(response.headers.get('content-range'))
    text = response.text if isinstance(response.text, str) else ''
    state, reason = 'unverified', 'http_unverified'
    if status in (404, 410):
        if truncated:
            reason = 'truncated'
        elif partial:
            reason = 'partial_response'
        else:
            state, reason = 'absent', 'http_absence'
    elif response.error:
        reason = 'request_failed'
    elif 200 <= status < 300:
        if truncated:
            reason = 'truncated'
        elif partial:
            reason = 'partial_response'
        elif status in (204, 205):
            reason = 'empty_body'
        elif mime in ('text/html', 'application/xhtml+xml') or re.match(
                r'^\s*(?:<!doctype\s+html\b|<html\b|<head\b|<body\b)', text.lstrip('\ufeff'), re.I):
            reason = 'html_response'
        elif mime not in _TEXT_TYPES:
            reason = 'unsupported_media_type'
        elif not text.strip('\ufeff \t\r\n'):
            reason = 'empty_body'
        elif not _heading(text):
            reason = 'heading_not_observed'
        else:
            state, reason = 'observed', 'candidate_text'
    return {'version': 1, 'basis': 'root_http_response', 'checked_path': '/llms.txt',
            'state': state, 'reason': reason, 'http_status': status,
            'media_type': mime, 'body_truncated': truncated, 'partial_response': partial,
            'requested_url': response.url, 'final_url': response.final_url,
            'source': SOURCE, 'source_checked': SOURCE_CHECKED}


def probe(url, *, allow_private, timeout):
    """Use the existing fetch guards/budget; do not follow links in the file."""
    return assess(http.fetch(url, allow_private=allow_private, timeout=timeout))


def recorded(value):
    """Accept only known, consistent receipts; never infer legacy HTTP state."""
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != 1 or value.get('checked_path') != '/llms.txt'):
        return None
    if value.get('basis') in ('legacy_context', 'not_recorded'):
        return value if value.get('state') == 'unverified' and (
            value['basis'] == 'not_recorded' or type(value.get('reported_present')) is bool) else None
    if (value.get('basis') != 'root_http_response' or type(value.get('http_status')) is not int
            or not 0 <= value['http_status'] <= 999 or type(value.get('body_truncated')) is not bool
            or type(value.get('partial_response')) is not bool
            or not isinstance(value.get('media_type'), str)
            or not all(isinstance(value.get(key), str) for key in ('requested_url', 'final_url'))):
        return None
    state, reason, status = value.get('state'), value.get('reason'), value['http_status']
    if not isinstance(reason, str):
        return None
    if state == 'observed':
        valid = (reason == 'candidate_text' and 200 <= status < 300 and status not in (204, 205, 206)
                 and not value['body_truncated'] and not value['partial_response']
                 and value['media_type'] in _TEXT_TYPES)
    elif state == 'absent':
        valid = (reason == 'http_absence' and status in (404, 410)
                 and not value['body_truncated'] and not value['partial_response'])
    else:
        valid = (state == 'unverified' and reason in _REASONS
                 and reason not in ('candidate_text', 'http_absence')
                 and (reason != 'truncated' or value['body_truncated'])
                 and (reason != 'partial_response' or value['partial_response'])
                 and (status not in (404, 410) or reason in ('truncated', 'partial_response')))
    return value if valid else None


def note(meta):
    value = recorded(meta.get('llms_txt')) if isinstance(meta, dict) else None
    if not value:
        return None
    if value['basis'] == 'root_http_response':
        detail = _REASONS[value['reason']] + f" (HTTP {value['http_status']})."
    elif value['basis'] == 'legacy_context':
        detail = 'A caller supplied a legacy presence/absence flag; no root HTTP evidence was recorded.'
    else:
        detail = 'No root HTTP evidence was recorded.'
    return 'Root llms.txt ' + value['state'] + ': ' + detail + ' ' + _SCOPE


def problem(meta, *, for_score=False):
    value = recorded(meta.get('llms_txt')) if isinstance(meta, dict) else None
    if not value or value['state'] != 'unverified':
        return None
    if for_score and value['basis'] != 'root_http_response':
        return None  # caller flags / old missing coverage are not HTTP measurements
    return note(meta)
