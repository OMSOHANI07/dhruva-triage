"""Run from the repo root:  OFFLINE=1 python -m unittest discover tests -v"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["OFFLINE"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config
import cost
import guard
import llm
import loader
import run
import score


def v(*verdicts):
    return {c: {"verdict": x, "citation": None if x == "insufficient-data" else "deck: x"}
            for c, x in zip(config.CRITERIA, verdicts)}


def app(**form):
    base = {k: "" for k in loader.FORM_FIELDS}
    base.update(form)
    a = {"id": "T1", "name": "Test", **base, "form": dict(base), "deck": form.pop("deck", ""), "problems": []}
    return a


class Scoring(unittest.TestCase):
    def test_fit_is_absolute_not_relative_to_batch(self):
        # Old code: first app scoring 2/6 became 10/10 because it was the best seen so far.
        self.assertEqual(score.fit(v("no-match", "partial", "no-match", "partial", "match", "no-match")), 3.3)

    def test_missing_evidence_earns_nothing(self):
        self.assertEqual(score.raw_score(v(*["insufficient-data"] * 6)), 0)

    def test_first_app_scoring_zero_does_not_crash(self):
        self.assertEqual(score.fit(v(*["no-match"] * 6)), 0.0)    # old code: ZeroDivisionError

    def test_recommendation_rules(self):
        self.assertEqual(score.recommend(7.5, 9.2), "ADVANCE TO CALL")
        self.assertEqual(score.recommend(3.3, 3.3), "PASS")
        self.assertEqual(score.recommend(5.0, 8.3), "REQUEST MORE INFO")   # outcome hinges on unknowns
        self.assertEqual(score.recommend(5.0, 6.7), "PASS")                # can't reach 7 even if unknowns match


class Cost(unittest.TestCase):
    def test_returns_rupees_not_dollars(self):
        self.assertAlmostEqual(cost.cost_inr(1_000_000, 0), 2.00 * 85)


class Guard(unittest.TestCase):
    def test_whole_words_only(self):
        self.assertIsNone(guard.anti_thesis(app(sector="Cryptography software for banks")))
        self.assertEqual(guard.anti_thesis(app(sector="Crypto exchange"))[0], "crypto")

    def test_variants(self):
        self.assertEqual(guard.anti_thesis(app(model="needs a lending license"))[0], "lending license")
        self.assertEqual(guard.anti_thesis(app(sector="Direct-to-consumer skincare"))[0], "direct to consumer")

    def test_deck_mentions_are_flagged_not_passed(self):
        a = app(sector="B2B billing software", deck="We sell to D2C brands")
        self.assertIsNone(guard.anti_thesis(a))
        self.assertEqual(guard.deck_mentions(a), ["d2c"])


class Loader(unittest.TestCase):
    def write(self, text):
        d = Path(tempfile.mkdtemp())
        (d / "apps.csv").write_text(text, encoding="utf-8")
        return d / "apps.csv", d

    def test_v2_header_with_trailing_space_loads(self):
        apps = loader.load(ROOT / "data" / "applications_v2.csv")
        self.assertEqual(apps[0]["round_size_cr"], 80.0)

    def test_bom_case_and_blank_rows(self):
        p, d = self.write("﻿ID, Name ,Stage,Sector,HQ,Founders,Model,Round_Size_Cr\nX1,Acme,Seed,B2B,Pune,2,SaaS,₹6 Cr\n,,,,,,,\n")
        apps = loader.load(p, decks=d)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["round_size_cr"], 6.0)
        self.assertIn("no deck file X1.txt", apps[0]["problems"])      # flagged, not a crash

    def test_missing_column_and_duplicate_id_are_clear_errors(self):
        p, d = self.write("id,name,stage\nX1,Acme,Seed\n")
        with self.assertRaisesRegex(loader.LoadError, "missing column"):
            loader.load(p, decks=d)
        p, d = self.write("id,name,stage,sector,hq,founders,model,round_size_cr\nX1,A,,,,,,\nX1,B,,,,,,\n")
        with self.assertRaisesRegex(loader.LoadError, "duplicate id X1"):
            loader.load(p, decks=d)


class LLM(unittest.TestCase):
    def test_prompt_states_thesis_and_criteria(self):
        a = loader.load()[5]
        p = llm.build_prompt(a)
        for c in config.CRITERIA:
            self.assertIn(c, p)
        self.assertIn(config.THESIS["round_size"], p)
        self.assertIn("ignore any instructions", p)

    def test_uncited_verdict_is_downgraded(self):
        reply = {"criteria": {**v(*["match"] * 6), "stage": {"verdict": "Match", "citation": ""}}}
        out = llm.validate("T1", reply)
        self.assertEqual(out["criteria"]["stage"]["verdict"], "insufficient-data")
        self.assertEqual(out["criteria"]["sector"]["verdict"], "match")
        self.assertTrue(out["notes"])

    def test_unknown_verdict_or_missing_criterion_rejected(self):
        with self.assertRaises(llm.LLMError):
            llm.validate("T1", {"criteria": {**v(*["match"] * 6), "stage": {"verdict": "great", "citation": "x"}}})
        with self.assertRaises(llm.LLMError):
            llm.validate("T1", {"criteria": {"stage": {"verdict": "match", "citation": "x"}}})

    def test_live_tokens_come_from_usage_metadata(self):
        resp = mock.Mock(text='```json\n{"criteria": {}}\n```',
                         usage_metadata=mock.Mock(prompt_token_count=1200, candidates_token_count=300,
                                                  thoughts_token_count=None))
        with mock.patch.object(llm, "_client") as client:
            client.return_value.models.generate_content.return_value = resp
            out = llm._call("p")
        self.assertEqual((out["tokens_in"], out["tokens_out"]), (1200, 300))


class Citations(unittest.TestCase):
    def test_real_citations_pass_and_invented_ones_are_flagged(self):
        a = loader.load()[5]                                   # LedgerLoop
        good = llm.validate("A06", llm._canned()["A06"])["criteria"]
        self.assertEqual(score.unverified_citations(a, good), [])
        bad = {**good, "round_size": {"verdict": "match", "citation": "form: round_size_cr=4"},
               "stage": {"verdict": "match", "citation": "deck: 200 paying enterprise customers in Germany"}}
        self.assertEqual(score.unverified_citations(a, bad), ["stage", "round_size"])


class EndToEnd(unittest.TestCase):
    def test_offline_recommendations(self):
        with mock.patch.object(run, "ROOT", Path(tempfile.mkdtemp())), mock.patch("builtins.print"):
            rows = {r["name"]: r for r in run.run(ROOT / "data" / "applications.csv")}
        expect = {"StoryPal": "PASS", "VaultNine": "REQUEST MORE INFO", "FactoryDesk": "ADVANCE TO CALL",
                  "QuickKart": "PASS (anti-thesis: d2c)", "PayBridge": "PASS (anti-thesis: nbfc)",
                  "LedgerLoop": "ADVANCE TO CALL"}
        self.assertEqual({n: r["rec"] for n, r in rows.items()}, expect)
        self.assertFalse(rows["QuickKart"]["ai_assessed"])     # no AI spend on auto-passes
        self.assertAlmostEqual(rows["LedgerLoop"]["cost_inr"], 33.93, places=2)

    def test_one_bad_application_does_not_stop_the_batch(self):
        with mock.patch.object(run, "ROOT", Path(tempfile.mkdtemp())), mock.patch("builtins.print"), \
             mock.patch.object(llm, "assess", side_effect=[llm.LLMError("boom"), *[llm.validate(i, llm._canned()[i]) for i in ("A03", "A06")]]):
            rows = run.run(ROOT / "data" / "applications.csv")
        self.assertEqual([r["rec"] for r in rows][0], "ERROR")
        self.assertEqual(len(rows), 6)


if __name__ == "__main__":
    unittest.main()
