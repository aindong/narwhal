"""Exclude source template fragments from the document's parsed page facts.

This is a streaming source projection, not a full HTML5 DOM/shadow-root parser.
The original HTML remains on Doc for provenance and bounded markup consumers.
No ordinary hidden/CSS-hidden content or JSON-LD data block is discarded.
"""

from html.parser import HTMLParser


class _Projection(HTMLParser):
    # RCDATA elements cannot open/close a source template. Their literal angle
    # brackets are encoded below so the stdlib HTML shim keeps the same view.
    CDATA_CONTENT_ELEMENTS = ("script", "style", "textarea", "title")

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "template":
            self.depth += 1
        elif not self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if tag == "template":
            # The slash does not close a non-void HTML template. Both optional
            # parser backends must agree rather than treating it as XML.
            self.depth += 1
        elif not self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "template":
            if self.depth:
                self.depth -= 1
        elif not self.depth:
            self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        if not self.depth:
            if self.cdata_elem in {"textarea", "title"}:
                data = data.replace("<", "&lt;").replace(">", "&gt;")
            self.parts.append(data)

    def handle_entityref(self, name):
        self.handle_data("&" + name + ";")

    def handle_charref(self, name):
        self.handle_data("&#" + name + ";")

    def handle_comment(self, data):
        self.handle_data("<!--" + data + "-->")

    def handle_decl(self, decl):
        self.handle_data("<!" + decl + ">")

    def unknown_decl(self, data):
        self.handle_data("<![" + data + "]>")

    def parse_html_declaration(self, index):
        try:
            return super().parse_html_declaration(index)
        except (AssertionError, NotImplementedError):
            # HTMLParser rejects unknown marked declarations. Browsers treat
            # these as bogus comments; preserve that non-content behavior.
            return self.parse_bogus_comment(index)

    def handle_pi(self, data):
        self.handle_data("<?" + data + ">")


def document_source(html):
    """Return the active source view; unchanged source takes the fast path."""
    if "<template" not in html.lower():
        return html
    parser = _Projection()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)
