import os
from dotenv import load_dotenv

load_dotenv()

OFFLINE = os.getenv("OFFLINE", "1") == "1"
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.0      # the same application must get the same verdicts on every run

CRITERIA = ["stage", "sector", "geography", "founder_profile", "business_model", "round_size"]
VERDICTS = {"match": 1.0, "partial": 0.5, "no-match": 0.0, "insufficient-data": 0.0}

# The thesis as told to the model. Inferred from the Case 3 verdicts in fixtures/;
# replace with the exact wording of the case brief.
THESIS = {
    "stage": "Pre-seed or seed: a working product with early pilots or paying customers",
    "sector": "B2B software that replaces a manual back-office process "
              "(paper registers, spreadsheets, WhatsApp groups, email follow-ups)",
    "geography": "Headquartered in India and selling to Indian customers",
    "founder_profile": "A founder who ran the process they now automate, plus a committed technical co-founder",
    "business_model": "Recurring B2B revenue, ideally annual SaaS contracts",
    "round_size": "Raising roughly Rs 1-10 crore",
}
ANTI_THESIS = ["consumer social", "gaming", "creator economy", "nbfc", "lending licence",
               "lending license", "d2c", "direct to consumer", "crypto", "web3"]

ADVANCE_AT = 7.0       # fit score out of 10 needed to advance to a call
# Pre-screen: an application this thin is sent back to the founder before any AI spend.
MIN_FORM_FIELDS = 3    # filled form fields (of 6)
MIN_DECK_WORDS = 30

COST_CEILING_INR = 20  # per application
QUARTERLY_VOLUME = 380
RETRY_ATTEMPTS = 3

if not OFFLINE and not API_KEY:
    raise SystemExit("GEMINI_API_KEY is not set (or set OFFLINE=1)")
