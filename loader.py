import csv
import re
from pathlib import Path

ROOT = Path(__file__).parent
FORM_FIELDS = ["stage", "sector", "hq", "founders", "model", "round_size_cr"]
REQUIRED = ["id", "name"] + FORM_FIELDS


class LoadError(Exception):
    pass


def load(path=ROOT / "data" / "applications.csv", decks=ROOT / "decks"):
    """Read applications and attach each deck. Tolerates real-world exports (BOM, stray spaces,
    header case, blank rows); stops with a clear message on a missing column or duplicate id."""
    apps, seen = [], set()
    with open(path, newline="", encoding="utf-8-sig") as f:   # utf-8-sig drops Excel's BOM
        reader = csv.DictReader(f)
        headers = [(h or "").strip().lower() for h in reader.fieldnames or []]
        missing = [c for c in REQUIRED if c not in headers]
        if missing:
            raise LoadError(f"{path}: missing column(s) {missing}; found {headers}")
        for line, raw in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()
                   if isinstance(v, str) or v is None}
            if not any(row.values()):
                continue
            if not row["id"]:
                raise LoadError(f"{path} line {line}: empty id")
            if row["id"] in seen:
                raise LoadError(f"{path} line {line}: duplicate id {row['id']}")
            seen.add(row["id"])
            apps.append(_app(row, Path(decks, row["id"] + ".txt")))
    return apps


def _app(row, deck_file):
    app = {k: row[k] for k in REQUIRED}
    app["form"] = {k: row[k] for k in FORM_FIELDS}       # exactly what the founder wrote, for citations
    app["problems"] = []
    app["round_size_cr"] = _crore(row["round_size_cr"])
    if row["round_size_cr"] and app["round_size_cr"] is None:
        app["problems"].append(f"round size not a number: {row['round_size_cr']!r}")
    if deck_file.exists():
        app["deck"] = deck_file.read_text(encoding="utf-8").strip()
    else:
        app["deck"] = ""
        app["problems"].append(f"no deck file {deck_file.name}")
    return app


def _crore(text):
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group()) if m else None


def filled_fields(app):
    return sum(1 for k in FORM_FIELDS if app["form"][k])
