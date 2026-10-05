"""Restrict Maximo rich text to static formatting before local display."""
from html import escape
from html.parser import HTMLParser

ALLOWED = {"table", "tbody", "thead", "tr", "td", "th", "p", "br", "ul", "ol", "li",
           "b", "strong", "i", "em", "div", "span"}


class _StaticHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skipped = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "object", "svg"}:
            self.skipped += 1
        elif not self.skipped and tag in ALLOWED:
            if tag == "table":
                self.parts.append('<table border="1" cellspacing="0" cellpadding="5">')
            elif tag == "br":
                self.parts.append("<br>")
            else:
                self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "object", "svg"}:
            self.skipped = max(0, self.skipped - 1)
        elif not self.skipped and tag in ALLOWED and tag != "br":
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(escape(data))


def sanitize_detail_html(raw: str) -> str:
    parser = _StaticHTML()
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.parts)
