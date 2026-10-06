"""Contrôles ciblés Chat ; aucune réécriture ni sanitization HTML."""
from collections import Counter
from html.parser import HTMLParser
import re


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.tags = set()
        self.counts = Counter()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self.tags.add(tag)
        self.counts[tag] += 1


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


def preserves_block_structure(before: str, after: str) -> bool:
    """Conserve la topologie simple des blocs pour les transformations non synthétiques."""
    try:
        original = _TagCollector()
        original.feed(before)
        original.close()
        candidate = _TagCollector()
        candidate.feed(after)
        candidate.close()
    except (AssertionError, ValueError):
        return False
    return all(original.counts[tag] == candidate.counts[tag] for tag in ("p", "ul", "ol", "li"))


def respects_single_output(text: str) -> bool:
    """Refuse les préambules/variantes typiques interdits par le contrat Chat."""
    if not text or not text.strip():
        return False
    value = text.strip()
    if re.match(r"(?i)^(?:nouvelle\s+version\s+du\s+message\s*:|voici\b)", value):
        return False
    if re.search(r"(?im)^\s*version\s*1\s*:", value) and re.search(
        r"(?im)^\s*version\s*2\s*:", value
    ):
        return False
    return True
