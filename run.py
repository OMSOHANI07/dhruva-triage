import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import config
import cost
import guard
import llm
import loader
import score

ROOT = Path(__file__).parent
ORDER = ["ADVANCE TO CALL", "REQUEST MORE INFO", "PASS", "ERROR"]


def triage(app):
    """Assess one application. Free rule checks run first, so the AI is paid for only when needed."""
    row = {"id": app["id"], "name": app["name"], "fit": None, "best_case": None,
           "could_not_establish": [], "flags": list(app["problems"]), "cost_inr": 0.0, "ai_assessed": False}

    hit = guard.anti_thesis(app)
    if hit:
        term, field = hit
        return {**row, "rec": f"PASS (anti-thesis: {term})", "reason": f"form {field} says '{app[field]}'"}

    if loader.filled_fields(app) < config.MIN_FORM_FIELDS and len(app["deck"].split()) < config.MIN_DECK_WORDS:
        return {**row, "rec": "REQUEST MORE INFO",
                "reason": f"application incomplete ({loader.filled_fields(app)}/6 form fields, "
                          f"{len(app['deck'].split())}-word deck); ask the founder before assessing"}

    reply = llm.assess(app["id"], llm.build_prompt(app))
    v = reply["criteria"]
    fit, best = score.fit(v), score.best_case(v)
    inr = cost.cost_inr(reply["tokens_in"], reply["tokens_out"])
    flags = row["flags"] + reply["notes"]
    flags += [f"deck mentions anti-thesis term '{t}': check" for t in guard.deck_mentions(app)]
    flags += [f"citation for {c} not found in form or deck: check" for c in score.unverified_citations(app, v)]
    if inr > config.COST_CEILING_INR:
        flags.append(f"AI cost Rs {inr:.2f} is over the Rs {config.COST_CEILING_INR} ceiling")
    rec = score.recommend(fit, best)
    gaps = score.missing(v)
    reason = f"fit {fit}/10" + (f"; {best}/10 if the unknowns ({', '.join(gaps)}) match" if gaps else "")
    return {**row, "fit": fit, "best_case": best, "rec": rec, "reason": reason, "could_not_establish": gaps,
            "flags": flags, "cost_inr": round(inr, 2), "ai_assessed": True, "criteria": v}


def run(path):
    apps = loader.load(path)
    run_id, at = uuid.uuid4().hex[:8], datetime.now(timezone.utc).isoformat()
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "runs").mkdir(exist_ok=True)
    rows = []
    with open(ROOT / "runs" / "run_log.jsonl", "a") as log:
        for app in apps:
            try:
                r = triage(app)
            except Exception as e:                    # one bad application must not stop the batch
                r = {"id": app["id"], "name": app["name"], "fit": None, "rec": "ERROR",
                     "reason": f"{type(e).__name__}: {e}; triage by hand", "flags": [], "cost_inr": 0.0,
                     "ai_assessed": False, "could_not_establish": []}
            r.update(run_id=run_id, at=at)
            (ROOT / "reports" / f"{app['id']}.json").write_text(json.dumps(r, indent=1))
            log.write(json.dumps({k: v for k, v in r.items() if k != "criteria"}) + "\n")
            log.flush()                               # a crash later keeps the rows already done
            rows.append(r)
    summarise(rows)
    return rows


def summarise(rows):
    print(f"{'application':14}{'fit':>5}  recommendation")
    for r in sorted(rows, key=lambda r: (ORDER.index(r["rec"].split(" (")[0]), -(r["fit"] or 0))):
        fit = "-" if r["fit"] is None else r["fit"]
        print(f"{r['name']:14}{fit:>5}  {r['rec']}  [{r['reason']}]")
        for f in r["flags"]:
            print(f"{'':21}! {f}")
    if not rows:
        return print("no applications")
    assessed = [r for r in rows if r["ai_assessed"]]
    total = sum(r["cost_inr"] for r in rows)
    per_app = total / len(rows)
    print(f"\nAI cost: Rs {total:.2f} for {len(rows)} applications "
          f"({len(assessed)} sent to the AI, {len(rows) - len(assessed)} screened out free)")
    if assessed:
        per_ai = total / len(assessed)
        print(f"  per AI-assessed application: Rs {per_ai:.2f} "
              f"({'OVER' if per_ai > config.COST_CEILING_INR else 'within'} the Rs {config.COST_CEILING_INR} ceiling)")
    print(f"  per application overall:     Rs {per_app:.2f} "
          f"({'OVER' if per_app > config.COST_CEILING_INR else 'within'} the ceiling)")
    print(f"  projected quarter ({config.QUARTERLY_VOLUME} apps at this mix): Rs {per_app * config.QUARTERLY_VOLUME:,.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", default=str(ROOT / "data" / "applications.csv"))
    run(ap.parse_args().apps)
