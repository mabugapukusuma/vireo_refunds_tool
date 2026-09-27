# Vireo Audio — refund summary tool (Task 1 V5, Set C)

Turns 18 months of messy `tickets.csv` into the monthly refund-by-reason-code-by-agent
summary Arjun Mehta asked for, and explains why his export and Sameer's disagreed.

## What this does, in order

1. **`clean.py`** — fixes two data bugs, deterministically, no AI involved:
   - **Currency bug**: legacy (pre-Sep-2025, Freshdesk-migrated) rows store refund amounts
     at 100x the rupee value the current helpdesk uses. Proven by comparing the 638 tickets
     that exist under both systems — the legacy row is always exactly 100x the helpdesk row.
   - **Duplicate-row bug**: those same 638 tickets were re-imported during migration
     reconciliation and appear twice in the export. Deduped, keeping the `helpdesk` row.
   - Also flags the 166 tickets where a customer got **both** a refund and a replacement,
     which `support-policy.pdf` §5 says should never happen without Finance/Team Lead sign-off.
2. **`reclassify.py`** — the AI-assisted part. `GW-OTHER` ("Goodwill / Other") is the first
   option in the refund-reason dropdown and is used on 42% of refunds — reading the tickets,
   most are actually duplicate payments, cancellations, or delayed return refunds that agents
   never re-tagged. This reclassifies them using the ticket's own free text:
   - a **rule engine** (regex patterns mined from real tickets) handles clear-cut phrasing —
     free, instant, no API key required. This is what's checked into the repo and what ran
     for the numbers in the memo.
   - an **optional LLM escalation tier** (`--llm` flag, calls the Anthropic API, needs
     `ANTHROPIC_API_KEY`) is wired up for tickets the rules can't confidently place. Not run
     for this submission — see "What I left out" below.
3. **`validate.py`** — checks the rule engine against 59 hand-labeled tickets
   (`gold_labels.csv`, labeled by reading each ticket myself). Reports accuracy overall and
   split by whether a rule actually fired.
4. **`summarize.py`** — produces the board-pack tables.
5. **`build_memo.py`** — renders the one-page memo to Arjun as a PDF.

## Run it (clean machine)

```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas reportlab pypdf

python3 clean.py        # -> outputs/tickets_clean.csv, policy_violations_refund_and_replacement.csv
python3 reclassify.py   # -> outputs/tickets_reclassified.csv   (add --llm to use the LLM tier, needs ANTHROPIC_API_KEY)
python3 validate.py     # -> outputs/validation_report.csv, prints accuracy
python3 summarize.py    # -> outputs/refund_by_month_reason.csv, refund_by_agent.csv, board_summary.csv
python3 build_memo.py   # -> outputs/memo_to_arjun.pdf
```

No config files, no database — everything reads from `data/*.csv` and writes to `outputs/`.

## The business goal (found in the data, not assumed)

Refund + replacement double-issuance (a defined, zero-tolerance policy violation) is running
at **~34 tickets/quarter**, up from ~15/quarter in early 2025 — a combined cost (refund value
+ replacement unit + reverse/forward shipping) of **~Rs 1.78 lakh/quarter now, ~Rs 7 lakh/year**,
more than double its starting rate. Goal: a system check that blocks a second remedy on a
ticket that already has one, without Team Lead override — cutting this toward zero.

## How I know it works

- Deterministic fixes (currency, dedup) are provable directly from the data: the 638
  duplicated tickets show the exact 100x relationship, so this isn't a guess.
- The reclassifier is checked against `gold_labels.csv`: **88.1% accuracy overall, 94.3% on
  the ~68% of GW-OTHER tickets where a rule actually fired**. The remaining ~32% are left as
  `GW-OTHER` rather than guessed — those are the ones that should go through the LLM tier or
  a human, not the rule engine, and the validation numbers say so explicitly (accuracy drops
  to 33% on exactly that residual group, which is why it's routed differently rather than
  forced through a rule).

## What I left out, and why (5-hour cap)

- **Didn't run the LLM escalation tier live.** No API key is available in the environment I
  built this in ("bring your own tools and keys" — I don't have Kusuma's/Vireo's). The code
  path is written, tested for wiring correctness, and off by default (`--llm` flag); the
  numbers in the memo come entirely from the free rule engine so they don't depend on a key
  existing. Running `--llm` would likely lift the ~32% left as `GW-OTHER` further, at the
  cost of ~317 API calls (one per remaining ticket) — worth doing before a real board
  submission, not worth blocking this one on.
- **Didn't chase the CSAT claim in the email thread.** Priya cites a 0.4-point CSAT rise
  alongside a "stop arguing with customers" policy in Q4 2025; the cleaned data shows CSAT
  flat (3.54 → 3.46) over the same window. Worth a follow-up, but it's a CX-team question,
  not a refund-accounting one, and Arjun didn't ask for it.
- **Didn't build a UI.** Five CSVs and a PDF is what a Finance controller asked to "drop into
  the board pack" needs; a dashboard would have eaten the time budget for a feature nobody
  requested. A small thing that runs beats a large thing that doesn't.
- **Didn't do a full statistically-sized validation set.** 59 tickets, hand-labeled once, not
  cross-checked by a second labeler. Enough to catch the rule engine's real failure modes
  (typos defeating regex, "resolved-then-goodwilled" tickets needing judgment) and to be
  honest about where it's weak — not enough to certify a number Legal would want to stand
  behind unsupervised.
- **Didn't reconcile against `orders.csv`/`customers.csv`** beyond joining for context (unit
  cost, agent roster). A refund-rate-by-product or repeat-refund-customer cut is a natural
  next question but wasn't the one asked.

## Files

```
clean.py, reclassify.py, validate.py, summarize.py, build_memo.py   # pipeline, run in order
gold_labels.csv              # 59 hand-labeled GW-OTHER tickets used by validate.py
data/                        # input CSVs (as provided)
outputs/
  tickets_clean.csv                                  # after currency fix + dedup
  policy_violations_refund_and_replacement.csv        # the 166 double-issuance tickets
  tickets_reclassified.csv                             # after GW-OTHER reclassification
  validation_report.csv                                # gold-set check, row by row
  refund_by_month_reason.csv, refund_by_agent.csv, board_summary.csv   # board-pack tables
  memo_to_arjun.pdf                                    # the one-page memo
```
