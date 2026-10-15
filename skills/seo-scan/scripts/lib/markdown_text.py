"""Encode literal report text for the limited Markdown presentation layer."""

import re
TABLE_TEXT_MARKER = '<!-- narwhal: escaped-table-cells-v1 -->'
_PUNCTUATION = re.compile(r'([\\`*_\[\]()|<>&~:.@])')


def table_text(value):
    """Keep one literal cell: replace CR/LF breaks and escape Markdown syntax.

    Escape backslashes first through the same substitution, so a literal pipe
    always has an odd escape run. Table splitting removes its one pipe escape;
    opt-in inline rendering decodes the remaining escapes exactly once.
    Precede a generated table with TABLE_TEXT_MARKER for the branded renderer;
    ordinary Markdown readers already understand the punctuation escapes.
    Escape URL prefixes too, so GFM URL autolinks do not consume punctuation
    escapes as literal backslashes in a target. Third-party email autolinking
    after unescaping is outside this encoder's control.
    This changes presentation only, not the underlying JSON evidence.
    """
    text = str(value).replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
    return _PUNCTUATION.sub(r'\\\1', text)
