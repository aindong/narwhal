"""Narrow, bounded diagnostics for expected URL rejections at CLI boundaries."""

from functools import wraps
import sys

from .http import URLInputError

MAX_DETAIL = 512


def url_errors(main):
    """Return usage failure for URL input errors; let other failures propagate."""
    @wraps(main)
    def wrapped(*args, **kwargs):
        try:
            return main(*args, **kwargs)
        except URLInputError as exc:
            detail = ''.join(ch if ch.isprintable() else '\\u{:04x}'.format(ord(ch))
                             for ch in str(exc))
            if len(detail) > MAX_DETAIL:
                detail = detail[:MAX_DETAIL] + '…'
            print('ERROR: URL rejected: ' + detail, file=sys.stderr)
            return 2
    return wrapped
