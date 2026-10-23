"""Literal URL path operations; no decoding, host policy or network access."""


def remove_dot_segments(value):
    """Remove complete dot segments without collapsing repeated separators."""
    segments = []
    parts = value.split('/')
    for index, part in enumerate(parts):
        if part in ('.', '..'):
            if part == '..' and len(segments) > 1:
                segments.pop()
            if index == len(parts) - 1:
                segments.append('')
        else:
            segments.append(part)
    return '/'.join(segments) or '/'
