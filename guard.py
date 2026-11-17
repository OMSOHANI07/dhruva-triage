import re

import config


def _pattern(term):
    # Whole words only ("crypto" must not hit "cryptography"); a space also matches "-" ("d2c" / "direct-to-consumer").
    words = [re.escape(w) for w in term.split()]
    return re.compile(r"\b" + r"[\s-]+".join(words) + r"\b", re.I)


_PATTERNS = {term: _pattern(term) for term in config.ANTI_THESIS}


def anti_thesis(app):
    """Return (term, field) for the first anti-thesis term in what the company says it IS
    (form sector or business model), or None. These are automatic passes."""
    for field in ("sector", "model"):
        for term, pat in _PATTERNS.items():
            if pat.search(app.get(field) or ""):
                return term, field
    return None


def deck_mentions(app):
    """Anti-thesis terms that appear only in the deck. Flagged for a human, not auto-passed:
    a deck may mention crypto or D2C as a customer or competitor."""
    return [term for term, pat in _PATTERNS.items() if pat.search(app.get("deck") or "")]
