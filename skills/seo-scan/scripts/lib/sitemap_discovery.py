"""Bounded sitemap discovery I/O; XML and receipt helpers remain pure."""

from . import http, sitemap

MAX_FILES = 50
MAX_INDEX_CHILDREN = 5
MAX_RESPONSE_BYTES = 5_000_000  # preserve the previous fetch_text discovery budget
COMMON_PATHS = ('/sitemap.xml', '/sitemap_index.xml', '/sitemap-index.xml')


class Discovery:
    """One component's deduplicated candidate sample, not a whole-site census."""

    def __init__(self, scope, max_files=MAX_FILES):
        if scope not in sitemap.DISCOVERY_SCOPES:
            raise ValueError('Unsupported sitemap discovery scope.')
        if type(max_files) is not int or not 0 <= max_files <= MAX_FILES:
            raise ValueError('Sitemap discovery budget must be an integer between 0 and 50.')
        self.scope = scope
        self.max_files = max_files
        self.seen = set()
        self.absent = set()
        self.counts = {'verified_files': 0, 'unverified_files': 0, 'absent_files': 0}
        self.reasons = {}
        self.limits = []
        self.uncertain_urls = []

    def limit(self, reason):
        if reason not in self.limits:
            self.limits.append(reason)

    def read(self, url, *, allow_private, timeout, declared=False):
        if url in self.seen:
            if declared and url in self.absent:
                self.absent.remove(url)
                self.counts['absent_files'] -= 1
                self.counts['unverified_files'] += 1
                self.reasons['declared_unavailable'] = self.reasons.get('declared_unavailable', 0) + 1
                self.uncertain_urls.append(url)
            return None  # duplicate references do not retain/reparse whole XML files
        if len(self.seen) >= self.max_files:
            self.limit('file_attempt_budget')
            return None
        self.seen.add(url)
        raw, error = http.fetch_bytes(url, allow_private=allow_private, timeout=timeout,
                                     max_bytes=MAX_RESPONSE_BYTES)
        if raw is None or error:
            if error in ('HTTP 404', 'HTTP 410') and not declared:
                self.counts['absent_files'] += 1
                self.absent.add(url)
                return None
            problem = 'declared_unavailable' if error in ('HTTP 404', 'HTTP 410') else 'fetch_unverified'
        else:
            text, problem = sitemap.decode_checked(raw)
            if not problem:
                kind, entries, problem = sitemap.parse_checked(text)
            if not problem:
                self.counts['verified_files'] += 1
                return kind, entries
        self.counts['unverified_files'] += 1
        self.reasons[problem] = self.reasons.get(problem, 0) + 1
        self.uncertain_urls.append(url)
        return None

    def receipt(self):
        return {'basis': 'bounded_xml_discovery', 'scope': self.scope,
                'attempted_files': len(self.seen), **self.counts,
                'file_attempt_limit': self.max_files, 'response_byte_limit': MAX_RESPONSE_BYTES,
                'decoded_byte_limit': sitemap.MAX_DECODED_BYTES,
                'reasons': dict(self.reasons), 'limits': list(self.limits)}
