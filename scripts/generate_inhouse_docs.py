"""Generate the source-independent N-PORT audit and field-level runbook HTML."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

import field_provenance as provenance
import runbook_traceability as legacy_trace

from nport.config import _CONFIG_KEY_MAP, _FILING_KEY_MAP, _HOLDINGS_KEY_MAP
from nport.schema import FIELD_BY_NAME


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TODAY = date(2026, 8, 3)


CSS = """
@page { size: Letter; margin: 0.55in 0.55in 0.6in; }
* { box-sizing: border-box; }
body { margin: 0; color: #243449; font: 10.2pt/1.38 Arial, Helvetica, sans-serif; }
h1 { margin: 0 0 8px; color: #17324d; font-size: 25pt; line-height: 1.05; }
h2 { margin: 24px 0 9px; padding-bottom: 5px; border-bottom: 2px solid #2b6d73; color: #17324d; font-size: 17pt; break-after: avoid; }
h3 { margin: 15px 0 6px; color: #244f64; font-size: 12.5pt; break-after: avoid; }
p { margin: 5px 0 9px; }
ul, ol { margin: 5px 0 10px 20px; padding: 0; }
li { margin: 3px 0; }
code { font: 8.5pt Consolas, monospace; color: #163a50; overflow-wrap: anywhere; }
.cover { min-height: 8.2in; display: flex; flex-direction: column; justify-content: center; page-break-after: always; }
.eyebrow { color: #2b6d73; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.subtitle { max-width: 6.8in; color: #536477; font-size: 13pt; }
.stamp { margin-top: 24px; color: #69788a; }
.callout { margin: 10px 0; padding: 10px 12px; border-left: 5px solid #2b6d73; background: #eef5f6; break-inside: avoid; }
.danger { border-color: #b33a24; background: #fff0ec; }
.good { border-color: #2d7655; background: #edf7f1; }
.muted { color: #667688; }
.small { font-size: 8.6pt; }
.page { page-break-before: always; }
.keep { break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: 7px 0 14px; table-layout: fixed; }
th { padding: 7px 7px; text-align: left; color: #17324d; background: #ffffff; border-top: 1px solid #7f9dad; border-bottom: 2px solid #7f9dad; font-size: 8.4pt; text-transform: uppercase; }
td { padding: 6px 7px; vertical-align: top; border-bottom: 1px solid #d4dde6; overflow-wrap: anywhere; }
tr { break-inside: avoid; }
.table-block { break-inside: avoid; page-break-inside: avoid; margin-bottom: 11px; }
.table-block table { margin: 0; }
.continued { margin: 2px 0 5px; color: #536b7d; font-size: 9.5pt; }
.dense { font-size: 8.1pt; line-height: 1.28; }
.dense th, .dense td { padding: 4.5px 5px; }
.dense code { font-size: 7.2pt; line-height: 1.15; overflow-wrap: anywhere; white-space: normal; }
.steps { margin: 8px 0 14px; }
.step { margin: 0 0 10px; padding: 10px 12px; border: 1px solid #c9d7df; break-inside: avoid; }
.step h3 { margin: 0 0 5px; }
.label { display: inline-block; min-width: 0.72in; color: #17324d; font-weight: 700; }
.cmd { margin: 6px 0; padding: 7px 9px; border: 1px solid #cbd5df; background: #f7fafb; font: 8pt/1.35 Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; page-break-inside: avoid; }
.id { width: .55in; font-weight: 700; color: #2b6d73; }
.status { font-weight: 700; }
.blocked { color: #a72e1c; }
.review { color: #9a5b00; }
.ok { color: #24704e; }
.tag { display: inline-block; padding: 2px 6px; border-radius: 10px; font-size: 7.5pt; font-weight: 700; background: #dfe9ef; }
.footer-note { margin-top: 16px; padding-top: 7px; border-top: 1px solid #cbd5df; color: #69788a; font-size: 8pt; }
"""


def shell(title: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>{CSS}</style></head><body>
<section class="cover"><div class="eyebrow">Corgi ETF Trust · N-PORT in-house service</div>
<h1>{escape(title)}</h1><p class="subtitle">{escape(subtitle)}</p>
<p class="stamp">As of August 3, 2026 · Source boundary corrected</p>
<div class="callout danger"><b>Controlling rule:</b> no file, value, mapping, or pre-fill delivered by U.S. Bank may populate the in-house filing. Those artifacts are read-only comparison evidence.</div>
</section>{body}<p class="footer-note">Generated from the repository field contracts and source controls on {TODAY.isoformat()}.</p>
</body></html>"""


def t(headers: list[str], rows: list[list[str]], widths: list[str] | None = None, cls: str = "") -> str:
    cg = ""
    if widths:
        cg = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in widths) + "</colgroup>"
    head = "".join(f"<th>{h}</th>" for h in headers)
    content = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<table class="{cls}">{cg}<thead><tr>{head}</tr></thead><tbody>{content}</tbody></table>'


def chunked_t(
    headers: list[str], rows: list[list[str]], widths: list[str] | None = None,
    cls: str = "", chunk_size: int = 4, chunk_label: str | None = None,
    label_first: bool = False,
) -> str:
    """Render small complete tables so no logical table is split across PDF pages."""
    blocks = []
    for start in range(0, len(rows), chunk_size):
        label = ""
        if chunk_label and (label_first or start > 0):
            suffix = "" if start == 0 else " (continued)"
            label = f'<h3 class="continued">{escape(chunk_label + suffix)}</h3>'
        block = t(headers, rows[start:start + chunk_size], widths, cls)
        blocks.append(f'<div class="table-block">{label}{block}</div>')
    return "".join(blocks)


def code(value: str) -> str:
    return f"<code>{escape(value)}</code>"


def effect(field: str, section: str) -> str:
    optional = {
        "regStreet2", "isin", "lei", "ticker", "exchangeRt", "issuerConditionalDesc",
        "assetConditionalDesc", "otherDesc", "otherValue", "liquidityCircumstancesJson",
    }
    conditional_prefixes = (
        "curMetrics", "creditSprd", "deriv", "median", "backtesting", "cashNot",
        "monthlyReturn", "maturity", "coupon", "annualized", "isDefault", "areIntrst",
        "isPaid", "counterparty", "unrealized", "putOrCall", "writtenOrPur", "shareNo",
        "exercise", "expDt", "delta", "ref", "swap", "termination", "upfront", "pmnt",
        "rcpt", "notional", "rec", "payoffProfDeriv", "otherDeriv", "liquidity",
    )
    if field in optional:
        return "Optional or alternative-ID path; review before omission"
    if section != "config" and field.startswith(conditional_prefixes):
        return "Blocks when the field/section is applicable"
    return "Blocks when absent, invalid, stale, or unapproved"


def filing_source(field: str) -> tuple[str, str]:
    if field in {"submissionType", "repPdEnd", "repPdDate", "derivativesRegime"}:
        return "Approved fund policy in the fund review", "System-derived after the policy rows are approved"
    if field in {"liveTestFlag", "isFinalFiling", "dateSigned"}:
        return "Filing operations / authorized signatory", "FundFields sheet; retain the independent evidence reference"
    if field in {"totAssets", "totLiabs", "netAssets", "assetsAttrMiscSec", "assetsInvested"} or field.startswith("amtPay") or field in {"delayDeliv", "standByCommit", "liquidPref", "isNonCashCollateral"}:
        return "Internal GL, NAV close, and accounting subledgers", "FundFields sheet; enter the supported value and source ID"
    if field.startswith("rtn") or field.startswith("netRealized") or field.startswith("netUnrealized"):
        return "Internal performance/accounting calculation", "FundFields sheet; reviewer confirms value and cutoff"
    if field.startswith("mon"):
        return "Internal create/redeem export reconciled to GL/transfer agent", "FundFields sheet; sales/redemptions can be calculated from --orders"
    if field in {"nameDesignatedIndex", "indexIdentifier"}:
        return "Approved prospectus/497K and risk policy", "FundFields sheet; required for relative VaR"
    if field in {"curMetricsJson", "creditSprdRiskIgJson", "creditSprdRiskNonigJson"}:
        return "Internal risk calculation using independent positions", "FundFields sheet; value or supported NOT_APPLICABLE disposition"
    if field == "cashNotReportedInCOrD":
        return "Internal cash ledger", "FundFields sheet; value or supported NOT_APPLICABLE disposition"
    if field.startswith("deriv") or field.startswith("median") or field == "backtestingExceptions":
        return "Internal Rule 18f-4 / VaR calculation", "FundFields sheet; value or supported NOT_APPLICABLE disposition"
    return "Approved internal filing calculation", "FundFields sheet with source, cutoff, reviewer, and time"


def holding_source(field: str) -> tuple[str, str]:
    if field in {"name", "title", "cusip", "ticker", "balance", "units", "curCd", "valUSD"}:
        return "Internal OMS/IBOR position close plus approved security master", "System feed; do not recreate manually"
    if field == "pctVal":
        return "Derived from valUSD / approved netAssets", "System-derived; reconciliation must tie denominator"
    if field in {"lei", "isin", "invCountry"}:
        sheet = {"lei": "no complete current sheet", "isin": "isin", "invCountry": "invCountry"}[field]
        return "Approved internal security master / licensed reference data", f"Exception review: {sheet} sheet; source evidence required"
    if field in {"assetCat", "issuerCat", "payoffProfile", "fairValLevel", "isRestrictedSec", "isCashCollateral", "isNonCashCollateral", "isLoanByFund"}:
        return "Internal classification engine plus accounting/risk policy", "System mapping; human reviews exceptions, not bulk population"
    if field.startswith("liquidity"):
        return "Internal liquidity risk program", "HoldingFields sheet; one row per applicable holding field"
    if field in {"maturityDt", "couponKind", "annualizedRt", "isDefault", "areIntrstPmntsInArrs", "isPaidKind"}:
        return "Internal security master, issuer events, and debt operations", "HoldingFields sheet when the debt field is present or required"
    if field in {"counterpartyName", "counterpartyLei"}:
        return "Internal trade record / legal entity record", "HoldingFields sheet keyed by holding record"
    if field in {"pmntFloatingRtIndex", "pmntFloatingRtSpread", "pmntRateTenor", "pmntRateUnit", "recFixedOrFloating", "recDesc"}:
        return "Executed swap confirmation / internal trade record", "HoldingFields sheet keyed by holding record"
    if field in {"delta"}:
        return "Internal risk result or licensed market data at report cutoff", "HoldingFields sheet keyed by holding record"
    if field in {"refIndexName", "refIndexIdentifier"}:
        return "Internal trade record / approved reference master", "HoldingFields sheet keyed by holding record"
    if field.startswith(("put", "written", "share", "exercise", "exp", "ref", "swap", "termination", "upfront", "pmnt", "rcpt", "notional", "rec", "unrealized", "payoffProfDeriv", "otherDeriv")) or field == "derivCat":
        return "Internal trade records, confirmations, and risk valuation", "HoldingFields sheet keyed by holding record"
    return "Independent internal position/reference source", "HoldingFields sheet when review is required"


def field_rows() -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    config_rows = []
    for key in _CONFIG_KEY_MAP:
        if key == "requiredSources":
            continue
        config_rows.append([
            code(key), code(f"FundFields / fund_config.txt / {key}"),
            "Internal legal, entity, signer, or policy record", effect(key, "config"),
        ])
    filing_rows = []
    for key in _FILING_KEY_MAP:
        source, _review = filing_source(key)
        filing_rows.append([
            code(key), code(f"FundFields / filing_data.txt / {key}"),
            source, effect(key, "filing"),
        ])
    holding_rows = []
    for key in _HOLDINGS_KEY_MAP:
        source, _review = holding_source(key)
        holding_rows.append([
            code(key), code(f"HoldingFields / <holding> / {key}"),
            source, effect(key, "holding"),
        ])
    return config_rows, filing_rows, holding_rows


def _safe_ref(filename: str, pattern: str, fallback_pattern: str) -> str:
    """Resolve a live code line without inventing a citation when a field has no writer."""
    try:
        return provenance.ref(filename, pattern)
    except SystemExit:
        return provenance.ref(filename, fallback_pattern)


def _legacy_code_ref(kind: str, external: str, internal: str, source: str) -> str:
    """Return the code location that writes, derives, or merely accepts the field."""
    import re

    if kind == "config":
        return provenance.ref("config.py", r"def parse_config")
    if "Bloomberg" in source:
        if kind == "holding":
            return _safe_ref("master_sheet.py", rf'"{re.escape(external)}"', r"_BBG_FORMULA_COLUMNS")
        return _safe_ref("filing_master.py", rf'"{re.escape(external)}"', r"^RETURN_COLS|^_RISK_BDP_FIELDS")
    if "EagleSTAR" in source:
        return _safe_ref("eaglestar.py", rf'\["{re.escape(external)}"\]', r"def filing_values|def derivative_values")
    if "custodian" in source.lower():
        return _safe_ref("custodian.py", rf'"{re.escape(external)}"', r"def transform_to_holding_dict")
    if "Human-review" in source or "human-review" in source:
        return _safe_ref("master_sheet.py", rf'\["{re.escape(external)}"\]', r"def apply_review_to_rows")
    if "Builder fallback" in source:
        return _safe_ref("builder.py", rf'"{re.escape(external)}"', r"def _add_derivative")
    if "No current feed" in source or "No verified automated writer" in source or "Manual value" in source:
        return _safe_ref("models.py", rf"^\s+{re.escape(internal)}:", r"class FilingData|class Holding")
    if kind == "filing":
        if external == "liveTestFlag":
            return provenance.ref("cli.py", r"def _live_gate_reasons")
        if external in {"repPdEnd", "repPdDate"}:
            return provenance.ref("custodian.py", r"def _period_end_date")
        if external == "dateSigned":
            return provenance.ref("filing_master.py", r"def _signed_date")
        return _safe_ref("filing_master.py", rf'"{re.escape(external)}"', r"^_CONST|^_ZERO_FIELDS|^_NA_FIELDS")
    return _safe_ref("custodian.py", rf'"{re.escape(external)}"', r"def transform_to_holding_dict")


def _exact_holding_legacy(external: str, internal: str, group: str) -> tuple[str, str]:
    """Describe the disabled legacy holding writer without implying production approval."""
    custodian_direct = {
        "name", "title", "cusip", "ticker", "balance", "payoffProfile", "putOrCall",
        "writtenOrPur", "exercisePrice", "expDt", "terminationDt", "notionalAmt",
        "refCusip", "refIssuerName", "refIssueTitle",
    }
    tool_values = {
        "units", "curCd", "assetCat", "issuerCat", "isRestrictedSec", "fairValLevel",
        "isCashCollateral", "isNonCashCollateral", "isLoanByFund", "isDefault",
        "areIntrstPmntsInArrs", "isPaidKind", "derivCat", "shareNo",
        "exercisePriceCurCd", "refInstType", "swapFlag", "swapCurCd",
        "pmntFixedOrFloating", "pmntCurCdLeg",
    }
    no_writer = {
        "assetConditionalDesc", "exchangeRt", "recFixedRt", "recFloatingRtIndex",
        "recFloatingRtSpread", "recPmntAmt", "recCurCd", "recRateTenor", "recRateUnit",
        "recResetDt", "recResetUnit", "pmntDesc", "pmntFixedRt", "pmntPmntAmt",
        "pmntResetDt", "pmntResetUnit", "payoffProfDeriv", "otherDerivDesc",
        "liquidityClassificationJson", "liquidityCircumstancesJson",
    }
    human_overlay = {
        "refIndexName", "refIndexIdentifier", "recFixedOrFloating", "recDesc",
        "pmntFloatingRtIndex", "pmntFloatingRtSpread", "pmntRateTenor", "pmntRateUnit",
    }
    if external == "valUSD":
        return (
            "U.S. Bank custodian CSV for non-swaps; EagleSTAR PVal for swaps",
            "MarketValue is used for non-swaps; swap value is replaced with matched unrealized PVal.",
        )
    if external == "pctVal":
        return (
            "Derived from filed valUSD and filed netAssets",
            "The legacy transform recalculates the percentage after accounting overrides.",
        )
    if external in {"lei", "isin", "invCountry"}:
        return (
            "Bloomberg workbook formula for conventional securities; explicit constants on some derivative/UST paths",
            "BDP enrichment owns conventional-security values; custodian code sets N/A/US or the U.S. Treasury LEI on identified special paths.",
        )
    if external in {"maturityDt", "couponKind", "annualizedRt"}:
        return (
            "Bloomberg workbook formula; U.S. Treasury name parser exists in the direct custodian transform",
            "Corporate/debt master enrichment uses BDP; the alternate direct Treasury path parses coupon and maturity from SecurityName.",
        )
    if external in {"counterpartyName", "counterpartyLei"}:
        return (
            "Seeded human-review overlay for swaps; OCC tool constant for options",
            "Swap values come from the legacy counterparty sheet; option values use the OCC constants in custodian.py.",
        )
    if external == "unrealizedAppr":
        return (
            "Gmail export - U.S. Bank EagleSTAR PVal attachment",
            "Matched by Primary Asset ID and written as the derivative unrealized amount.",
        )
    if external == "delta":
        return (
            "Manual value preserved in security_master.xlsx; no automated feed",
            "The legacy master preserves the workbook cell; it does not calculate or source delta.",
        )
    if external in {"refIsin", "refTicker"}:
        return (
            "Bloomberg workbook formula on the reference security",
            "BDP enrichment uses the reference CUSIP/security key.",
        )
    if external in human_overlay:
        return (
            "Seeded legacy human-review workbook overlay",
            "master_sheet.py copies the reviewed/seeded workbook value when present; the old workbook lacks mandatory reviewer/time/evidence fields.",
        )
    if external in {"upfrontPmnt", "upfrontRcpt"}:
        return (
            "Builder fallback, not a sourced legacy field",
            "builder.py emits 0 when the accepted holding column is blank.",
        )
    if external in {"pmntCurCd", "rcptCurCd"}:
        return (
            "Builder fallback, not a sourced legacy field",
            "builder.py uses the holding currency when the accepted holding column is blank.",
        )
    if external == "issuerConditionalDesc":
        return (
            "Tool constant only on the legacy swap path; otherwise no verified writer",
            "custodian.py sets N/A for swaps; other issuerCat=OTHER cases are not populated automatically.",
        )
    if external in {"otherDesc", "otherValue"}:
        return (
            "Tool-generated identifier only for legacy option/swap paths",
            "custodian.py writes USER DEFINED plus an internally constructed option/swap identifier; other paths remain blank.",
        )
    if external in no_writer:
        return (
            "No verified automated writer in the legacy pipeline",
            "The canonical model accepts the field and validation/builder may use it, but no legacy intake adapter supplies it.",
        )
    if external in tool_values:
        return (
            "Tool constant or classification in custodian.py",
            "The legacy custodian transform assigns the value according to its holding-type branch.",
        )
    if external in custodian_direct:
        return (
            "U.S. Bank custodian CSV",
            "The legacy custodian transform copies or parses the value from the custody row.",
        )
    return (
        "No verified automated writer in the legacy pipeline",
        "The field is accepted by the canonical model, but the legacy writer is not established by the traced code.",
    )


def _new_review_location(kind: str, external: str, internal: str = "") -> str:
    if kind == "config":
        if external == "requiredSources":
            return "System-derived from APPROVED rows on Sources; the reviewer does not type it."
        return (
            f"FundFields: targetFile=fund_config.txt, recordKey=FUND, fieldName={external}. "
            "Enter proposedValue and cite an approved independent Sources row."
        )
    if kind == "filing":
        if external in {"submissionType", "repPdEnd", "repPdDate", "derivativesRegime"}:
            return "SYSTEM_DERIVED after the period and approved fund-policy rows pass review."
        if external == "liveTestFlag":
            return "SYSTEM_CONTROL; remains TEST until all release controls pass."
        return (
            f"FundFields: targetFile=filing_data.txt, recordKey=FUND, fieldName={external}. "
            "Use APPROVED or a supported NOT_APPLICABLE disposition."
        )
    spec = FIELD_BY_NAME[internal]
    return (
        f"Base value is positions.csv column {external}. If missing or review-sensitive, use "
        f"HoldingFields: recordKey=<holding>, fieldName={external}. Requirement: "
        f"{spec.required}{' - ' + spec.condition if spec.condition else ''}."
    )


def trace_rows() -> tuple[list[list[str]], list[list[str]], list[list[str]], list[str]]:
    """Build an exhaustive, code-located trace for every accepted canonical field."""
    checks = provenance.verify()
    config_rows: list[list[str]] = []
    filing_rows: list[list[str]] = []
    holding_rows: list[list[str]] = []

    for external, internal in _CONFIG_KEY_MAP.items():
        source, transform, _control = legacy_trace.config_source(internal)
        config_rows.append([
            code(external), source,
            f"{transform}<br>{code(_legacy_code_ref('config', external, internal, source))}",
            _new_review_location("config", external, internal),
        ])
    for external, internal in _FILING_KEY_MAP.items():
        source, transform, _control = legacy_trace.filing_source(internal)
        filing_rows.append([
            code(external), source,
            f"{transform}<br>{code(_legacy_code_ref('filing', external, internal, source))}",
            _new_review_location("filing", external, internal),
        ])
    for external, internal in _HOLDINGS_KEY_MAP.items():
        spec = FIELD_BY_NAME[internal]
        source, transform = _exact_holding_legacy(external, internal, spec.group)
        holding_rows.append([
            code(external), source,
            f"{transform}<br>{code(_legacy_code_ref('holding', external, internal, source))}",
            _new_review_location("holding", external, internal),
        ])

    expected = (len(_CONFIG_KEY_MAP), len(_FILING_KEY_MAP), len(_HOLDINGS_KEY_MAP))
    actual = (len(config_rows), len(filing_rows), len(holding_rows))
    if actual != expected:
        raise RuntimeError(f"field trace incomplete: expected {expected}, got {actual}")
    checks.append(
        f"Exhaustive canonical trace: {sum(actual)} fields "
        f"({actual[0]} config, {actual[1]} filing, {actual[2]} holding)"
    )
    return config_rows, filing_rows, holding_rows, checks


GAPS = [
    ["G-001", '<span class="status blocked">DATA BLOCKER</span>', "Independent position population",
     "All Part C holdings, including GPTZ if the fund owns it",
     code("prepare-review <fund> <period> --positions <independent.csv>") + "; review surfaced rows in HoldingFields.",
     "Operations", "Approved POSITIONS row, period-end cutoff, hash, row count, and position-count reconciliation"],
    ["G-002", '<span class="status blocked">DATA BLOCKER</span>', "Independent fund-accounting close",
     "Assets, liabilities, net assets, balance-sheet items, gains, returns, and cash",
     "Add the internal close file to Sources; enter supported values in FundFields where targetFile=filing_data.txt.",
     "Fund Accounting", "Each row cites the approved source; NAV equation passes"],
    ["G-003", '<span class="status review">PARTLY AUTOMATED</span>', "Create/redeem flows",
     "mon1/2/3 Sales, Redemption, and Reinvestment",
     "Pass --orders to prepare-review. Review calculated sales/redemptions in FundFields. Enter reinvestment only from separate internal evidence.",
     "Capital Markets + Accounting", "Accepted-order calculation, cutoff review, and independent reconciliation"],
    ["G-004", '<span class="status ok">ENGINEERED</span>', "Fund policy and static data",
     "Fiscal year-end, filing type, derivatives regime, applicability, identity, and signer fields",
     "Use FundFields where targetFile=fund_config.txt. No separate fund_registry.csv is required.",
     "Compliance / Legal", "Approved value, effective date, approver, timestamp, and internal policy reference"],
    ["G-005", '<span class="status ok">ENGINEERED</span>', "Source manifest",
     "Lineage for every accepted source",
     "Complete Sources. Finalize-review creates source_manifest.csv automatically.",
     "Operations", "Path exists; cutoff, hash, count, preparer, reviewer, and approval are complete"],
    ["G-006", '<span class="status ok">ENGINEERED CONTROL</span>', "Prohibited comparison inputs",
     "U.S. Bank, EagleSTAR, prepared filings, legacy masters, and derived canonical files",
     "Do not add them to Sources. Known labels and repository landing paths are rejected.",
     "Engineering + Operations", "Prohibited-source check passes; legacy writers remain disabled"],
    ["G-007", '<span class="status ok">ENGINEERED</span>', "Human-review evidence",
     "Value/disposition, source, cutoff, reviewer, time, reason, and two-person approval",
     "Complete FundFields, HoldingFields, Sources, and Approvals in the fund-period workbook.",
     "Operations", "review-status returns zero blockers; review receipt hashes workbook and outputs"],
    ["G-008", '<span class="status blocked">DATA BLOCKER IF SWAPS</span>', "Swap economics",
     "Counterparty, LEI, notional, value, termination, and receive/pay leg terms",
     "Use HoldingFields for the swap record. Cite internal trade evidence or an independently retained executed confirmation.",
     "Derivatives Operations", "All required swap fields supported; valuation reconciles"],
    ["G-009", '<span class="status blocked">DATA BLOCKER IF APPLICABLE</span>', "B.2.f / B.3 / B.5.c / B.9 / B.10",
     "Cash outside C/D, risk metrics, monthly categories, derivatives exposure, or VaR",
     "Use FundFields. Enter a supported value or NOT_APPLICABLE with source, reviewer, time, and reason.",
     "Accounting + Risk", "Fund policy determines applicability; preflight enforces applicable sections"],
    ["G-010", '<span class="status blocked">DATA BLOCKER IF APPLICABLE</span>', "C.7 liquidity",
     "liquidityClassificationJson and liquidityCircumstancesJson by holding",
     "Use HoldingFields for each surfaced holding and cite internal liquidity-risk evidence.",
     "Liquidity Risk", "100% applicable holding coverage and approval evidence"],
    ["G-011", '<span class="status blocked">DATA BLOCKER FOR OPTIONS</span>', "Option terms and delta",
     "Delta, exercise terms, expiry, and underlying/reference identity",
     "Use HoldingFields for the option record and cite internal trade/risk evidence at the cutoff.",
     "Derivatives Risk", "Required option fields supported and validated"],
    ["G-012", '<span class="status review">PARTLY ENGINEERED</span>', "Reconciliation",
     "NAV equation and position count are automated; GL, derivatives, and flow tie-outs still need source reports",
     "Clear automated results in Reconciliation and attach the other internal control reports in Sources.",
     "Accounting + Operations", "No automated exception; independent control reports reviewed"],
    ["G-013", '<span class="status blocked">RESIDUAL CONTROL LIMIT</span>', "Origin assurance",
     "Local files cannot prove a reviewer did not manually copy and relabel a prohibited value",
     "Use source-system attestations, hashes, dual review, and the receipt. This remains a governance control without authenticated connectors.",
     "Operations + Compliance", "Documented origin attestation; no claim that local code can prove origin"],
]

GAP_FILES = {
    "G-001": ["data/intake/<period>/<fund>/positions.csv", "clean bundle: holdings.csv"],
    "G-002": ["accounting_close.csv or accounting_close.pdf", "clean bundle: filing_data.txt"],
    "G-003": ["create_redeem_orders.csv", "reinvestment_support.csv (if applicable)"],
    "G-004": ["fund_policy_approval.pdf", "fund_static_data.csv", "clean bundle: fund_config.txt"],
    "G-005": ["human_review.xlsx", "clean bundle: source_manifest.csv"],
    "G-006": ["comparison only: data/custodian/*", "data/fund_accounting/*", "data/master/*.xlsx", "legacy data/funds/* files"],
    "G-007": ["human_review.xlsx", "field_provenance.csv", "review_receipt.json"],
    "G-008": ["swap_trade_export.csv", "executed_swap_confirmations.pdf"],
    "G-009": ["cash_ledger.csv", "risk_metrics.csv", "rule_18f4_results.csv", "var_backtesting.csv", "monthly_return_categories.csv"],
    "G-010": ["liquidity_classifications.csv", "liquidity_circumstances.csv (if applicable)"],
    "G-011": ["option_trade_terms.csv", "option_delta.csv"],
    "G-012": ["reconciliation.csv", "positions_to_gl_reconciliation.csv", "flow_reconciliation.csv", "derivatives_reconciliation.csv"],
    "G-013": ["source_origin_attestation.pdf", "review_receipt.json"],
}


def gap_files(gap_id: str) -> str:
    return "<br>".join(code(value) for value in GAP_FILES[gap_id])


def blocker_tables() -> tuple[str, str]:
    files_table = chunked_t(
        ["ID / status", "Gap / affected fields", "Required file templates"],
        [[f"<b>{r[0]}</b><br>{r[1]}", f"<b>{r[2]}</b><br>{r[3]}", gap_files(r[0])] for r in GAPS],
        ["18%", "34%", "48%"], "dense", 4,
    )
    action_table = chunked_t(
        ["ID", "Exactly where to fix", "Owner", "Proof to close"],
        [[f"<b>{r[0]}</b>", r[4], f"<b>{r[5]}</b>", r[6]] for r in GAPS],
        ["10%", "40%", "20%", "30%"], "dense", 4,
    )
    return files_table, action_table


def audit_html() -> str:
    gap_file_table, gap_action_table = blocker_tables()
    review_rows = [
        ["Summary", "Fund + period", "Nothing", "Scope, stop rule, and next command", "Read-only"],
        ["GapGuide", "gapId", "Read-only explanation", "All 13 gaps and exact sheet", "Navigation only"],
        ["FundFields", "targetFile + fieldName", "proposedValue, sourceId, sourceAsOf, status, reviewer, reviewedAt, comment", "Fund config and filing-level values", "APPROVED value or supported NOT_APPLICABLE disposition"],
        ["HoldingFields", "recordKey + fieldName", "Same review columns", "Debt, derivative, option, swap, and liquidity exceptions", "Generated from the independent positions file"],
        ["Sources", "sourceId", "System, path, cutoff, hash, count, preparer, reviewer, approval", "Evidence used by reviewed rows", "U.S. Bank/reference sources are rejected"],
        ["Approvals", "PREPARER / REVIEWER", "Name, approvedAt, status, comment", "Package approval", "Two different people required"],
        ["Reconciliation", "check", "Status, actual, expected, detail", "NAV equation and position count", "Generated during evaluation/finalization"],
    ]
    body = fr"""
<h2>1. Final conclusion</h2>
<div class="callout danger"><b>No June 2026 output is release-eligible.</b> The repository's landed custody, EagleSTAR, prepared N-PORT, master workbooks, and derived per-fund files came from U.S. Bank-delivered material. They may be compared against independently generated output, but they cannot populate it.</div>
<p>The correct comparison is output-to-output after dates and fund identity are aligned. It is not a source merge. Numerical differences caused only by different report dates are not gaps. A gap is missing coverage, evidence, logic, or reconciliation in the in-house service.</p>

<h2>2. Missing versus blocking</h2>
{t(["Term", "Meaning", "Example", "Release effect"], [
    ["Missing", "A required value, dataset, approval, or proof is absent.", "No internal position close exists for 2026-06-30.", "Usually becomes a blocker if applicable."],
    ["Blocking", "The system must refuse release. The cause may be missing, stale, invalid, unapproved, prohibited, or unreconciled.", "A netAssets value is present but came from U.S. Bank.", "Release must stop."],
    ["Non-blocking review", "Optional or supported data needs confirmation, but omission is permitted by the filing contract.", "ISIN is absent but a valid CUSIP is filed.", "Review and document; does not automatically stop release."],
], ["17%", "35%", "31%", "17%"])}
<div class="callout"><b>Key point:</b> “present” does not mean “usable.” A value from a prohibited source is a blocker even when it is populated.</div>

<h2>3. What the code does now</h2>
{chunked_t(["Control", "Current behavior", "Truth / limitation"], [
    ["Production build", code("nport build") + " reads canonical fund_config.txt, filing_data.txt, and holdings.csv only.", "It no longer calls the U.S. Bank custodian or EagleSTAR parsers."],
    ["Fund review", code("prepare-review") + " creates one workbook under the fund and period.", "It contains exact locations for every fund field and surfaced holding exception."],
    ["Evidence gate", code("review-status") + " checks values, dispositions, sources, cutoffs, hashes, counts, timestamps, and approvals.", "Known U.S. Bank/EagleSTAR labels and legacy repository paths are rejected."],
    ["Clean finalization", code("finalize-review") + " writes a new versioned bundle under data/builds.", "It never overwrites the source workbook or legacy canonical files."],
    ["Legacy/write workflow", "masters, split, mergehumanreview, enrich, merge, new-filing, and the master-specific commands exit with an error.", "They either consume prohibited material or cannot authenticate independent origin."],
    ["Reference comparison", code("nport compare-reference") + " is read-only.", "It reports structural differences and never writes filing inputs."],
    ["Residual limitation", "Manifest checks use labels, paths, dates, hashes, counts, and approval.", "They cannot prove origin if a prohibited file is deliberately moved and relabelled; authenticated connectors remain required."],
], ["20%", "40%", "40%"], "", 4)}

<h2>4. Complete open-blocker register</h2>
<p>These are the 13 tracked gaps. Engineering status and data status are separate: a workflow can be implemented while the filing remains blocked because the independent value has not been supplied.</p>
<p class="small"><b>File-name rule:</b> the names below are expected internal naming templates, not claims that the files currently exist. Use the real source filename when different. An empty placeholder never closes a blocker.</p>
{gap_file_table}
<h3>Exact fix location and proof</h3>
{gap_action_table}

<h2>5. Where a human enters values</h2>
<div class="callout good"><b>Implemented location:</b> <code>data/funds/&lt;fund&gt;/filings/&lt;period&gt;/human_review.xlsx</code>. This is the only workbook used by the new review path.</div>
{chunked_t(["Sheet", "Row key", "Editable values", "Covers", "Release rule"], review_rows, ["15%", "16%", "30%", "19%", "20%"], "dense", 4)}
<p>The workbook is generated for one fund and one period from the independently supplied positions file. It is a controlled queue: Sources establishes the evidence, FundFields and HoldingFields record decisions, Approvals records two-person sign-off, and Reconciliation records automated results. It is not a source of facts by itself.</p>
<h3>What a human may and may not do</h3>
<ul><li>May: enter a value supported by an approved independent source.</li><li>May: mark a conditional field NOT_APPLICABLE only with a source, reviewer, timestamp, and reason.</li><li>May not: invent a zero, N/A, policy choice, identifier, term, or classification.</li><li>May not: cite or copy U.S. Bank, EagleSTAR, a prepared filing, or a file derived from them.</li><li>May not: type the base position population into Excel; it must be supplied with <code>--positions</code>.</li></ul>

<h2>6. Correct operating sequence</h2>
{chunked_t(["Step", "Actor", "Deterministic action", "Completion condition"], [
    ["1. Intake", "Operations", "Place the actual independent positions file and optional orders file in the fund-period intake folder.", "Real files exist; their origin is independent of U.S. Bank."],
    ["2. Template", "Operations", code("nport prepare-review <fund> <period> --positions <file> [--orders <file>]"), "The fund-period human_review.xlsx exists."],
    ["3. Evidence", "Preparer + source owner", "Complete Sources with the actual system, path, cutoff, hash/count, and preparation evidence.", "Every used source row is complete and PENDING or APPROVED."],
    ["4. Decisions", "Field owners", "Resolve generated FundFields and HoldingFields rows; every accepted decision cites Sources.", "No applicable row is MISSING or NEEDS_REVIEW."],
    ["5. Approval", "Second reviewer", "Review sources and decisions; complete Approvals separately from the preparer.", "PREPARER and REVIEWER are different and both APPROVED."],
    ["6. Gate", "Operations", code("nport review-status <fund> <period>"), "Command reports zero blockers."],
    ["7. Build", "Operations", code("nport build <fund> <period> --from-review"), "Versioned clean bundle and validated XML are written."],
    ["8. Compare", "Reviewer", "Compare the independent XML with U.S. Bank output on the same fund/date only.", "Differences are documented; comparison data is never merged back."],
], ["10%", "18%", "45%", "27%"], "dense", 4)}
<div class="callout"><b>All-fund operation:</b> repeat the sequence independently for every fund. The runbook contains copy/paste PowerShell loops that discover fund folders from <code>data/intake/&lt;period&gt;/</code>, create one workbook per fund, stop on blocked reviews, and build only review-ready funds. FDRS is an example ticker, not a scope limitation.</div>
<div class="callout"><b>Field coverage:</b> the runbook contains a generated trace for all 170 accepted canonical fields: 30 fund-configuration fields, 56 filing-level fields, and 84 holding fields. It separates the actual current/legacy writer from the new review location.</div>

<h2>7. What remains before release</h2>
<p>The local review, evidence, merge, provenance, basic reconciliation, and build controls are implemented. What remains is the actual independent fund data and control evidence for each period, plus GL/position, flow, and derivatives reconciliations. Local code also cannot prove that a person did not copy and relabel a prohibited value. Until the applicable data and evidence are supplied, the honest filing status remains <span class="status blocked">BLOCKED</span>.</p>
"""
    return shell("Comprehensive Final Audit", "What is prohibited, what is missing, where each gap must be fixed, and what remains before an independently built N-PORT filing can be released.", body)


def runbook_html() -> str:
    config_rows, filing_rows, holding_rows, trace_checks = trace_rows()
    gap_file_table, gap_action_table = blocker_tables()
    source_rows = [
        ["Positions", code("internal_positions"), "Part C base rows and values", "Required", "Actual source system is recorded by Operations in Sources"],
        ["Fund accounting", code("internal_fund_accounting"), "B.1/B.2, gains, returns, cash", "Required when fields apply", "Actual GL/NAV source is recorded by Fund Accounting"],
        ["Create/redeem", code("internal_create_redeem"), "Calculated sales/redemptions only", "Optional input; review still required", "Actual order system is recorded by Capital Markets"],
        ["Security/reference", code("internal_security_reference"), "Identifiers, country, categories, debt/reference terms", "As applicable", "Actual independent or licensed source is recorded in Sources"],
        ["Liquidity", code("internal_liquidity"), "C.7", "Only if policy requires C.7", "Actual liquidity-risk evidence is recorded in Sources"],
        ["Derivatives/risk", code("internal_derivatives"), "C.11 and B.9/B.10", "Only for applicable holdings/regimes", "Actual trade/risk evidence is recorded in Sources"],
    ]
    trace_headers = ["Canonical field", "Actual current/legacy origin", "Transform and live code location", "New independent workflow"]
    trace_widths = ["14%", "24%", "30%", "32%"]
    holding_groups: dict[str, list[list[str]]] = {}
    for external, internal in _HOLDINGS_KEY_MAP.items():
        holding_groups.setdefault(FIELD_BY_NAME[internal].group, []).append(
            holding_rows[list(_HOLDINGS_KEY_MAP).index(external)]
        )
    holding_trace = "".join(
        chunked_t(
            trace_headers, rows, trace_widths, "dense", 4,
            group.replace('_', ' ').title(), True,
        )
        for group, rows in holding_groups.items()
    )
    batch_prepare = escape(r'''$period = "2026-06"
$nport = ".\.venv\Scripts\nport.exe"
$intakeRoot = Join-Path ".\data\intake" $period

foreach ($fundFolder in Get-ChildItem -LiteralPath $intakeRoot -Directory) {
    $fund = $fundFolder.Name.ToLowerInvariant()
    $positions = Join-Path $fundFolder.FullName "positions.csv"
    $orders = Join-Path $fundFolder.FullName "create_redeem_orders.csv"
    if (-not (Test-Path -LiteralPath $positions)) {
        throw "Missing independent positions file for $fund: $positions"
    }
    $reviewArgs = @("prepare-review", $fund, $period, "--positions", $positions)
    if (Test-Path -LiteralPath $orders) {
        $reviewArgs += @("--orders", $orders)
    }
    & $nport @reviewArgs
    if ($LASTEXITCODE -ne 0) { throw "prepare-review failed for $fund" }
}''')
    batch_status = escape(r'''$period = "2026-06"
$nport = ".\.venv\Scripts\nport.exe"
$failedFunds = @()

foreach ($book in Get-ChildItem -Path ".\data\funds\*\filings\$period\human_review.xlsx" -File) {
    $fund = $book.Directory.Parent.Parent.Name.ToLowerInvariant()
    & $nport review-status $fund $period
    if ($LASTEXITCODE -ne 0) { $failedFunds += $fund }
}
if ($failedFunds.Count -gt 0) {
    throw "Blocked funds: $($failedFunds -join ', ')"
}''')
    batch_build = escape(r'''$period = "2026-06"
$nport = ".\.venv\Scripts\nport.exe"

foreach ($book in Get-ChildItem -Path ".\data\funds\*\filings\$period\human_review.xlsx" -File) {
    $fund = $book.Directory.Parent.Parent.Name.ToLowerInvariant()
    & $nport build $fund $period --from-review
    if ($LASTEXITCODE -ne 0) { throw "build failed for $fund" }
}''')
    body = fr"""
<h2>1. Purpose and non-negotiable boundary</h2>
<p>This runbook operates an N-PORT service built from independent sources. U.S. Bank custody exports, EagleSTAR attachments, prepared filings, email attachments, and prior master workbooks are benchmark outputs only. They may never be copied, merged, seeded, or used to clear a production exception.</p>
<div class="callout danger"><b>Stop rule:</b> if the only available answer comes from U.S. Bank, record the field as missing and keep the filing blocked.</div>

<h2>2. Status language</h2>
{t(["Status", "Use it when", "Operator action"], [
    ['<span class="status blocked">MISSING</span>', "The field or evidence does not exist.", "Obtain it from the named independent owner/source."],
    ['<span class="status blocked">BLOCKED</span>', "Release must stop because an applicable item is missing, invalid, stale, unapproved, prohibited, or unreconciled.", "Do not promote to LIVE."],
    ['<span class="status review">REVIEW</span>', "A human decision or confirmation is required.", "Enter the value only in the named exception location and attach evidence."],
    ['<span class="status ok">CLEAR</span>', "Source, cutoff, validation, reconciliation, and approval all pass.", "Retain the evidence and proceed."],
], ["14%", "43%", "43%"])}

<h2>3. What the source labels mean</h2>
<div class="callout"><b>Deterministic rule:</b> these are dataset categories, not claims that a system or file exists. The real system name, real path, cutoff, hash, count, preparer, and reviewer are supplied on the Sources sheet for the specific fund and period.</div>
{chunked_t(["Evidence category", "Dataset value", "Can support", "When required", "Who records the actual source"], source_rows, ["16%", "18%", "24%", "19%", "23%"], "dense", 3)}

<h2>4. Exact operating workflow</h2>
<div class="callout good"><b>Use this order every time.</b> Do not skip ahead. A command that returns a blocker means stop, correct the named workbook row or source evidence, and rerun that command.</div>
<div class="steps">
<div class="step"><h3>Step 1 - Check the input format</h3><p><span class="label">Run:</span></p><div class="cmd">Set-Location "C:\Users\damie\nportvalidation"
&amp; ".\.venv\Scripts\nport.exe" schema</div><p><span class="label">System:</span> Prints the required and conditional <code>positions.csv</code> columns.</p><p><span class="label">Human:</span> Export independent positions to <code>data/intake/&lt;period&gt;/&lt;fund&gt;/positions.csv</code>. If available, place the independent order file beside it as <code>create_redeem_orders.csv</code>.</p><p><span class="label">Stop if:</span> Either file came from or was derived from U.S. Bank or EagleSTAR.</p></div>
<div class="step"><h3>Step 2 - Create the fund review workbook</h3><p><span class="label">Run:</span></p><div class="cmd">&amp; ".\.venv\Scripts\nport.exe" prepare-review FDRS 2026-06 --positions ".\data\intake\2026-06\fdrs\positions.csv" --orders ".\data\intake\2026-06\fdrs\create_redeem_orders.csv"</div><p><span class="label">System:</span> Creates or refreshes <code>data/funds/fdrs/filings/2026-06/human_review.xlsx</code>. Omit <code>--orders</code> when no independent order export exists.</p><p><span class="label">Human:</span> Confirm the printed fund, period, positions path, and workbook path are correct.</p><p><span class="label">Pass when:</span> The command prints <code>Prepared:</code> and the expected workbook path.</p></div>
<div class="step"><h3>Step 3 - Register source evidence</h3><p><span class="label">Run:</span> No new command. Open <code>human_review.xlsx</code> and use the <code>Sources</code> sheet.</p><p><span class="label">System:</span> Carries the positions/orders paths, SHA-256, and record counts into the workbook. If a source file changes, its status returns to PENDING.</p><p><span class="label">Human:</span> For every source actually used, complete sourceSystem, sourcePath, sourceAsOf, acquiredAt, preparedBy, reviewedBy, reviewedAt, status, and comment. The reviewer must be a different person.</p><p><span class="label">Pass when:</span> Every cited source is independent, period-aligned, complete, and APPROVED.</p></div>
<div class="step"><h3>Step 4 - Resolve the field review queue</h3><p><span class="label">Run:</span> No new command. In the workbook, filter <code>FundFields</code> and <code>HoldingFields</code> to MISSING or NEEDS_REVIEW.</p><p><span class="label">System:</span> Shows the exact targetFile, recordKey, fieldName, current value, and gap ID.</p><p><span class="label">Human:</span> Enter proposedValue, sourceId, sourceAsOf, reviewer, reviewedAt, and comment. Use APPROVED for a supported value. Use NOT_APPLICABLE only with evidence and a factual reason. Do not edit SYSTEM_DERIVED or SYSTEM_CONTROL rows.</p><p><span class="label">Pass when:</span> No applicable row remains MISSING or NEEDS_REVIEW.</p></div>
<div class="step"><h3>Step 5 - Complete two-person approval</h3><p><span class="label">Run:</span> No new command. Use the workbook's <code>Approvals</code> sheet.</p><p><span class="label">Human:</span> One person completes PREPARER; a different person completes REVIEWER. Both enter name, ISO-8601 approvedAt, APPROVED status, and comment.</p><p><span class="label">Pass when:</span> Both approval rows are complete and the names differ.</p></div>
<div class="step"><h3>Step 6 - Run the blocker gate</h3><p><span class="label">Run:</span></p><div class="cmd">&amp; ".\.venv\Scripts\nport.exe" review-status FDRS 2026-06</div><p><span class="label">System:</span> Prints every unresolved field, source, approval, cutoff, hash, count, or reconciliation issue.</p><p><span class="label">Human:</span> Fix the exact row named after <code>Fix:</code>, save the workbook, and rerun this command.</p><p><span class="label">Pass when:</span> The command prints <code>READY - zero review blockers.</code></p></div>
<div class="step"><h3>Step 7 - Test without retaining output</h3><p><span class="label">Run:</span></p><div class="cmd">&amp; ".\.venv\Scripts\nport.exe" build FDRS 2026-06 --from-review --dry-run</div><p><span class="label">System:</span> Finalizes in temporary storage, validates canonical data, generates XML, and runs XSD validation.</p><p><span class="label">Human:</span> Read every reported error. Return to the named source or workbook row; never patch generated XML.</p><p><span class="label">Pass when:</span> The command prints <code>DRY RUN PASSED</code>.</p></div>
<div class="step"><h3>Step 8 - Build, then compare</h3><p><span class="label">Run:</span></p><div class="cmd">&amp; ".\.venv\Scripts\nport.exe" build FDRS 2026-06 --from-review
&amp; ".\.venv\Scripts\nport.exe" compare-reference --internal ".\output\FDRS_2026-06.xml" --reference "&lt;aligned-reference.xml&gt;"</div><p><span class="label">System:</span> Writes a versioned clean bundle under <code>data/builds/fdrs/2026-06/&lt;run-id&gt;/</code>, writes XML under <code>output/</code>, and performs a read-only comparison.</p><p><span class="label">Human:</span> Confirm the internal and reference outputs use the same fund identity and report date. Document gaps; never copy comparison values back into the filing.</p><p><span class="label">Pass when:</span> The clean bundle, receipt, validated XML, and documented comparison all exist.</p></div>
</div>

<h3>Run the workflow for every fund</h3>
<div class="callout"><b>Scope rule:</b> the service is not limited to FDRS. Each fund has its own positions file, review workbook, source evidence, approvals, clean bundle, and XML. Never reuse one fund's workbook or approval for another fund.</div>
<p><b>Phase A - generate one review workbook per intake folder.</b> The folder name is the fund ticker. The loop requires <code>positions.csv</code> and includes <code>create_redeem_orders.csv</code> only when that file exists.</p>
<div class="cmd">{batch_prepare}</div>
<p><b>Phase B - pause for human review.</b> Reviewers complete Sources, FundFields, HoldingFields, and Approvals separately for every fund. Do not run the build loop before this work is complete.</p>
<p><b>Phase C - check every prepared workbook.</b> The loop exits with a list of blocked funds if any review is incomplete.</p>
<div class="cmd">{batch_status}</div>
<p><b>Phase D - build every review-ready fund.</b> Run only after Phase C finishes without an error.</p>
<div class="cmd">{batch_build}</div>

<h3>Complete command reference</h3>
{chunked_t(["Command", "Stage", "What it does", "Writes data?"], [
    [code("nport schema"), "Intake design", "Prints every canonical positions.csv column, type, and applicability rule.", "No"],
    [code("nport prepare-review <fund> <period> --positions <file> [--orders <file>]"), "Template", "Creates or refreshes the fund-period review workbook and source rows.", "Yes - human_review.xlsx"],
    [code("nport review-status <fund> <period>"), "Gate", "Lists every unresolved field, evidence, approval, source, and reconciliation blocker.", "No"],
    [code("nport finalize-review <fund> <period>"), "Finalization", "Writes a versioned clean canonical bundle only when the review has zero blockers.", "Yes - data/builds/..."],
    [code("nport build <fund> <period> --from-review --dry-run"), "Pre-release test", "Finalizes in temporary storage and validates without retaining a bundle or XML.", "No retained output"],
    [code("nport build <fund> <period> --from-review"), "Release build", "Finalizes the approved review, generates XML, and runs schema validation.", "Yes - clean bundle and XML"],
    [code("nport compare-reference --internal <xml> --reference <xml>"), "Post-build comparison", "Performs a read-only structural comparison after dates and fund identity are aligned.", "No filing inputs"],
    [code("nport check-schema"), "Maintenance", "Checks the local N-PORT schema files and version.", "Cache only when applicable"],
    [code("nport pull --ticker <ticker> --list"), "External research", "Lists recent EDGAR N-PORT filings; it is not an input adapter.", "No, unless an explicit output download is requested"],
], ["38%", "15%", "33%", "14%"], "dense", 4)}
<p><b>Disabled write paths:</b> masters, split, mergehumanreview, enrich, merge, new-filing, build-master, split-master, build-filing-master, and split-filing-master. Do not use them for the independent service.</p>

<h2>5. Review workbook template</h2>
{chunked_t(["Sheet", "Key", "What the human edits", "Result", "Release rule"], [
    ["Summary", "Fund + period", "Nothing", "Shows scope, stop rule, and next command", "Read-only"],
    ["GapGuide", "gapId", "Nothing", "Explains all 13 gaps, evidence template, and exact destination", "Read-only"],
    ["FundFields", "targetFile + fieldName", "proposedValue, sourceId, sourceAsOf, status, reviewer, reviewedAt, comment", "Approved config and filing-level values", "Every required row resolved"],
    ["HoldingFields", "recordKey + fieldName", "Same seven review columns", "Approved holding exceptions", "Every surfaced required row resolved"],
    ["Sources", "sourceId", "Actual system/path/cutoff/hash/count plus dual-review evidence", "Generated source manifest", "Every used source approved, independent, and unchanged"],
    ["Approvals", "role", "Name, approvedAt, status, comment", "Package approval", "Different preparer and reviewer"],
    ["Reconciliation", "check", "Nothing; correct upstream values/evidence", "NAV equation and position-count results", "Every automated check passes"],
], ["15%", "17%", "30%", "23%", "15%"], "dense", 4)}
<div class="callout danger"><b>The workbook is a controlled exception and approval layer.</b> It does not make unsupported data true. It only accepts a value when the row points to an approved source and the required review evidence is complete.</div>

<h2>6. Status and timestamp rules</h2>
{chunked_t(["Value", "Exact meaning", "Required evidence"], [
    ["MISSING", "No usable value has been supplied.", "None yet; remains a blocker when applicable."],
    ["NEEDS_REVIEW", "A value exists but has not been approved.", "Independent source plus reviewer decision."],
    ["APPROVED", "The proposed/current value is supported and accepted.", "sourceId, matching sourceAsOf, reviewer, reviewedAt, approved Sources row."],
    ["NOT_APPLICABLE", "A conditional field does not apply to this fund/holding.", "sourceId, reviewer, reviewedAt, and a factual reason in comment."],
    ["SYSTEM_DERIVED", "The system calculates the value from approved period/policy inputs.", "No manual override."],
    ["SYSTEM_CONTROL", "The system owns the release-state value.", "No manual override."],
], ["20%", "40%", "40%"], "dense", 3)}
<p>Use ISO-8601, for example <code>2026-08-03T16:30:00-05:00</code>. The example is a format illustration, not an asserted review time.</p>

<h2>7. Current blocker checklist and exact fix location</h2>
<p class="small"><b>File-name rule:</b> these are expected templates. Use the actual independent source filename; never create an empty placeholder.</p>
{gap_file_table}
<h3>Exact fix location and proof</h3>
{gap_action_table}

<h2 class="page">8. How to read the field trace</h2>
<div class="callout danger"><b>Actual lineage is not authorization.</b> The second column states what the current/legacy code really used, including Bloomberg formulas, U.S. Bank custody, EagleSTAR, seeded review workbooks, constants, and no-feed fields. Those legacy writers are disabled or prohibited for the new production build. The fourth column is the only production workflow.</div>
<p>The trace is generated from the canonical config, filing, and holding field maps. Generation stops if field counts change or the verified lineage anchors no longer resolve.</p>
<p class="small">Verification performed: {escape('; '.join(trace_checks))}.</p>

<h2 class="page">9. Exhaustive field trace - fund configuration</h2>
<p>All {len(config_rows)} accepted fund-configuration fields are listed. <code>requiredSources</code> is derived from approved Sources rows in the new workflow; it is not typed as business data.</p>
{chunked_t(trace_headers, config_rows, trace_widths, "dense", 4, "Fund configuration")}

<h2 class="page">10. Exhaustive field trace - filing-level data</h2>
<p>All {len(filing_rows)} accepted filing-level fields are listed. A legacy constant is reported as a constant; it is not silently reclassified as sourced data.</p>
{chunked_t(trace_headers, filing_rows, trace_widths, "dense", 4, "Filing-level data")}

<h2 class="page">11. Exhaustive field trace - holdings</h2>
<p>All {len(holding_rows)} accepted holdings fields are listed and grouped by filing condition. Present base values remain tied to the approved POSITIONS source; missing required and review-sensitive values are surfaced in HoldingFields.</p>
{holding_trace}

<div class="keep"><h2>12. Release decision</h2>
<p>The code may build only after <code>review-status</code> returns zero blockers. That requires applicable fields to be resolved from approved independent sources, source cutoffs to match the report period, source hashes and counts to match, two-person approval to be complete, automated reconciliation to pass, canonical validation to pass, and XSD validation to pass. The local workflow cannot prove that a person did not copy and relabel a prohibited value; origin attestation remains a human governance control.</p></div>
"""
    return shell("N-PORT In-House Runbook", "A field-by-field operating guide showing what supplies each value, exactly where it is entered, how human review works, and what blocks release.", body)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "nport_final_inhouse_audit_2026-08-03.html").write_text(audit_html(), encoding="utf-8")
    (DOCS / "nport_runbook.html").write_text(runbook_html(), encoding="utf-8")


if __name__ == "__main__":
    main()
