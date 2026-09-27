"""
summarize.py — build the deliverable Arjun actually asked for:
"monthly summary of refunds by reason code and by agent."

Inputs: outputs/tickets_reclassified.csv (clean + reclassified),
        data/agents.csv (roster, for agent name/team/site/tier)

Outputs (all under outputs/):
  refund_by_month_reason.csv     month x reason_code_final pivot, Rs value + count
  refund_by_agent.csv            per-agent totals + rate, joined to name/team/site
  policy_violations_refund_and_replacement.csv   (from clean.py)
  board_summary.csv              single flat table: the thing that goes in the pack
"""
import pandas as pd

def latest_agent_row(agents: pd.DataFrame) -> pd.DataFrame:
    """
    agents.csv is one row per assignment (an agent can have several rows
    if they changed site/team/shift). For "who is giving away money", we
    want each agent's CURRENT/most recent assignment, not every historical
    one. Keep the row with the latest from_date per agent_id.
    """
    agents = agents.copy()
    agents["from_date"] = pd.to_datetime(agents["from_date"])
    agents = agents.sort_values("from_date")
    return agents.drop_duplicates(subset="agent_id", keep="last")


def main():
    t = pd.read_csv("outputs/tickets_reclassified.csv", parse_dates=["created_at"])
    agents = pd.read_csv("data/agents.csv")
    agents_latest = latest_agent_row(agents)

    refunded = t[t["refund_amount_inr"].notna()].copy()
    refunded["month"] = refunded["created_at"].dt.to_period("M").astype(str)

    # --- 1. month x reason code -----------------------------------------
    by_month_reason = (
        refunded.groupby(["month", "reason_code_final"])
        .agg(refund_inr=("refund_amount_inr", "sum"), tickets=("ticket_id", "count"))
        .reset_index()
        .sort_values(["month", "refund_inr"], ascending=[True, False])
    )
    by_month_reason.to_csv("outputs/refund_by_month_reason.csv", index=False)

    # --- 2. by agent -------------------------------------------------------
    by_agent = (
        refunded.groupby("agent_id")
        .agg(refund_inr=("refund_amount_inr", "sum"), tickets=("ticket_id", "count"))
        .reset_index()
        .merge(agents_latest[["agent_id", "name", "site", "team", "tier"]], on="agent_id", how="left")
        .sort_values("refund_inr", ascending=False)
    )
    # GW-OTHER (still-unexplained goodwill) share per agent -- this is the
    # "who is giving away money with no stated reason" cut Arjun wants
    gw_share = (
        refunded.assign(is_gw=refunded["reason_code_final"] == "GW-OTHER")
        .groupby("agent_id")["is_gw"].mean()
        .rename("pct_tickets_still_gw_other")
        .reset_index()
    )
    by_agent = by_agent.merge(gw_share, on="agent_id", how="left")
    by_agent["pct_tickets_still_gw_other"] = (by_agent["pct_tickets_still_gw_other"] * 100).round(1)
    by_agent.to_csv("outputs/refund_by_agent.csv", index=False)

    # --- 3. flat board-pack table: month x agent x reason -----------------
    board = (
        refunded.groupby(["month", "agent_id", "reason_code_final"])
        .agg(refund_inr=("refund_amount_inr", "sum"), tickets=("ticket_id", "count"))
        .reset_index()
        .merge(agents_latest[["agent_id", "name", "site", "team"]], on="agent_id", how="left")
        .sort_values(["month", "refund_inr"], ascending=[True, False])
    )
    board = board[["month", "agent_id", "name", "site", "team", "reason_code_final", "tickets", "refund_inr"]]
    board.to_csv("outputs/board_summary.csv", index=False)

    print(f"[summarize] total refund value (cleaned, reclassified): Rs {refunded['refund_amount_inr'].sum():,.0f}")
    print(f"[summarize] total refund tickets: {len(refunded)}")
    print(f"[summarize] date range: {refunded['created_at'].min().date()} to {refunded['created_at'].max().date()}")
    print()
    print("Top 5 months by refund value:")
    print(refunded.groupby("month")["refund_amount_inr"].sum().sort_values(ascending=False).head(5))
    print()
    print("By reason code (post-reclassification):")
    rc = refunded.groupby("reason_code_final")["refund_amount_inr"].agg(["sum", "count"]).sort_values("sum", ascending=False)
    print(rc)
    print()
    print("Top 10 agents by refund value:")
    print(by_agent.head(10)[["agent_id", "name", "team", "refund_inr", "tickets", "pct_tickets_still_gw_other"]].to_string(index=False))

if __name__ == "__main__":
    main()
