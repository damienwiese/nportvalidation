"""Generate the concise operating runbook and current-state audit PDFs."""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field_provenance as provenance  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
# Stable timestamps and document IDs keep repeat generations byte-for-byte reproducible.
rl_config.invariant = 1
NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#2B6D73")
SEA = colors.HexColor("#3FA7A3")
GOLD = colors.HexColor("#E3B341")
INK = colors.HexColor("#283849")
GRID = colors.HexColor("#CDD8E1")
PALE = colors.HexColor("#EEF5F6")
MIST = colors.HexColor("#F5F8FA")
RED = colors.HexColor("#A83221")

styles = getSampleStyleSheet()
COVER_EYEBROW = ParagraphStyle("CoverEyebrow", parent=styles["Normal"], fontName="Helvetica-Bold",
                               fontSize=8.5, leading=11, textColor=GOLD, alignment=TA_CENTER,
                               tracking=1.4, spaceAfter=15)
TITLE = ParagraphStyle("Title2", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=28,
                       leading=31, textColor=colors.white, alignment=TA_CENTER, spaceAfter=16)
SUBTITLE = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, leading=17,
                          textColor=colors.HexColor("#D9E7EC"), alignment=TA_CENTER)
H1 = ParagraphStyle("H1x", parent=styles["Heading1"], fontSize=16, leading=19,
                    textColor=NAVY, spaceBefore=14, spaceAfter=8)
H2 = ParagraphStyle("H2x", parent=styles["Heading2"], fontSize=11.5, leading=14,
                    textColor=TEAL, spaceBefore=9, spaceAfter=5)
BODY = ParagraphStyle("Bodyx", parent=styles["BodyText"], fontSize=9.4, leading=13.2,
                      textColor=INK, spaceAfter=7)
SMALL = ParagraphStyle("Smallx", parent=BODY, fontSize=8.1, leading=11)
TABLE_HEAD = ParagraphStyle("TableHead", parent=SMALL, fontName="Helvetica-Bold",
                            fontSize=7.6, leading=9.5, textColor=colors.white)
CODE = ParagraphStyle("Codex", parent=BODY, fontName="Courier", fontSize=8.1, leading=11,
                      leftIndent=10, rightIndent=10, borderColor=GRID, borderWidth=0.6,
                      borderPadding=7, backColor=colors.HexColor("#F7FAFB"), spaceBefore=4,
                      spaceAfter=8)
CALLOUT = ParagraphStyle("Callout", parent=BODY, leftIndent=9, rightIndent=9,
                         borderColor=TEAL, borderWidth=1, borderPadding=8,
                         backColor=PALE, spaceBefore=6, spaceAfter=10)
WARN = ParagraphStyle("Warn", parent=CALLOUT, borderColor=RED,
                      backColor=colors.HexColor("#FFF1ED"))
STEP_TITLE = ParagraphStyle("StepTitle", parent=H2, fontSize=11, leading=13,
                            spaceBefore=0, spaceAfter=4)
STEP_NUM = ParagraphStyle("StepNum", parent=styles["Normal"], fontName="Helvetica-Bold",
                          fontSize=15, leading=18, textColor=colors.white, alignment=TA_CENTER)
STEP_CODE = ParagraphStyle("StepCode", parent=BODY, fontName="Courier", fontSize=7.8,
                           leading=10.5, textColor=NAVY, backColor=colors.HexColor("#EDF3F6"),
                           borderPadding=5, spaceAfter=5)
STEP_BODY = ParagraphStyle("StepBody", parent=BODY, fontSize=8.7, leading=11.5, spaceAfter=0)
METRIC_NUMBER = ParagraphStyle("MetricNumber", parent=styles["Normal"], fontName="Helvetica-Bold",
                               fontSize=18, leading=20, textColor=NAVY, alignment=TA_CENTER)
METRIC_LABEL = ParagraphStyle("MetricLabel", parent=SMALL, fontSize=7.3, leading=9,
                              textColor=colors.HexColor("#596B7D"), alignment=TA_CENTER)


def p(text: str, style=BODY) -> Paragraph:
    for old, new in {
        "\u2014": " - ", "\u2013": "-", "\u2026": "...", "\u2192": "->",
        "\u00d7": "x", "\u00f7": "/", "\u2011": "-",
    }.items():
        text = text.replace(old, new)
    return Paragraph(text, style)


def table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[p(x, TABLE_HEAD) for x in headers]] + [[p(x, SMALL) for x in row] for row in rows]
    out = Table(data, colWidths=[w * inch for w in widths], repeatRows=1, hAlign="LEFT")
    out.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -1), 0.45, GRID),
        ("BOX", (0, 0), (-1, -1), 0.6, GRID),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, MIST]),
    ]))
    return out


def page(canvas, doc):
    canvas.saveState()
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0, 0.18 * inch, letter[1], fill=1, stroke=0)
        canvas.setFillColor(SEA)
        canvas.circle(7.45 * inch, 9.7 * inch, 0.62 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#21455F"))
        canvas.circle(7.85 * inch, 9.2 * inch, 0.88 * inch, fill=1, stroke=0)
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(2)
        canvas.line(3.45 * inch, 6.0 * inch, 5.05 * inch, 6.0 * inch)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#BFD1D9"))
        canvas.drawCentredString(letter[0] / 2, 0.42 * inch, "CORGI ETF TRUST  /  N-PORT OPERATIONS")
        canvas.restoreState()
        return
    canvas.setFillColor(TEAL)
    canvas.rect(0.55 * inch, 10.48 * inch, 7.4 * inch, 0.055 * inch, fill=1, stroke=0)
    canvas.setStrokeColor(GRID)
    canvas.line(0.55 * inch, 0.46 * inch, 7.95 * inch, 0.46 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#68798A"))
    canvas.drawString(0.55 * inch, 0.28 * inch, "Corgi ETF Trust - N-PORT operating documentation")
    canvas.drawRightString(7.95 * inch, 0.28 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build(path: Path, story: list) -> None:
    doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=0.55 * inch,
                          rightMargin=0.55 * inch, topMargin=0.55 * inch,
                          bottomMargin=0.6 * inch, title=path.stem)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates(PageTemplate(id="clean", frames=[frame], onPage=page))
    doc.build(story)


def cover(title: str, subtitle: str) -> list:
    return [Spacer(1, 1.28 * inch), p("CORGI ETF TRUST  /  OPERATING DOCUMENT", COVER_EYEBROW),
            p(title, TITLE), p(subtitle, SUBTITLE),
            Spacer(1, 0.32 * inch), p("August 4, 2026  |  Controlled operating copy", SUBTITLE),
            PageBreak()]


def metrics(items: list[tuple[str, str]]) -> Table:
    cells = [[p(number, METRIC_NUMBER), p(label, METRIC_LABEL)] for number, label in items]
    out = Table([cells], colWidths=[7.3 * inch / len(cells)] * len(cells), hAlign="LEFT")
    out.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.7, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return out


def step_card(number: str, title: str, command: str, meaning: str) -> Table:
    badge = Table([[p(number, STEP_NUM)]], colWidths=[0.46 * inch], rowHeights=[0.46 * inch])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    content = [p(title, STEP_TITLE), p(command.replace("\n", "<br/>"), STEP_CODE), p(meaning, STEP_BODY)]
    card = Table([[badge, content]], colWidths=[0.65 * inch, 6.65 * inch], hAlign="LEFT")
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.65, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 9),
        ("RIGHTPADDING", (0, 0), (0, 0), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 9),
    ]))
    return card


def trace_appendix() -> list:
    story = [PageBreak(), p("Field-level source trace", H1),
             p("This appendix restores the detailed one-writer map. Every row is generated from the current repository source map and includes a live code anchor. Create/redeem is labeled as a control where applicable; prepared N-PORT XML is not a writer.", CALLOUT)]
    checks = provenance.verify()
    story += [p("Verification: " + "; ".join(checks) + ".", SMALL)]
    grouped: dict[str, list[tuple[str, str, str, str]]] = {}
    for group, field, owner, mechanism, filename, anchor in provenance.ROWS:
        grouped.setdefault(group, []).append((field, owner, mechanism, provenance.ref(filename, anchor)))
    for group, rows in grouped.items():
        for start in range(0, len(rows), 5):
            label = group if start == 0 else f"{group} - continued"
            story += [KeepTogether([p(label, H2), table(
                ["XML field(s)", "Current writer", "How populated", "Code anchor"],
                [list(row) for row in rows[start:start + 5]],
                [1.25, 1.55, 2.9, 1.6],
            )])]
    return story


def runbook() -> list:
    s = cover("N-PORT Runbook", "One input path, one human-review workbook, one build sequence")
    s += [metrics([("3", "RECEIVED INPUT FOLDERS"), ("2", "BLOOMBERG WORKBOOKS"),
                  ("1", "HUMAN-REVIEW WORKBOOK"), ("6", "OPERATING STEPS")]),
          p("The only monthly input folders", H1),
          p("Do not create <b>positions.csv</b>. Put the files already received into these folders.", CALLOUT),
          table(["Input", "Folder", "What it does"], [
              ["Custodian positions", "data/custodian/", "Creates the holdings population and supplies custody position and valuation fields."],
              ["EagleSTAR", "data/fund_accounting/", "Supplies fund-accounting totals, gains, liabilities, flows, and derivative unrealized amounts when present."],
              ["Create/redeem", "data/orders/", "Reconciles EagleSTAR subscription/redemption flows. It is a control; it does not overwrite filing values."],
              ["Bloomberg", "Open the two master workbooks", "Calculates the formulas inserted for returns, durations, and supported security-reference fields."],
              ["Human review", "data/humanreview/&lt;period&gt;_review.xlsx", "Holds residual values automation cannot supply. This is the only manual monthly workbook."],
          ], [1.15, 1.8, 4.35]),
          p("Front-to-end commands", H1)]
    steps = [
        ("1. Load the received files", '& ".\\.venv\\Scripts\\nport.exe" masters 2026-06',
         "The command prints the exact custodian, EagleSTAR, and create/redeem paths selected. Stop if any path is wrong."),
        ("2. Let Bloomberg calculate", "Open data\\master\\security_master.xlsx\nOpen data\\master\\filing_master.xlsx",
         "Use Excel on the Bloomberg machine. Wait for formulas to return values, then save and close both workbooks."),
        ("3. Generate the residual review", '& ".\\.venv\\Scripts\\nport.exe" mergehumanreview 2026-06',
         "Open data\\humanreview\\2026-06_review.xlsx. Fill only the required blank cells reported by the command. Save and close."),
        ("4. Apply human entries", '& ".\\.venv\\Scripts\\nport.exe" mergehumanreview 2026-06',
         "If required blanks are still reported, correct those exact rows and run the same command again."),
        ("5. Write each fund's files", '& ".\\.venv\\Scripts\\nport.exe" split 2026-06',
         "This projects the reviewed masters into data\\funds\\&lt;fund&gt;\\. Do not edit those generated files before the next split."),
        ("6. Build XML", '& ".\\.venv\\Scripts\\nport.exe" build',
         "Builds all funds. For one fund, run: nport build fdrs 2026-06."),
    ]
    for heading, command, meaning in steps:
        number, title = heading.split(". ", 1)
        s += [Spacer(1, 5), KeepTogether([step_card(number, title, command, meaning)])]
    s += [p("What the human actually enters", H1),
          table(["Review sheet", "Human entry", "Rule"], [
              ["swap_legs", "The missing executed swap-leg terms, currently including pmntFloatingRtSpread.", "Use the executed confirmation. Enter 0 only when the actual spread is zero."],
              ["invCountry", "Missing investment country.", "Use the supported security/reference record; do not infer from name."],
              ["option_index", "Missing option reference-index name and identifier.", "Use the actual contract/reference instrument."],
              ["swap_counterparties", "Missing legal counterparty name or LEI.", "Use the executed trade/legal-entity record."],
              ["designated_index", "Fund designated index when applicable.", "Use the fund's approved prospectus/risk policy."],
              ["isin", "Missing ISIN when available.", "Optional when the filing can use another identifier."],
          ], [1.35, 3.15, 2.8]),
          p("Reconciliation flags are different", H1),
          p("A missing review value has a cell in the review workbook. A reconciliation flag means two received sources do not agree or are not aligned. Do not type over the difference in the review workbook. Correct or replace the source file in its input folder, rerun <b>masters</b>, and review the regenerated reconciliation report.", WARN),
          p("Success check", H1),
          p("The run is complete only when the selected input paths are correct, Bloomberg has been saved, required human-review cells are filled, reconciliation REVIEW flags are cleared for the filing, split succeeds, and build produces schema-valid XML.", BODY)]
    s += trace_appendix()
    return s


def audit() -> list:
    s = cover("N-PORT Final Operating Audit", "What the system uses now, what remains open, and exactly where each issue is fixed")
    s += [metrics([("3", "CURRENT SOURCE FILES"), ("58", "SWAP REVIEW GAPS"),
                  ("258", "RECONCILIATION FLAGS"), ("6 DAYS", "TO REPORT DATE")]),
          p("Executive conclusion", H1),
          p("The immediate input error was caused by instructions that required a nonexistent per-fund positions.csv. That was the wrong workflow for this repository. The working monthly path is custodian + EagleSTAR + create/redeem, followed by Bloomberg and one centralized human-review workbook.", CALLOUT),
          p("Current file selection", H1),
          table(["Input", "Selected file", "Observed cutoff", "Role"], [
              ["Custodian", "data/custodian/Corgi_Adv.40C8.C8_ETF_Holdings (1).csv", "2026-06-25", "Filing input"],
              ["EagleSTAR", "data/fund_accounting/takeout-20260625T000453Z-3-001.zip", "2026-06-24", "Filing input"],
              ["Create/redeem", "data/orders/HistoricalOrders (83).csv", "through 2026-06-24", "Reconciliation control"],
              ["Report date", "2026-06 filing", "2026-06-30", "Target"],
          ], [1.05, 3.15, 1.05, 1.55]),
          p("Time-series finding", H1),
          p("The current sources are not period-end aligned: custody is June 25, EagleSTAR is June 24, create/redeem ends June 24, and the filing date is June 30. Therefore the current numerical differences are not a valid final apples-to-apples period-end comparison. They remain open until period-end files are loaded or the filing period is changed to match the source cutoff.", WARN),
          p("Current open items", H1),
          table(["Open item", "Measured state", "Exact place to fix", "Resolution"], [
              ["Swap payment-leg spread", "58 of 58 swap review rows are blank for pmntFloatingRtSpread.", "data/humanreview/2026-06_review.xlsx -> swap_legs -> pmntFloatingRtSpread", "Enter the actual spread from each executed swap confirmation; then rerun mergehumanreview."],
              ["Flow reconciliation", "238 REVIEW rows: 216 sales and 22 redemptions across mon1-mon3.", "Replace/update data/orders/ and/or data/fund_accounting/; then rerun masters.", "Align both sources to the same report cutoff and investigate remaining differences. Do not overwrite EagleSTAR filing values with order-book values."],
              ["Net-assets reconciliation", "19 REVIEW rows.", "Replace/update data/custodian/ and/or data/fund_accounting/; then rerun masters.", "Use matching as-of dates first; investigate only the residual breaks."],
              ["Liability reconciliation", "1 REVIEW row.", "Correct the EagleSTAR mapping/source in data/fund_accounting/ or the accounting adapter; then rerun masters.", "Confirm mapped payable accounts equal the EagleSTAR total-liabilities control."],
          ], [1.1, 1.7, 2.45, 2.05]),
          KeepTogether([p("Fund policy release gap", H2),
          p("<b>Measured state:</b> data/master/fund_registry.csv is absent, and fund_config files without policy fields cannot release.<br/><b>Exact place to fix:</b> per fund, enter fiscalYearEndMMDD, derivativesRegimePolicy, liquidityRequired, cashB2fRequired, and policyEffectiveFrom in fund_config.txt.<br/><b>Rule:</b> enter approved fund facts; the code must not infer them.", WARN)]),
          p("Meaning of missing versus blocking", H1),
          table(["Term", "Meaning", "Action"], [
              ["Missing", "An applicable value is absent and the system has a known entry location.", "Enter it in the named human-review cell or correct the named input."],
              ["Blocking", "The system must not release XML because an applicable value, policy fact, reconciliation, or validation is unresolved.", "Resolve the underlying issue. A blocker is a state, not a separate file type."],
              ["Reconciliation REVIEW", "Two controls disagree or their dates are not aligned.", "Fix/replace source inputs and rerun. It is not a blank field to type over."],
          ], [1.15, 3.1, 3.15]),
          p("Verified operating boundary", H1),
          p("Prepared N-PORT XML and other reference filings remain comparison-only. The restored masters command no longer reads data/RealXMLs. Create/redeem orders remain a control only. The command prints selected inputs before writing, which makes an accidental file selection visible.", BODY),
          KeepTogether([p("Remaining engineering gap", H1),
          p("The monthly human-review workbook centralizes residual security and derivative fields, but fund policy is still stored per fund and reconciliation exceptions are still resolved upstream. That is the current code behavior. It would be inaccurate to claim every blocker can be cleared inside the human-review workbook today.", WARN)])]
    return s


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    build(DOCS / "NPORT_Runbook.pdf", runbook())
    build(DOCS / "US_Bank_NPORT_Comprehensive_Final_Audit_2026-08-03.pdf", audit())


if __name__ == "__main__":
    main()
