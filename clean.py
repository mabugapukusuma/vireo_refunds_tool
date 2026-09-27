"""
clean.py — deterministic cleaning of tickets.csv

Two bugs explain why Arjun's export and Sameer's export disagree by ~20x:

1. CURRENCY BUG: legacy Freshdesk rows (source_system == 'legacy_fd') store
   refund_amount_inr in paise-equivalent, i.e. 100x the rupee value used by
   the current helpdesk. Proven directly: for the 638 tickets that exist as
   BOTH a 'helpdesk' row and a 'legacy_fd' row (see bug 2), the legacy row's
   refund_amount_inr is always exactly 100x the helpdesk row's value for the
   same ticket. support-policy.pdf S9 confirms "the legacy tool stored
   monetary values in its own native unit; the current helpdesk stores
   rupees" -- this is that native unit.

2. DUPLICATE-ROW BUG: support-policy.pdf S9 says a subset of legacy tickets
   was re-imported during reconciliation and can appear under both source
   systems. 638 ticket_ids (1,276 rows) appear twice in tickets.csv -- once
   as 'helpdesk', once as 'legacy_fd' -- with identical created_at. Summing
   both counts every one of those refunds twice, on top of bug 1.

Fix order matters: divide legacy amounts by 100 FIRST, then deduplicate by
ticket_id keeping the 'helpdesk' row when both exist (it is the
currently-maintained record; policy S9 implies the helpdesk is authoritative
for anything post-migration).
"""
import pandas as pd

RENAMED_REASON_NOTE = "reason_code_source"  # audit column we add


def load_clean_tickets(path="data/tickets.csv") -> pd.DataFrame:
    t = pd.read_csv(
        path,
        parse_dates=["created_at", "first_response_at", "resolved_at"],
    )

    before_rows = len(t)
    before_refund_sum = t["refund_amount_inr"].sum()

    # --- Bug 1: currency fix -------------------------------------------
    is_legacy = t["source_system"] == "legacy_fd"
    t.loc[is_legacy, "refund_amount_inr"] = t.loc[is_legacy, "refund_amount_inr"] / 100

    # --- Bug 2: de-dup migration re-imports -----------------------------
    # keep 'helpdesk' row over 'legacy_fd' row when a ticket_id has both
    t = t.sort_values("source_system")  # 'helpdesk' < 'legacy_fd' alphabetically
    dup_ticket_ids = t.loc[t["ticket_id"].duplicated(keep=False), "ticket_id"].nunique()
    t = t.drop_duplicates(subset="ticket_id", keep="first").sort_index()

    after_rows = len(t)
    after_refund_sum = t["refund_amount_inr"].sum()

    print(f"[clean] rows: {before_rows} -> {after_rows}  "
          f"(removed {before_rows - after_rows} duplicate rows, "
          f"{dup_ticket_ids} distinct re-imported ticket_ids)")
    print(f"[clean] refund_amount_inr sum: Rs {before_refund_sum:,.0f} -> "
          f"Rs {after_refund_sum:,.0f}  "
          f"({before_refund_sum / after_refund_sum:.1f}x overstatement in the raw export)")

    return t


def flag_policy_violations(t: pd.DataFrame) -> pd.DataFrame:
    """
    support-policy.pdf S5: 'In no case is a customer to receive both a
    refund and a replacement for the same order; where this happens in
    error it must be escalated to the Team Lead and Finance the same day.'
    Flag tickets where both refund_amount_inr is set AND replacement_issued
    == 'Y'. This is a distinct, policy-defined leakage category -- separate
    from normal refund reasons -- and belongs in front of Finance on its own.
    """
    viol = t[(t["refund_amount_inr"].notna()) & (t["replacement_issued"] == "Y")].copy()
    return viol


if __name__ == "__main__":
    t = load_clean_tickets()
    t.to_csv("outputs/tickets_clean.csv", index=False)
    viol = flag_policy_violations(t)
    viol.to_csv("outputs/policy_violations_refund_and_replacement.csv", index=False)
    print(f"[clean] policy-violation tickets (refund + replacement both issued): "
          f"{len(viol)}, total refund value on those tickets: "
          f"Rs {viol['refund_amount_inr'].sum():,.0f}")
