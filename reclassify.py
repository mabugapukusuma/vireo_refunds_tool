"""
reclassify.py — reclassify GW-OTHER refund tickets into a real reason code
using the free-text customer_message + agent_notes fields.

WHY THIS EXISTS
----------------
GW-OTHER is the FIRST option in the helpdesk's refund-reason dropdown
(support-policy.pdf S5). Across all refunded tickets it is used 42% of the
time -- far more than any genuine "goodwill/other" rate should be. Reading
samples of GW-OTHER tickets shows the free text almost always describes one
of the seven *other* defined reasons (duplicate payment, cancellation,
return-QC refund, lost/damaged in transit, warranty fault, price/coupon
adjustment) -- agents are leaving the dropdown on its default value instead
of picking the specific code. That single UI default is why Arjun cannot
see "who is giving away money and for what": 42% of the money is dumped in
a bucket called "Other".

DESIGN
------
Two-tier classifier, in order to keep this cheap and auditable:

  1. RULE ENGINE (fast, free, deterministic, no API key needed) -- a set of
     keyword/phrase patterns mined directly from real tickets (see the
     PATTERNS list below, each with the ticket text that motivated it).
     Handles the large majority of cases; this is what gets validated
     against gold_labels.csv in validate.py.

  2. LLM ESCALATION (optional, needs ANTHROPIC_API_KEY) -- any ticket the
     rule engine can't confidently place is sent to Claude with the same
     taxonomy and asked to pick one code + a one-line reason, for a human
     to spot-check. This is the fallback for phrasing the rules don't
     cover, not the primary mechanism -- keeping 90%+ of tickets off the
     API keeps this cheap enough to re-run every month.

A ticket that keeps GW-OTHER after both tiers is very likely genuine
goodwill (agent explicitly says "as a gesture", "one-time", issue was
already resolved by troubleshooting, etc.) -- these are the ones actually
worth Arjun's attention as a use-of-discretion story, not a data-quality one.
"""
import os
import re
import sys
import json
import pandas as pd

REASON_CODES = [
    "DOA-REPL", "LOST-TRANSIT", "DUP-PAYMENT", "CANCEL",
    "PRICE-ADJ", "RETURN-QC-OK", "WTY-BUYBACK", "GW-OTHER",
]

REASON_DESCRIPTIONS = {
    "DOA-REPL": "Dead on arrival / wrong or defective item, refund chosen (within 7 days of delivery)",
    "LOST-TRANSIT": "Lost, undelivered, or damaged in transit",
    "DUP-PAYMENT": "Duplicate charge, or payment deducted with no order created",
    "CANCEL": "Customer cancelled before dispatch",
    "PRICE-ADJ": "Price or coupon adjustment",
    "RETURN-QC-OK": "Customer returned the item; refund follows pickup/QC (includes refund-delay-after-return complaints)",
    "WTY-BUYBACK": "In-warranty hardware/functional fault (charging, audio, pairing, display, strap, etc.)",
    "GW-OTHER": "Genuine goodwill / doesn't fit any other code (issue already resolved, refund given as a gesture)",
}

# Each pattern: (compiled regex, reason_code, human-readable rationale)
# Order matters -- first match wins. Mined from manual reading of sampled
# GW-OTHER tickets (see gold_labels.csv for the worked examples).
PATTERNS = [
    (re.compile(r"\b(twice|double|duplicate)\b.*\b(paid|payment|charged|deducted)\b|"
                r"\b(paid|payment|charged|deducted)\b.*\b(twice|double|duplicate)\b", re.I),
     "DUP-PAYMENT", "duplicate/double payment language"),
    (re.compile(r"(amount|payment).{0,20}(deducted|debited).{0,40}(no order|not create|no order id|no confirmation)|"
                r"(no order|not create).{0,40}(deducted|debited)|"
                r"(upi|payment).{0,20}(success|went through).{0,40}(no order|nothing|not (show|reflect))", re.I),
     "DUP-PAYMENT", "payment taken but no order created"),
    (re.compile(r"\bcancel\b", re.I), "CANCEL", "cancellation request"),
    (re.compile(r"\b(promo|coupon|discount|price)\b.{0,30}(invalid|not applied|wrong|adjust)", re.I),
     "PRICE-ADJ", "coupon/price adjustment language"),
    # refund/money-specific "not received" must be checked BEFORE the
    # generic order/product "not received" pattern below, since both use
    # similar words and refund-not-received is the far more common case
    # among GW-OTHER tickets (it's a returns-desk pattern, not logistics).
    (re.compile(r"(pickup|pick-up).{0,30}(not (done|happen)|missed|no ?one showed)|"
                r"(money|refund|amount).{0,30}(hasn'?t|has ?n[o']?t|not).{0,20}"
                r"(come back|credited|receiv|reflect|(in|to) my account|nowhere)|"
                r"(refund|amount).{0,20}(nowhere|pending|delay)|"
                r"where is.{0,10}(the )?money|refund (not|hasn'?t).{0,15}(received|credited)|"
                r"still waiting for (my |the )?refund|refund not (yet )?(received|credited)", re.I),
     "RETURN-QC-OK", "refund-after-return / refund-delay language"),
    (re.compile(r"(lost|missing).{0,20}(transit|courier|shipment)|"
                r"(order|item|product|parcel|delivery).{0,15}(not|n't)\s+(received|delivered)|"
                r"track(ing)?\s+(not updat|stuck)|"
                r"arrived damaged|damaged in transit|received.{0,15}damaged", re.I),
     "LOST-TRANSIT", "non-delivery / damaged-in-transit language"),
    (re.compile(r"wrong (item|product|colour|color)|different (thing|item)|incorrect (item|product)", re.I),
     "DOA-REPL", "wrong/incorrect item on arrival"),
    (re.compile(r"(pair|pairing|bluetooth|connect).{0,30}(fail|not work|drop)|"
                r"(charg|charging).{0,20}(not work|fail|no)|"
                r"(one side|single side).{0,20}(sound|audio|play)|"
                r"(strap|display|screen).{0,20}(broke|peel|unresponsive|crack)|"
                r"not (pairing|charging|working)", re.I),
     "WTY-BUYBACK", "hardware/functional fault language"),
]


def rule_classify(message: str, notes: str) -> tuple[str | None, str]:
    """Return (reason_code_or_None, rationale). None means: send to LLM / leave as GW-OTHER."""
    text = f"{message or ''}\n{notes or ''}"
    for pattern, code, rationale in PATTERNS:
        if pattern.search(text):
            return code, rationale
    return None, "no rule matched"


def llm_classify(message: str, notes: str, category: str, api_key: str | None = None) -> tuple[str, str]:
    """
    Escalate an ambiguous ticket to Claude. Requires ANTHROPIC_API_KEY
    (or pass api_key explicitly). Returns (reason_code, rationale).
    """
    import urllib.request

    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY set. Export it to enable LLM escalation, "
            "e.g.: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    taxonomy = "\n".join(f"- {c}: {d}" for c, d in REASON_DESCRIPTIONS.items())
    prompt = f"""You are classifying a customer-support refund ticket into exactly one reason code.

Reason codes:
{taxonomy}

Ticket category tag: {category}
Customer message: {message}
Agent's closing note: {notes}

Reply with ONLY a JSON object, no other text: {{"reason_code": "<ONE_OF_THE_CODES_ABOVE>", "rationale": "<one short sentence>"}}"""

    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    text = "".join(b["text"] for b in data["content"] if b["type"] == "text")
    text = text.strip().strip("`").removeprefix("json").strip()
    parsed = json.loads(text)
    code = parsed["reason_code"]
    if code not in REASON_CODES:
        code = "GW-OTHER"
    return code, parsed.get("rationale", "")


def reclassify_gw_other(t: pd.DataFrame, use_llm: bool = False, api_key: str | None = None) -> pd.DataFrame:
    """
    For every refunded ticket currently tagged GW-OTHER, try the rule
    engine first. If use_llm is True, anything the rules can't place is
    escalated to the API instead of being left as GW-OTHER.
    Adds two columns: reason_code_final, reclass_method.
    """
    t = t.copy()
    t["reason_code_final"] = t["refund_reason_code"]
    t["reclass_method"] = "original"

    mask = (t["refund_amount_inr"].notna()) & (t["refund_reason_code"] == "GW-OTHER")
    n_total = mask.sum()
    n_rule = n_llm = n_kept = 0

    for idx in t.index[mask]:
        row = t.loc[idx]
        code, rationale = rule_classify(row["customer_message"], row["agent_notes"])
        if code:
            t.at[idx, "reason_code_final"] = code
            t.at[idx, "reclass_method"] = f"rule: {rationale}"
            n_rule += 1
        elif use_llm:
            try:
                code, rationale = llm_classify(
                    row["customer_message"], row["agent_notes"], row["category"], api_key
                )
                t.at[idx, "reason_code_final"] = code
                t.at[idx, "reclass_method"] = f"llm: {rationale}"
                n_llm += 1
            except Exception as e:
                t.at[idx, "reclass_method"] = f"llm_error: {e}"
                n_kept += 1
        else:
            n_kept += 1

    print(f"[reclassify] GW-OTHER tickets: {n_total}")
    print(f"[reclassify]   -> reclassified by rule engine: {n_rule}")
    if use_llm:
        print(f"[reclassify]   -> reclassified by LLM escalation: {n_llm}")
    print(f"[reclassify]   -> left as GW-OTHER (genuine / unresolved): {n_total - n_rule - n_llm}")
    return t


if __name__ == "__main__":
    use_llm = "--llm" in sys.argv
    t = pd.read_csv("outputs/tickets_clean.csv")
    t = reclassify_gw_other(t, use_llm=use_llm)
    t.to_csv("outputs/tickets_reclassified.csv", index=False)
