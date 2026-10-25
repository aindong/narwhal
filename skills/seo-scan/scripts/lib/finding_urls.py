"""Bounded recorded URL labels for recurring rules; never fetch or certify them."""
from urllib.parse import urlparse

from . import links

BASIS = 'recorded_crawl_rule_url_labels_v1'
LIMIT = 5
MAX_URL_CHARS = 4096


def _origin(value):
    if (not isinstance(value, str) or not value or len(value) > MAX_URL_CHARS
            or any(c.isspace() or ord(c) < 32 for c in value)
            or links.has_credential_like_marker(value)):
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None:
            return None
        port = parsed.port
        return parsed.scheme, parsed.hostname.lower(), port if port is not None else (443 if parsed.scheme == 'https' else 80)
    except ValueError:
        return None


def same_origin_label(value, site):
    origin = _origin(site)
    return origin is not None and _origin(value) == origin


def record(samples, key, url):
    sample = samples.setdefault(key, {'basis': BASIS, 'urls': [], 'truncated': False, 'omitted': 0})
    if _origin(url) is None:
        sample['omitted'] += 1
    elif url not in sample['urls']:
        sample['urls'] = sorted(sample['urls'] + [url])
        if len(sample['urls']) > LIMIT:
            sample['urls'].pop()
            sample['truncated'] = True


def read(row, site):
    """Read only supported, consistent same-origin receipts; unknown stays unknown."""
    sample = row.get('url_sample')
    if not isinstance(sample, dict) or set(sample) != {'basis', 'urls', 'truncated', 'omitted'}:
        return None
    urls, omitted, truncated = sample['urls'], sample['omitted'], sample['truncated']
    count = row.get('count', row.get('occurrences', 1))
    if (sample['basis'] != BASIS or not isinstance(urls, list) or len(urls) > LIMIT
            or any(not isinstance(url, str) for url in urls) or len(set(urls)) != len(urls)
            or type(omitted) is not int or omitted < 0 or type(truncated) is not bool
            or not urls and not omitted
            or type(count) is not int or count < len(urls) + omitted or count < 1
            or truncated and (len(urls) != LIMIT or count <= LIMIT + omitted)
            or any(not same_origin_label(url, site) for url in urls)):
        return None
    return {'basis': BASIS, 'urls': list(urls), 'truncated': truncated, 'omitted': omitted}
