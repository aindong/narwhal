"""Shared stdlib source parsing policy, not complete HTML5 tree construction."""
from html.parser import HTMLParser


class SourceHTMLParser(HTMLParser):
    """Treat unsupported marked declarations as bogus comments across readers."""

    def parse_html_declaration(self, index):
        try:
            return super().parse_html_declaration(index)
        except (AssertionError, NotImplementedError):
            # Existing document-source projection policy: do not abort every
            # auditor or expose declaration text as markup/content.
            return self.parse_bogus_comment(index)
