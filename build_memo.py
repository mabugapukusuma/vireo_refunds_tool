from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib import colors

styles = getSampleStyleSheet()
body = ParagraphStyle('body', parent=styles['Normal'], fontSize=9, leading=12.6, spaceAfter=5)
h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=15, leading=18, spaceAfter=2, textColor=colors.HexColor('#1a1a1a'))
meta = ParagraphStyle('meta', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor('#555555'), spaceAfter=10)
h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=11.3, leading=14, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor('#0a3d62'))
bullet = ParagraphStyle('bullet', parent=body, leftIndent=12, bulletIndent=0, spaceAfter=4)
small = ParagraphStyle('small', parent=body, fontSize=8.6, leading=11.5, textColor=colors.HexColor('#555555'))

doc = SimpleDocTemplate("outputs/memo_to_arjun.pdf", pagesize=A4,
                         topMargin=12*mm, bottomMargin=10*mm, leftMargin=18*mm, rightMargin=18*mm)

story = []
story.append(Paragraph("Refunds: what was actually going on", h1))
story.append(Paragraph("To: Arjun Mehta, Finance Controller &nbsp;&nbsp;|&nbsp;&nbsp; From: Kabir Nanda &nbsp;&nbsp;|&nbsp;&nbsp; Re: Monthly refund summary by reason and agent", meta))
story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor('#cccccc'), spaceAfter=8))

story.append(Paragraph("1. Why your number and Sameer's didn't match", h2))
story.append(Paragraph(
    "Your export and the helpdesk's own report disagreed because of two data bugs, not because refunds are "
    "out of control. First, tickets migrated from the old support tool (Freshdesk) before September 2025 store "
    "rupee amounts 100x too large in the raw export. Second, 638 tickets got counted twice because they were "
    "re-imported during the migration and now appear under both the old and new systems. Once both are fixed, "
    "18 months of refunds (Jan 2025&ndash;Jun 2026) total <b>Rs 67.1 lakh</b> &mdash; averaging about "
    "<b>Rs 11.2 lakh a quarter</b>, matching the helpdesk's own report almost exactly. Your export summed the "
    "same money multiple times at 100x its real value, which is how it reached a crore.", body))

story.append(Paragraph("2. Refunds aren't rising out of control &mdash; the business is growing", h2))
story.append(Paragraph(
    "Refund value did rise from ~Rs 6.1 lakh in Q1 2025 to ~Rs 16.3 lakh in Q4 2025. But total support tickets "
    "grew just as fast over the same period (1,053 to 2,678 a quarter), and the average refund per ticket "
    "(~Rs 2,700&ndash;3,000) barely moved. The refund rate &mdash; the share of tickets that end in a refund &mdash; "
    "has stayed flat at 18&ndash;22% for six straight quarters. This is volume, not a leak.", body))

story.append(Paragraph("3. The real visibility problem: \u201cOther\u201d was swallowing the answer", h2))
story.append(Paragraph(
    "\u201cGoodwill / Other\u201d is the first option in the agent's dropdown, and it was selected for 42% of all "
    "refunds &mdash; the largest single bucket, and not a genuine answer to \u201cwhat for.\u201d Reading the tickets "
    "themselves, most of these are duplicate payments, cancellations, and delayed return refunds that agents simply "
    "didn't re-tag. I built a small AI-assisted tool that reads each ticket's own text and reassigns it to the "
    "correct reason where the text is clear, and leaves it as goodwill where it genuinely is. That took the "
    "unexplained bucket from 42% of refund value down to 14% (Rs 29.1 lakh \u2192 Rs 9.4 lakh over 18 months). "
    "The full breakdown by reason and by agent is in the attached board_summary.csv.", body))

story.append(Paragraph("4. The one finding that is a real problem", h2))
story.append(Paragraph(
    "Vireo's own policy says a customer should never get both a refund <i>and</i> a replacement unit for the same "
    "order without Finance/Team Lead sign-off. It's happening anyway: 166 tickets over 18 months, and the rate is "
    "climbing &mdash; about 34 tickets a quarter now versus 15 a quarter in early 2025. Refund value alone on these "
    "is Rs 5.7 lakh; including the replacement units sent out alongside, the combined cost is roughly "
    "<b>Rs 1.78 lakh every quarter</b> at the current run rate, more than double where it started. It's spread "
    "across Chat, Logistics and Email Frontline, not one team or agent gaming the system &mdash; it reads as a "
    "process gap (no system check stops a second remedy once a refund is logged), not fraud.", body))

story.append(Paragraph("Business goal", h2))
story.append(Paragraph(
    "<b>Add a system check that blocks a replacement being issued on a ticket that already has a refund (or vice "
    "versa) without explicit Team Lead approval &mdash; cutting this policy-violation rate from ~34 tickets/quarter "
    "toward zero, worth roughly Rs 1.78 lakh a quarter (~Rs 7 lakh a year) in avoided double-cost, on top of closing "
    "a compliance gap.</b>", body))

story.append(Paragraph("What's attached", h2))
items = [
    "board_summary.csv &mdash; refunds by month, agent and (corrected) reason code, ready for the board pack.",
    "refund_by_agent.csv &mdash; per-agent totals. Read raw refund value by agent with care: the Returns Desk and "
    "Billing teams process the large majority of refunds by policy design, so they rank highest by volume alone, "
    "not because of a problem. The more useful per-agent cut is the '% still tagged Other' column.",
    "policy_violations_refund_and_replacement.csv &mdash; the 166 tickets behind finding #4, for Team Lead follow-up.",
]
for it in items:
    story.append(Paragraph(f"&bull; {it}", bullet))

story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor('#dddddd'), spaceAfter=4))
story.append(Paragraph(
    "Caveat: the reclassifier was checked by hand against 59 sampled tickets &mdash; 88% right overall, 94% where "
    "it was confident enough to act. Good enough for a board-level view; not precise enough to cite one agent off "
    "a single ticket without a human reading it first.", small))

doc.build(story)
print("done")