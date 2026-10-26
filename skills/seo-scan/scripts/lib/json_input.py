"""Strict object-key admission for JSON input, without rewriting values."""


class DuplicateKeyError(ValueError):
    """A JSON object repeated a decoded key; never choose a winning value."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError('JSON object contains duplicate keys.')
        result[key] = value
    return result
