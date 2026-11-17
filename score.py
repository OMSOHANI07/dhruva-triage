import re

import config


def raw_score(verdicts):
    """Points across the six criteria, 0 to 6. Missing evidence earns nothing."""
    return sum(config.VERDICTS[verdicts[c]["verdict"]] for c in config.CRITERIA)


def missing(verdicts):
    return [c for c in config.CRITERIA if verdicts[c]["verdict"] == "insufficient-data"]


def fit(verdicts):
    """Fit out of 10 against the thesis itself, not against other applicants in the batch."""
    return round(raw_score(verdicts) / len(config.CRITERIA) * 10, 1)


def best_case(verdicts):
    """Fit if every unknown criterion turned out to be a match."""
    return round((raw_score(verdicts) + len(missing(verdicts))) / len(config.CRITERIA) * 10, 1)


def recommend(fit_score, best):
    if fit_score >= config.ADVANCE_AT:
        return "ADVANCE TO CALL"
    if best < config.ADVANCE_AT:
        return "PASS"                  # cannot reach the bar even if every unknown is a match
    return "REQUEST MORE INFO"         # the answer depends on what we don't know yet


def unverified_citations(app, verdicts):
    """Criteria whose citation can't be found in the form or deck: a human should check them.
    'form: field=value' must match that form field; 'deck: quote' must share at least half
    its words and every number with the application text. Commentary after ';' without a
    source prefix is ignored."""
    text = _words(app["deck"] + " " + " ".join(app["form"].values()))
    bad = []
    for c in config.CRITERIA:
        cit = verdicts[c]["citation"]
        if not cit:
            continue
        for piece in cit.split(";"):
            piece = piece.strip()
            src, _, quote = piece.partition(":")
            if src.strip().lower() not in ("form", "deck"):
                continue
            field, eq, value = quote.partition("=")
            if src.strip().lower() == "form" and eq:
                actual = app["form"].get(field.strip().lower(), "")
                ok = bool(value.strip()) and value.strip().lower() in actual.lower()
            else:
                quoted = _words(quote)
                words = [w for w in quoted if len(w) >= 4 and not w.isdigit()]
                numbers_ok = all(n in text for n in quoted if n.isdigit())   # invented figures are the usual fake
                ok = numbers_ok and (not words or sum(w in text for w in words) / len(words) >= 0.5)
            if not ok:
                bad.append(c)
                break
    return bad


def _words(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))
