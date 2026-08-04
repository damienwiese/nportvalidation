"""Generate the concise operating runbook and current-state audit PDFs."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
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


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
NAVY = colors.HexColor("#17324D")
TEAL = colors.HexColor("#2B6D73")
INK = colors.HexColor("#283849")
GRID = colors.HexColor("#CDD8E1")
PALE = colors.HexColor("#EEF5F6")
RED = colors.HexColor("#A83221")

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Title2", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24,
                       leading=27, textColor=NAVY, alignment=TA_CENTER, spaceAfter=14)
SUBTITLE = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12, leading=17,
                          textColor=colors.HexColor("#586A7D"), alignment=TA_CENTER)
H1 = ParagraphStyle("H1x", parent=styles["Heading1"], fontSize=16, leading=19,
                    textColor=NAVY, spaceBefore=14, spaceAfter=8)
H2 = ParagraphStyle("H2x", parent=styles["Heading2"], fontSize=11.5, leading=14,
                    textColor=TEAL, spaceBefore=9, spaceAfter=5)
BODY = ParagraphStyle("Bodyx", parent=styles["BodyText"], fontSize=9.4, leading=13.2,
                      textColor=INK, spaceAfter=7)
SMALL = ParagraphStyle("Smallx", parent=BODY, fontSize=8.1, leading=11)
CODE = ParagraphStyle("Codex", parent=BODY, fontName="Courier", fontSize=8.1, leading=11,
                      leftIndent=10, rightIndent=10, borderColor=GRID, borderWidth=0.6,
                      borderPadding=7, backColor=colors.HexColor("#F7FAFB"), spaceBefore=4,
                      spaceAfter=8)
CALLOUT = ParagraphStyle("Callout", parent=BODY, leftIndent=9, rightIndent=9,
                         borderColor=TEAL, borderWidth=1, borderPadding=8,
                         backColor=PALE, spaceBefore=6, spaceAfter=10)
WARN = ParagraphStyle("Warn", parent=CALLOUT, borderColor=RED,
                      backColor=colors.HexColor("#FFF1ED"))


def p(text: str, style=BODY) -> Paragraph:
    return Paragraph(text, style)


def table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[p(x, SMALL) for x in headers]] + [[p(x, SMALL) for x in row] for row in rows]
    out = Table(data, colWidths=[w * inch for w in widths], repeatRows=1, hAlign="LEFT")
    out.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EFF3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, GRID),
    ]))
    return out


def page(canvas, doc):
    canvas.saveState()
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
    return [Spacer(1, 1.45 * inch), p(title, TITLE), p(subtitle, SUBTITLE),
            Spacer(1, 0.3 * inch), p("Operating date: August 4, 2026", SUBTITLE),
            PageBreak()]


def runbook() -> list:
    s = cover("N-PORT Runbook", "One input path, one human-review workbook, one build sequence")
    s += [p("The only monthly input folders", H1),
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
        s += [KeepTogether([p(heading, H2), p(command.replace("\n", "<br/>"), CODE), p(meaning, BODY)])]
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
    return s


def audit() -> list:
    s = cover("N-PORT Final Operating Audit", "What the system uses now, what remains open, and exactly where each issue is fixed")
    s += [p("Executive conclusion", H1),
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
              ["Fund policy", "data/master/fund_registry.csv is absent; fund_config files without policy fields cannot release.", "Per fund: fund_config.txt fields fiscalYearEndMMDD, derivativesRegimePolicy, liquidityRequired, cashB2fRequired, policyEffectiveFrom.", "Enter approved fund facts. The code must not infer them."],
          ], [1.1, 1.7, 2.45, 2.05]),
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
