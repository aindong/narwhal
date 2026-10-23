"""Local canonical-reference resolution and bounded HTTP URL comparison.

RFC 3986 sections 6.2.2/6.2.3 and RFC 9110 section 4.2.3 inform the
normalizations, not a claim of server equivalence or search-engine selection.
No DNS, URL retrieval or permission decision belongs in these helpers.
"""
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit
from .urlpaths import remove_dot_segments as _path

VERSION = 1
BASIS = 'first_html_canonical_http_components_v1'
COMPONENTS = ('scheme', 'host', 'port', 'path', 'query', 'fragment')
LIMITS = ('First parsed HTML canonical only; comparison normalizes scheme/host case, '
          'default ports, empty root paths, percent-encoded unreserved characters and dot segments. '
          'Other path/query case, separators and query/fragment presence remain distinct. '
          'No target fetch, redirect/content equivalence, HTTP canonical headers, conflict validation '
          'or search-engine-selected canonical is verified.')
ERROR = 'HTML canonical comparison needs verification; technical/overall score comparisons are unverified.'
_PCT = re.compile(r'%([0-9A-Fa-f]{2})')
_BAD_PCT = re.compile(r'%(?![0-9A-Fa-f]{2})')
_UNRESERVED = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')
_ILLEGAL = frozenset('<>"{}|^`\\')


class _Base(HTMLParser):
    """Read the first href-bearing base from an already non-template source."""
    CDATA_CONTENT_ELEMENTS = ('script', 'style', 'textarea', 'title', 'xmp', 'iframe', 'noembed', 'noframes')
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.href = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == 'base' and self.href is None:
            for name, value in attrs:
                if name == 'href':
                    self.href = value or ''
                    break

    def parse_html_declaration(self, index):
        try:
            return super().parse_html_declaration(index)
        except (AssertionError, NotImplementedError):
            # Match the non-template source projection's bogus-comment handling.
            return self.parse_bogus_comment(index)


def _join(base, href):
    """Resolve references without losing empty queries or repeated separators.

    Follow RFC 3986 section 5.2 component inheritance; comparison's additional
    percent normalization stays in key(). Absolute candidates retain evidence.
    """
    reference = urlsplit(href)
    if reference.scheme:
        return href
    if href.startswith('//') and not reference.netloc:
        return href  # an explicit empty authority is not the document's host
    origin = urlsplit(base)
    query_defined = '?' in href.split('#', 1)[0]
    query = reference.query
    if reference.netloc:
        authority, path = reference.netloc, _path(reference.path or '/')
    else:
        authority = origin.netloc
        if not reference.path:
            path = origin.path
            if not query_defined:
                query_defined = '?' in base.split('#', 1)[0]
                query = origin.query
        else:
            merged = (reference.path if reference.path.startswith('/') else
                      ('/' if authority and not origin.path else origin.path.rpartition('/')[0] + '/') + reference.path)
            path = _path(merged)
    return ((origin.scheme + ':' if origin.scheme else '')
            + ('//' + authority if authority else '') + path
            + ('?' + query if query_defined else '')
            + ('#' + reference.fragment if '#' in href else ''))


def first_base(source):
    """Return the first href-bearing base, or None; no document repair or I/O."""
    if '<base' not in source.lower():
        return None
    return _Base(source).href


def resolve(base, href, base_href=None):
    """Resolve a candidate locally; retain malformed nonempty input as evidence."""
    if not href:
        return None
    href = href.strip()
    if not href:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in href):
        return href  # do not let version-dependent URL repair fabricate a match
    try:
        reference = urlsplit(href)
        if reference.scheme in ('http', 'https') and not reference.netloc:
            return href  # explicit HTTP(S) syntax must not borrow the document's authority
        if base_href is not None and any(ord(c) < 32 or ord(c) == 127 for c in base_href.strip()):
            return href
        declared = urlsplit(base_href.strip()) if base_href is not None else None
        if declared is not None and declared.scheme in ('http', 'https') and not declared.netloc:
            return href
        effective = _join(base, base_href.strip()) if base_href is not None else base
        return _join(effective, href)
    except ValueError:
        return href  # presence is not validity; key() will withhold comparison


def _escapes(value):
    def replace(match):
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else '%' + match.group(1).upper()
    return _PCT.sub(replace, value)


def _utf8(value):
    """Map literal non-ASCII component text to UTF-8 percent bytes, not IDNA/NFC."""
    return re.sub(r'[^\x00-\x7f]+',
                  lambda match: ''.join('%%%02X' % byte for byte in match.group().encode('utf-8')),
                  value)


def key(url):
    """Hashable component key, or None for unsupported/malformed candidates.

    Not full URI/IRI validation: IDNA aliases and alternative numeric host
    spellings are not inferred. Never reuse this comparison as a fetch guard.
    """
    if not isinstance(url, str) or not url or any(ord(c) <= 32 or ord(c) == 127 or c.isspace() for c in url):
        return None
    if any(character in _ILLEGAL for character in url) or _BAD_PCT.search(url):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username is not None:
            return None
        if not parts.hostname.isascii() or any(int(match.group(1), 16) >= 128 for match in _PCT.finditer(parts.hostname)):
            return None  # Unicode/IDNA host aliases are outside this comparison
        suffix = parts.netloc.partition(']')[2] if parts.netloc.startswith('[') else parts.netloc.partition(':')[2]
        raw_port = suffix[1:] if parts.netloc.startswith('[') and suffix.startswith(':') else suffix
        if raw_port and not re.fullmatch(r'[0-9]+', raw_port):
            return None
        port = parts.port
        path, query, fragment = (_utf8(part) for part in (parts.path or '/', parts.query, parts.fragment))
    except (ValueError, UnicodeEncodeError):
        return None
    default = 443 if parts.scheme == 'https' else 80
    return (parts.scheme.lower(), _escapes(parts.hostname).lower(), default if port is None else port,
            _path(_escapes(path)),
            ('?' in url.split('#', 1)[0], _escapes(query)),
            ('#' in url, _escapes(fragment)))


def observe(doc, final_url):
    """Record only the first parsed HTML declaration and comparison outcome."""
    declarations = doc.links_by_rel('canonical')
    target = doc.canonical()
    left, right = key(target), key(final_url)
    status = ('missing' if not declarations else
              'unverified' if left is None or right is None else
              'matches' if left == right else 'differs')
    differences = [name for name, a, b in zip(COMPONENTS, left, right) if a != b] if left and right else []
    return {'version': VERSION, 'basis': BASIS, 'status': status, 'differences': differences}


def unverified(meta):
    """Only an explicit supported receipt proves this known comparison gap."""
    value = meta.get('canonical_comparison') if isinstance(meta, dict) else None
    return (isinstance(value, dict) and type(value.get('version')) is int
            and value['version'] == VERSION and value.get('basis') == BASIS
            and value.get('status') == 'unverified' and value.get('differences') == [])
