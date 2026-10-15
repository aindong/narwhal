"""Bounded attribution-cue observations, never verified writers or expertise.

Read-only source projection shared by scans and comparisons. No links are
followed, names authenticated or structured-data author graphs interpreted.
"""

from html.parser import HTMLParser
from itertools import chain, islice
import re

MAX_SOURCE_CHARS = 250_000
MAX_LEADING_TEXT = 1_500
MAX_VALUE_CHARS = 160
MAX_CANDIDATES = 5
MAX_DEPTH = 80
MAX_NORMALIZED_FIELDS = 1000
_VOID = set('area base br col embed hr img input link meta param source track wbr'.split())
_BLOCKS = {'p', 'div', 'header', 'address', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
_SKIP = {'script', 'style', 'template', 'textarea', 'title', 'nav', 'footer', 'aside'}
_MARKERS = {'byline', 'article-author', 'author-name', 'post-author'}
_LABEL = re.compile(r'^(?:written\s+by|reviewed\s+by|by|author:)\s+(.+)$', re.I)
LIMITS_NOTE = ('Attribution candidates only: writer identity, rendered visibility, expertise, '
               'trust, author-link destinations and ranking impact are not verified. '
               'These bounded checks do not establish that attribution is absent.')
LABELS = {'author_meta': 'Author metadata', 'article_author_meta': 'Article-author metadata',
          'author_link': 'Declared author link', 'byline_block': 'Leading byline-like block',
          'provided_text': 'Provided byline-like text'}


def _text(value):
    if not isinstance(value, str):
        return ''
    return ' '.join(''.join(c if ord(c) >= 32 else ' ' for c in value).split())


def _byline(value, marked=False):
    """Conservative short-label heuristic, not a person-name recognizer."""
    value = _text(value)
    if not value or len(value) > MAX_VALUE_CHARS:
        return False
    match = _LABEL.match(value)
    payload = match.group(1) if match else value
    if not marked and not match:
        return False
    if not payload or len(payload.split()) > 8 or not any(c.isalpha() for c in payload):
        return False
    if payload.lower().rstrip(':').strip() in {'by', 'author', 'written by', 'reviewed by'}:
        return False
    if not marked:
        # Reject common prose such as "by following these steps". Unmarked
        # lowercase pen names may be missed; explicit markers/metadata support
        # those without pretending a language-independent name validator.
        first = next((c for c in payload if c.isalpha()), '')
        if not first or first.islower() or any(c.isdigit() for c in payload):
            return False
    return True


class _Limit(Exception):
    pass


class _Probe(HTMLParser):
    CDATA_CONTENT_ELEMENTS = ('script', 'style', 'textarea', 'title')

    def __init__(self, noscript=False):
        super().__init__(convert_charrefs=True)
        self.frames, self.candidates, self.seen = [], [], set()
        self.text_seen = 0
        self.noscript = noscript
        self.depth_limited = self.candidates_omitted = False

    def add(self, kind, value):
        value = _text(value)
        if not value:
            return
        key = kind, value[:MAX_VALUE_CHARS]
        if key in self.seen:
            return
        if len(self.candidates) >= MAX_CANDIDATES:
            self.candidates_omitted = True
            return
        self.seen.add(key)
        self.candidates.append({'kind': kind, 'value': key[1],
                                'truncated': len(value) > MAX_VALUE_CHARS})

    def declaration(self, tag, attrs):
        if tag == 'meta':
            if _text(attrs.get('name')).lower() == 'author':
                self.add('author_meta', attrs.get('content'))
            if _text(attrs.get('property')).lower() == 'article:author':
                self.add('article_author_meta', attrs.get('content'))
        if tag in {'a', 'area', 'link'} and 'author' in _text(attrs.get('rel')).lower().split():
            self.add('author_link', attrs.get('href'))

    def handle_starttag(self, tag, pairs):
        attrs = {}
        for key, value in pairs:
            attrs.setdefault(key, value)
        blocked = (bool(self.frames and self.frames[-1]['blocked']) or tag in _SKIP
                   or (tag == 'noscript' and not self.noscript) or 'hidden' in attrs
                   or _text(attrs.get('aria-hidden')).lower() == 'true')
        if not blocked:
            self.declaration(tag, attrs)
        if tag in _VOID:
            return
        if len(self.frames) >= MAX_DEPTH:
            self.depth_limited = True
            raise _Limit()
        marked = bool(_MARKERS & set(_text(attrs.get('class')).lower().split()))
        self.frames.append({'tag': tag, 'blocked': blocked, 'marked': marked,
                            'collect': tag in _BLOCKS or marked, 'start': self.text_seen,
                            'parts': [], 'length': 0})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        # HTML ignores the slash on non-void elements. In particular, a slash
        # must not expose text inside a hidden/template/raw-text container.
        if tag in self.CDATA_CONTENT_ELEMENTS:
            self.set_cdata_mode(tag)

    def emit(self, frame):
        if (not frame['blocked'] and frame['collect'] and frame['start'] < MAX_LEADING_TEXT
                and frame['length'] <= MAX_VALUE_CHARS):
            text = ' '.join(frame['parts'])
            if _byline(text, frame['marked']):
                self.add('byline_block', text)

    def handle_endtag(self, tag):
        # Template contents cannot close an outer document frame. Apply the
        # same conservative boundary to unselected noscript content.
        barrier = next((i for i in range(len(self.frames) - 1, -1, -1)
                        if self.frames[i]['tag'] in {'template', 'noscript'}), 0)
        for index in range(len(self.frames) - 1, -1, -1):
            if index < barrier:
                return
            if self.frames[index]['tag'] == tag:
                for frame in reversed(self.frames[index:]):
                    self.emit(frame)
                del self.frames[index:]
                return

    def handle_data(self, data):
        if self.frames and self.frames[-1]['blocked']:
            return
        text = _text(data)
        if not text:
            return
        self.text_seen += len(text) + 1
        for frame in self.frames:
            if frame['collect'] and frame['start'] < MAX_LEADING_TEXT and frame['length'] <= MAX_VALUE_CHARS:
                separator = int(bool(frame['parts']))
                frame['parts'].append(text[:MAX_VALUE_CHARS + 1])
                frame['length'] += len(text) + separator

    def parse_html_declaration(self, index):
        try:
            return super().parse_html_declaration(index)
        except (AssertionError, NotImplementedError):
            return self.parse_bogus_comment(index)


def observe(doc, text=''):
    """Return owned JSON-safe, capped source witnesses, independent of main text."""
    probe = _Probe(noscript=getattr(doc, 'extraction', '') == 'noscript fallback')
    source = getattr(doc, 'document_html', '')
    source = source if isinstance(source, str) else ''
    source_truncated = len(source) > MAX_SOURCE_CHARS
    normalized_fields_limited = False
    if source:
        try:
            probe.feed(source[:MAX_SOURCE_CHARS])
            if not source_truncated:
                probe.close()
                for frame in reversed(probe.frames):
                    probe.emit(frame)
        except _Limit:
            pass
    else:
        # Preserve normalized-Doc/programmatic callers without inventing an
        # HTTP/source observation or assuming supplied text is rendered visible.
        def bounded_fields(items):
            nonlocal normalized_fields_limited
            for index, item in enumerate(islice(items, MAX_NORMALIZED_FIELDS + 1)):
                if index == MAX_NORMALIZED_FIELDS:
                    normalized_fields_limited = True
                    return
                yield item

        for tag in bounded_fields(getattr(doc, 'meta', [])):
            attrs = getattr(tag, 'attrs', {})
            if isinstance(attrs, dict):
                probe.declaration('meta', attrs)
        for tag in bounded_fields(chain(getattr(doc, 'links', []), getattr(doc, 'link_rels', []))):
            attrs = getattr(tag, 'attrs', {})
            if isinstance(attrs, dict):
                attrs = dict(attrs)
                if isinstance(attrs.get('rel'), list):
                    attrs['rel'] = ' '.join(item for item in attrs['rel'] if isinstance(item, str))
                probe.declaration('a', attrs)
        if isinstance(text, str):
            for line in text[:MAX_LEADING_TEXT].splitlines():
                if _byline(line):
                    probe.add('provided_text', line)
    return {'version': 1, 'interpretation': 'attribution_candidates_only',
            'basis': 'bounded_document_cues' if source else 'normalized_doc_fields',
            'state': 'candidate_observed' if probe.candidates else 'no_candidate_observed',
            'candidates': probe.candidates, 'limits_note': LIMITS_NOTE,
            'limits': {'source_characters': MAX_SOURCE_CHARS, 'leading_text_characters': MAX_LEADING_TEXT,
                       'value_characters': MAX_VALUE_CHARS, 'candidates': MAX_CANDIDATES, 'depth': MAX_DEPTH,
                       'normalized_fields_per_group': MAX_NORMALIZED_FIELDS},
            'coverage': {'source_truncated': source_truncated, 'depth_limited': probe.depth_limited,
                         'candidates_omitted': probe.candidates_omitted,
                         'normalized_fields_limited': normalized_fields_limited}}


def evidence_lines(meta):
    """Validate presentation input; values stay literal code, never hyperlinks."""
    receipt = meta.get('authorship_cues') if isinstance(meta, dict) else None
    if (not isinstance(receipt, dict) or type(receipt.get('version')) is not int
            or receipt['version'] != 1 or receipt.get('interpretation') != 'attribution_candidates_only'):
        return []
    lines = []
    candidates = receipt.get('candidates')
    if isinstance(candidates, list):
        for item in candidates[:MAX_CANDIDATES]:
            if (isinstance(item, dict) and isinstance(item.get('kind'), str)
                    and item['kind'] in LABELS and isinstance(item.get('value'), str)):
                value = _text(item['value'])[:MAX_VALUE_CHARS]
                if value:
                    lines.append(LABELS[item['kind']] + ': ' + value
                                 + (' [value clipped]' if item.get('truncated') is True else ''))
    if not lines and receipt.get('article_hint') is not True:
        return []
    if not lines:
        lines.append('No candidate observed in the checked sources; attribution remains unverified.')
    coverage = receipt.get('coverage')
    if isinstance(coverage, dict) and any(coverage.get(key) is True for key in
                                         ('source_truncated', 'depth_limited', 'candidates_omitted',
                                          'normalized_fields_limited')):
        lines.append('A source/depth/candidate/field limit was reached; unchecked evidence remains unknown.')
    return lines
