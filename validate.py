"""
validate.py — how do we know the reclassifier is right, and how often is it wrong?

Method: 60 GW-OTHER refund tickets were sampled at random (seed=42, see
clean.py/reclassify.py for the pipeline that produced the pool they were
drawn from) and hand-labeled by reading customer_message + agent_notes
(gold_labels.csv). This script re-runs the rule engine on those same 60
tickets and reports accuracy against the hand labels.

This is a held-out check in spirit (the rules were written by reading a
DIFFERENT set of ~15 example tickets before this 60-ticket sample was
pulled), but it is not a strict train/test split -- with 5 hours on the
clock, a single honestly-reported sample was the call made here. See the
memo / scope notes for why a larger or continuously-refreshed gold set was
cut.
"""
import pandas as pd
from reclassify import rule_classify

def main():
    gold = pd.read_csv("gold_labels.csv")
    tickets = pd.read_csv("outputs/tickets_clean.csv")
    merged = gold.merge(
        tickets[["ticket_id", "category", "customer_message", "agent_notes"]],
        on="ticket_id", how="left",
    )

    correct = 0
    rows = []
    for _, r in merged.iterrows():
        pred, rationale = rule_classify(r["customer_message"], r["agent_notes"])
        pred_final = pred if pred else "GW-OTHER"
        is_correct = pred_final == r["gold_reason_code"]
        correct += is_correct
        rows.append({
            "ticket_id": r["ticket_id"],
            "gold": r["gold_reason_code"],
            "predicted": pred_final,
            "correct": is_correct,
            "rule_matched": pred is not None,
        })

    report = pd.DataFrame(rows)
    n = len(report)
    acc = correct / n

    print(f"Gold set size: {n}")
    print(f"Rule-engine accuracy: {correct}/{n} = {acc:.1%}")
    print()
    print("Where it's wrong:")
    wrong = report[~report.correct]
    print(wrong.to_string(index=False))
    print()
    print("Accuracy on tickets where a rule fired at all "
          f"({report.rule_matched.sum()}/{n}):",
          f"{report[report.rule_matched].correct.mean():.1%}")
    print("Accuracy on tickets left as default GW-OTHER "
          f"({(~report.rule_matched).sum()}/{n}):",
          f"{report[~report.rule_matched].correct.mean():.1%}" if (~report.rule_matched).any() else "n/a")

    report.to_csv("outputs/validation_report.csv", index=False)

if __name__ == "__main__":
    main()
