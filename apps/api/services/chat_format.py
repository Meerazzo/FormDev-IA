"""Contrôles ciblés Chat ; aucune réécriture ni sanitization HTML."""
from html.parser import HTMLParser


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tags = set()

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)


def _tags(text: str) -> set[str]:
    parser = _TagCollector()
    parser.feed(text)
    parser.close()
    return parser.tags


def contains_html(text: str) -> bool:
    try:
        return bool(_tags(text))
    except (AssertionError, ValueError):
        return False


def preserves_format(before: str, after: str) -> bool:
    """Compare des familles de balises, sans certifier la validité du HTML."""
    try:
        original, candidate = _tags(before), _tags(after)
    except (AssertionError, ValueError):
        return False
    if bool(original) != bool(candidate):
        return False
    for family in (
        {"strong", "b"},
        {"em", "i"},
        {"h1", "h2", "h3", "h4", "h5", "h6"},
        {"ul", "ol", "li"},
    ):
        if bool(original & family) != bool(candidate & family):
            return False
    if original & {"ul", "ol", "li"}:
        if not candidate & {"ul", "ol"} or "li" not in candidate:
            return False
    return True
