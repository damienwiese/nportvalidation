"""Generate the source-independent N-PORT audit and field-level runbook HTML."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

import field_provenance as provenance
import runbook_traceability as legacy_trace

from nport.config import _CONFIG_KEY_MAP, _FILING_KEY_MAP, _HOLDINGS_KEY_MAP
from nport.fund_review import FLOW_RECON_FIELDS, SYSTEM_DERIVED_FILING
from nport.schema import FIELD_BY_NAME


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TODAY = date(2026, 8, 4)


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
<section class="cover"><div class="eyebrow">Corgi ETF Trust &middot; N-PORT in-house service</div>
<h1>{escape(title)}</h1><p class="subtitle">{escape(subtitle)}</p>
<p class="stamp">As of August 4, 2026 &middot; Source-independent workflow</p>
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
        return "Prevents release when the field/section is applicable"
    return "Prevents release when absent, invalid, stale, or unsupported"


def filing_source(field: str) -> tuple[str, str]:
    if field in {"submissionType", "repPdEnd", "repPdDate", "derivativesRegime"}:
        return "Current fund policy and static-data record", "System-derived after the policy rows pass validation"
    if field in {"liveTestFlag", "isFinalFiling", "dateSigned"}:
        return "Filing operations / authorized signatory", "FundFields sheet; enter the applicable XML value"
    if field in {"totAssets", "totLiabs", "netAssets", "assetsAttrMiscSec", "assetsInvested"} or field.startswith("amtPay") or field in {"delayDeliv", "standByCommit", "liquidPref", "isNonCashCollateral"}:
        return "Internal GL, NAV close, and accounting subledgers", "FundFields sheet; enter the applicable XML value"
    if field.startswith("rtn") or field.startswith("netRealized") or field.startswith("netUnrealized"):
        return "Internal performance/accounting calculation or Bloomberg return series", "FundFields sheet; enter the applicable XML value"
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
    return "Supported internal filing calculation", "FundFields sheet with value, source ID, status, and factual comment when needed"


def holding_source(field: str) -> tuple[str, str]:
    if field in {"name", "title", "cusip", "ticker", "balance", "units", "curCd", "valUSD"}:
        return "Internal OMS/IBOR position close plus independent security master", "System feed; do not recreate manually"
    if field == "pctVal":
        return "Derived from valUSD / supplied netAssets", "System-derived; reconciliation must tie denominator"
    if field in {"lei", "isin", "invCountry"}:
        sheet = {"lei": "no complete current sheet", "isin": "isin", "invCountry": "invCountry"}[field]
        return "Approved internal security master / licensed reference data", f"Exception review: {sheet} sheet; enter the missing XML value"
    if field in {"assetCat", "issuerCat", "payoffProfile", "fairValLevel", "isRestrictedSec", "isCashCollateral", "isNonCashCollateral", "isLoanByFund"}:
        return "Internal classification engine plus accounting/risk policy", "System mapping; only unresolved exceptions are entered"
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
        return "Internal trade record / independent reference master", "HoldingFields sheet keyed by holding record"
    if field.startswith(("put", "written", "share", "exercise", "exp", "ref", "swap", "termination", "upfront", "pmnt", "rcpt", "notional", "rec", "unrealized", "payoffProfDeriv", "otherDeriv")) or field == "derivCat":
        return "Internal trade records, confirmations, and risk valuation", "HoldingFields sheet keyed by holding record"
    return "Independent internal position/reference source", "HoldingFields sheet when review is required"


def field_rows() -> tuple[list[list[str]], list[list[str]], list[list[str]]]:
    config_rows = []
    for key in _CONFIG_KEY_MAP:
        if key in {"requiredSources", "policySourceRef"}:
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
            "master_sheet.py copies the seeded legacy workbook value when present; that workflow does not establish independent origin.",
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
            return "Optional provenance metadata; it is not requested and does not affect XML."
        if external in {"policyApprovedBy", "policyApprovedAt", "policySourceRef"}:
            return "Compatibility/provenance key; it is not requested and does not affect XML."
        return (
            f"FundFields: targetFile=fund_config.txt, recordKey=FUND, fieldName={external}. "
            "Enter proposedValue and status=PROVIDED; sourceId is optional."
        )
    if kind == "filing":
        if external in {"submissionType", "repPdEnd", "repPdDate", "derivativesRegime"}:
            return "SYSTEM_DERIVED after the period and supplied fund-policy rows pass validation."
        if external == "liveTestFlag":
            return "SYSTEM_CONTROL; remains TEST until all release controls pass."
        return (
            f"FundFields: targetFile=filing_data.txt, recordKey=FUND, fieldName={external}. "
            "Use PROVIDED, or NOT_APPLICABLE with a factual comment; sourceId is optional."
        )
    spec = FIELD_BY_NAME[internal]
    return (
        f"Base value is positions.csv column {external}. If missing or exception-sensitive, use "
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
    ["G-001", '<span class="status review">OPEN INPUT</span>', "Position population",
     "All Part C holdings", "CLI + HoldingFields",
     code("prepare <fund> <period> --positions <independent.csv>") + "; then resolve MISSING HoldingFields rows.",
     "Operations", "The file loads and every required holding value validates"],
    ["G-002", '<span class="status review">OPEN INPUT</span>', "Fund-accounting values",
     "Assets, liabilities, net assets, balance-sheet items, gains, returns, and cash", "FundFields",
     "Filter gapId G-002; enter proposedValue and status. Use a factual comment for NOT_APPLICABLE.",
     "Fund Accounting", "Every applicable XML value is present and the NAV equation passes"],
    ["G-003", '<span class="status review">PARTLY AUTOMATED INPUT</span>', "Create/redeem flows",
     "Monthly sales, redemptions, and reinvestments", "CLI + FundFields",
     "Pass --orders to prepare; enter only unresolved G-003 proposedValue/status rows.",
     "Capital Markets + Accounting", "Every applicable flow value is present and reconciles"],
    ["G-004", '<span class="status review">OPEN INPUT</span>', "Policy and static data",
     "Fiscal year-end, derivatives regime, applicability, identity, and signer fields", "FundFields",
     "For targetFile=fund_config.txt enter proposedValue/status; policyEffectiveTo may be blank if open-ended.",
     "Compliance / Legal", "Every XML-impacting policy/static value validates"],
    ["G-005", '<span class="status ok">OPTIONAL</span>', "Source manifest",
     "Diagnostic provenance only; no XML element", "Sources", "No reviewer entry is required for XML release.",
     "None", "Never blocks XML generation"],
    ["G-006", '<span class="status ok">INPUT BOUNDARY</span>', "Prohibited comparison inputs",
     "U.S. Bank, EagleSTAR, and prepared filing outputs", "CLI + optional Sources",
     "Remove any prohibited supplied path/reference. Never copy comparison values into the workbook.",
     "Engineering + Operations", "No prohibited comparison output is used as an input"],
    ["G-007", '<span class="status ok">OPTIONAL</span>', "Manual provenance",
     "sourceId and provenance sidecars; no XML element", "FundFields + HoldingFields",
     "No sourceId is required. For NOT_APPLICABLE, enter only a factual comment plus status.",
     "None", "Never blocks XML generation"],
    ["G-008", '<span class="status review">CONDITIONAL OPEN INPUT</span>', "Swap economics",
     "Counterparty, LEI, notional, value, termination, and leg terms", "HoldingFields",
     "Filter gapId G-008 and enter proposedValue/status for each named recordKey.",
     "Derivatives Operations", "All required swap XML fields validate and valuation reconciles"],
    ["G-009", '<span class="status review">CONDITIONAL OPEN INPUT</span>', "B.2.f / B.3 / B.5.c / B.9 / B.10",
     "Cash outside C/D, risk metrics, monthly categories, derivatives exposure, or VaR", "FundFields",
     "Filter gapId G-009; enter proposedValue/status or factual NOT_APPLICABLE comment.",
     "Accounting + Risk", "Policy determines applicability; every applicable XML section validates"],
    ["G-010", '<span class="status review">CONDITIONAL OPEN INPUT</span>', "C.7 liquidity",
     "Liquidity classification/circumstances by holding", "HoldingFields",
     "Filter gapId G-010 and enter proposedValue/status for each named recordKey.",
     "Liquidity Risk", "Every applicable holding has valid C.7 XML content"],
    ["G-011", '<span class="status review">CONDITIONAL OPEN INPUT</span>', "Option terms and delta",
     "Delta, exercise terms, expiry, and reference identity", "HoldingFields",
     "Filter gapId G-011 and enter proposedValue/status for each named recordKey.",
     "Derivatives Risk", "Every required option XML field validates"],
    ["G-012", '<span class="status ok">ACCURACY GATE</span>', "Reconciliation",
     "Position-to-GL, monthly flows, derivative totals, and NAV equation", "ReconciliationInputs",
     "Enter controlValue, tolerance, status, and comment. sourceId is optional. Build calculates actual and difference.",
     "Accounting + Operations", "Every calculated difference is within tolerance"],
    ["G-013", '<span class="status">OUT OF ACTIVE SCOPE</span>', "Origin assurance",
     "Source metadata cannot authenticate origin and does not affect XML", "No workbook entry",
     "No action in this workflow.", "None", "Does not gate XML generation"],
]

def issue_tables() -> tuple[str, str]:
    centralized_table = chunked_t(
        ["ID / status", "What must be resolved", "Single review destination"],
        [[f"<b>{r[0]}</b><br>{r[1]}", f"<b>{r[2]}</b><br>{r[3]}",
          (code("filing_inputs.xlsx") + "<br>" + r[4]) if r[0] != "G-013" else r[4]]
         for r in GAPS],
        ["18%", "42%", "40%"], "dense", 4,
    )
    action_table = chunked_t(
        ["ID", "Sheet / entry point", "Exact action", "Owner", "Completion test"],
        [[f"<b>{r[0]}</b>", r[4], r[5], f"<b>{r[6]}</b>", r[7]] for r in GAPS],
        ["8%", "17%", "37%", "16%", "22%"], "dense", 3,
    )
    return centralized_table, action_table


def _field_names(names) -> str:
    return '<span class="small">' + ", ".join(code(name) for name in names) + "</span>"


def human_handoff_html(section: str) -> str:
    """Explain the exact post-automation queue without implying every candidate is typed."""
    config_fields = [
        name for name in _CONFIG_KEY_MAP
        if name not in {"requiredSources", "policyApprovedBy", "policyApprovedAt", "policySourceRef"}
    ]
    policy_names = {
        "fiscalYearEndMMDD", "derivativesRegimePolicy", "liquidityRequired",
        "cashB2fRequired", "policyEffectiveFrom", "policyEffectiveTo",
    }
    config_identity = [name for name in config_fields if name not in policy_names]
    config_policy = [name for name in config_fields if name in policy_names]
    system_filing = set(SYSTEM_DERIVED_FILING) | {"liveTestFlag"}
    flow_fields = list(FLOW_RECON_FIELDS)
    return_fields = ["rtn1", "rtn2", "rtn3"]
    risk_fields = [
        name for name in _FILING_KEY_MAP
        if name not in system_filing and (
            name in {
                "cashNotReportedInCOrD", "curMetricsJson", "creditSprdRiskIgJson",
                "creditSprdRiskNonigJson", "monthlyReturnCategoriesJson",
            }
            or name.startswith(("deriv", "median", "backtesting"))
        )
    ]
    core_fields = [
        name for name in _FILING_KEY_MAP
        if name not in system_filing
        and name not in set(flow_fields + return_fields + risk_fields)
    ]
    entry_rows = [
        ["FundFields", "Filter status = MISSING",
         "PROVIDED: proposedValue when no automated value exists, plus status. NOT_APPLICABLE: status and factual comment; leave proposedValue blank. sourceId is optional.",
         "For targetFile=fund_config.txt, proposedValue is required whenever the field applies; currentValue is reference-only."],
        ["HoldingFields", "Filter status = MISSING",
         "PROVIDED: status; add proposedValue only when currentValue is blank or must be corrected. NOT_APPLICABLE: status and factual comment. sourceId is optional.",
         "Enter only rows generated for the supplied positions. Do not add holdings or invent missing rows."],
        ["ReconciliationInputs", "Every generated checkId",
         "PROVIDED: controlValue, tolerance, status, comment. A flow may be NOT_APPLICABLE only when its filed flow is N/A; then enter status and factual comment. sourceId is optional.",
         "Never type actualBasis or the filed-side actual. Build calculates the actual and difference."],
        ["Sources", "Optional only",
         "Nothing is required for XML. Automation retains technical paths needed to reload supplied files; optional sourceId notes may be added for diagnostics.",
         "Source labels, paths, hashes, counts, and as-of dates never serialize into N-PORT XML."],
    ]
    field_groups = [
        ["Fund configuration - identity/static", "Every generated row is a human confirmation from independent evidence", _field_names(config_identity)],
        ["Fund configuration - policy", "Confirm from the current policy record. policyEffectiveTo may remain blank when the policy is open-ended.", _field_names(config_policy)],
        ["Filing - accounting, signer, and core values", "Enter only rows still MISSING", _field_names(core_fields)],
        ["Filing - monthly returns", "Bloomberg normally populates these; enter only if still MISSING and another independent source supports them", _field_names(return_fields)],
        ["Filing - create/redeem flows", "Orders may populate these; enter only the rows still MISSING", _field_names(flow_fields)],
        ["Filing - conditional risk sections", "Enter PROVIDED when applicable, or NOT_APPLICABLE with a factual comment when policy says the section does not apply", _field_names(risk_fields)],
        ["Holdings", "The exact queue is dynamic: every generated HoldingFields row whose status remains MISSING. fieldName and recordKey identify exactly what and which holding.", "Possible fields are listed by condition in the runbook's exhaustive holding trace; no hidden holding inputs exist."],
        ["Reconciliation", "Every generated ReconciliationInputs check", _field_names([
            "POSITIONS_TO_GL", *[f"FLOW:{name}" for name in FLOW_RECON_FIELDS],
            "DERIVATIVE_MARKET_VALUE (when generated)",
            "DERIVATIVE_UNREALIZED (when generated)",
        ])],
    ]
    return fr"""
<h2>{section}. Post-automation human entry queue</h2>
<div class="callout good"><b>Automation handoff:</b> run <code>prepare</code>, open/save the workbook on Bloomberg, then work only in <code>filing_inputs.xlsx</code>. Filter <code>FundFields</code> and <code>HoldingFields</code> to <code>MISSING</code>. Work only the values, policy decisions, and reconciliation controls listed below. Do not complete Sources for XML release.</div>
{chunked_t(["Sheet", "Rows to work", "What the reviewer types", "What the system owns"], entry_rows, ["16%", "19%", "39%", "26%"], "dense", 2)}
<h3>Exact field names that may remain after automation</h3>
{chunked_t(["Queue", "When the reviewer acts", "fieldName / checkId"], field_groups, ["22%", "31%", "47%"], "dense", 2)}
<div class="callout"><b>Do not edit:</b> Summary, Bloomberg formulas, GapGuide, Reconciliation, gapId, targetFile, recordKey, fieldName, currentValue, actualBasis, SYSTEM_DERIVED rows, or SYSTEM_CONTROL rows.</div>
<p class="small"><b>Permitted blanks:</b> <code>policyEffectiveTo</code> may stay blank for an open-ended policy; <code>nameDesignatedIndex</code> and <code>indexIdentifier</code> are required only for relative VaR; holding <code>isin</code> and <code>ticker</code> may remain blank when another permitted identifier path is valid.</p>
"""


def audit_html() -> str:
    review_location_table, gap_action_table = issue_tables()
    input_rows = [
        ["Summary", "Fund + period", "Nothing", "Scope, stop rule, and next command", "Read-only"],
        ["Bloomberg", "targetFile + recordKey + fieldName", "Nothing; formulas calculate on terminal", "Returns and supported security/reference fields", "Unresolved formulas remain MISSING"],
        ["GapGuide", "gapId", "Read-only explanation", "All 13 gaps and exact sheet", "Navigation only"],
        ["FundFields", "targetFile + fieldName", "PROVIDED: proposedValue if needed + status. N/A: status + factual comment. sourceId optional", "Fund config and filing-level XML values", "Candidate rows have status MISSING"],
        ["HoldingFields", "recordKey + fieldName", "PROVIDED: status + proposedValue only to supply/correct. N/A: status + factual comment. sourceId optional", "Holding XML exceptions", "Only generated candidate rows"],
        ["Sources", "sourceId", "No required human entry; optional trace only", "Diagnostic sidecars and technical intake paths", "Does not gate XML"],
        ["ReconciliationInputs", "checkId", "controlValue, tolerance, status, comment; sourceId optional", "Control totals used to test filed values", "Every generated difference must be within tolerance"],
        ["Reconciliation", "check", "Nothing", "Calculated actual, expected, difference, and result", "Generated in the clean bundle; every row must PASS"],
    ]
    body = fr"""
<h2>1. Final conclusion</h2>
<div class="callout danger"><b>No June 2026 output is release-eligible.</b> The repository's landed custody, EagleSTAR, prepared N-PORT, master workbooks, and derived per-fund files came from U.S. Bank-delivered material. They may be compared against independently generated output, but they cannot populate it.</div>
<p>The correct comparison is output-to-output after dates and fund identity are aligned. It is not a source merge. Numerical differences caused only by different report dates are not gaps. A gap is missing coverage, evidence, logic, or reconciliation in the in-house service.</p>
<div class="callout good"><b>What actually matters:</b> (1) fields serialized into XML, (2) policy/applicability inputs that decide which XML is emitted, and (3) reconciliation controls that test whether filed values are accurate. Source metadata does not appear in XML and is not a release gate.</div>

<h2>2. Open input versus true blocker</h2>
{t(["Term", "Meaning", "Example", "Release effect"], [
    ["Open input", "A required XML value or policy decision has a defined entry path.", "Enter netAssets in FundFields.", "Filing is NOT READY until supplied; this is not an engineering blocker."],
    ["Validation error", "An entered value or calculated relationship fails a deterministic rule.", "The NAV equation fails or a required XML field has invalid format.", "Correct the named workbook row or upstream file, then rebuild."],
    ["True blocker", "No implemented input, calculation, or control can resolve the issue.", "A local file path cannot authenticate source-system origin.", "Requires engineering or an accepted external control."],
], ["17%", "35%", "31%", "17%"])}
<div class="callout"><b>Key point:</b> “present” does not mean “usable.” A prohibited value must be removed and replaced through the named independent input path.</div>

<h2>3. What the code does now</h2>
{chunked_t(["Control", "Current behavior", "Truth / limitation"], [
    ["Production build", code("nport build") + " reads canonical fund_config.txt, filing_data.txt, and holdings.csv only.", "It no longer calls the U.S. Bank custodian or EagleSTAR parsers."],
    ["Input preparation", code("nport prepare") + " creates filing_inputs.xlsx with Bloomberg formulas and exact gap locations.", "It does not call U.S. Bank or EagleSTAR."],
    ["Bloomberg population", "The operator opens filing_inputs.xlsx on a Bloomberg terminal and saves resolved formula results.", "Blank or error results remain MISSING."],
    ["Final build", code("nport build --from-inputs") + " checks XML fields, applicability, and reconciliation; finalizes a clean bundle; builds and validates XML.", "It prints each open input/error and writes nothing until the filing is ready."],
    ["Legacy/write workflow", "masters, split, mergehumanreview, enrich, merge, new-filing, and the master-specific commands exit with an error.", "They either consume prohibited material or cannot authenticate independent origin."],
    ["Reference comparison", code("nport compare-reference") + " is read-only.", "It reports structural differences and never writes filing inputs."],
    ["Provenance sidecars", "Sources, source_manifest.csv, field_provenance.csv, and input_receipt.json may be retained for diagnostics.", "They do not change XML content and do not block generation."],
], ["20%", "40%", "40%"], "", 4)}

{human_handoff_html("4")}

<h2>5. Complete tracked-item register</h2>
<p>G-001 through G-012 now have implemented entry, correction, calculation, or validation paths. G-013 is retained only as a disclosed limitation and is outside the active remediation plan, per the operating decision.</p>
<div class="callout good"><b>One review workspace:</b> every correctable value, disposition, and reconciliation input is resolved in <code>filing_inputs.xlsx</code>. The reviewer does not complete Sources to release XML.</div>
{review_location_table}
<h3>Exact fix location and proof</h3>
{gap_action_table}

<h2>6. Workbook map</h2>
<div class="callout good"><b>Implemented location:</b> <code>data/funds/&lt;fund&gt;/filings/&lt;period&gt;/filing_inputs.xlsx</code>.</div>
{chunked_t(["Sheet", "Row key", "Editable values", "Covers", "Release rule"], input_rows, ["15%", "16%", "30%", "19%", "20%"], "dense", 4)}
<p>The workbook is generated for one fund and period from independent positions. Bloomberg formulas populate supported values; FundFields and HoldingFields contain remaining XML values and applicability decisions; ReconciliationInputs contains control totals and tolerances. Sources is optional trace metadata.</p>
<p><b>Fund-configuration safeguard:</b> a displayed <code>currentValue</code> is reference-only. A <code>fund_config.txt</code> row requires an independently supported <code>proposedValue</code>; changing its status alone does not release it.</p>
<h3>What a human may and may not do</h3>
<ul><li>May: enter an independently known value in the named row.</li><li>May: mark a conditional field NOT_APPLICABLE only with a factual reason.</li><li>May not: invent a zero, N/A, policy choice, identifier, term, or classification.</li><li>May not: copy U.S. Bank, EagleSTAR, or prepared-filing values into an input.</li><li>May not: type the base position population into Excel; supply it with <code>--positions</code>.</li></ul>

<h2>7. Correct operating sequence</h2>
{chunked_t(["Step", "Actor", "Deterministic action", "Completion condition"], [
    ["1. Intake", "Operations", "Place the actual independent positions file and optional orders file in the fund-period intake folder.", "Real files exist; their origin is independent of U.S. Bank."],
    ["2. Prepare", "Operations", code("nport prepare <fund> <period> --positions <file> [--orders <file>]"), "filing_inputs.xlsx exists."],
    ["3. Bloomberg", "Operator", "Open filing_inputs.xlsx on a Bloomberg terminal; wait for formulas; save.", "Bloomberg cells contain values or visible errors."],
    ["4. Complete", "Field owner", "Resolve MISSING FundFields/HoldingFields and every generated ReconciliationInputs row. Ignore Sources unless optional tracing is desired.", "No applicable XML input remains MISSING and reconciliations pass."],
    ["5. Build", "Operations", code("nport build <fund> <period> --from-inputs"), "Clean bundle and validated XML are written, or exact open inputs/errors are printed."],
    ["6. Compare", "Operator", "Optionally compare independent XML with U.S. Bank output on the same fund/date.", "Comparison data is never merged back."],
], ["10%", "18%", "45%", "27%"], "dense", 4)}
<div class="callout"><b>All-fund operation:</b> repeat the sequence independently for every fund. FDRS is an example ticker, not a scope limitation.</div>
<div class="callout"><b>Field coverage:</b> the runbook contains a generated trace for all 170 accepted canonical fields: 30 fund-configuration fields, 56 filing-level fields, and 84 holding fields. It separates the actual current/legacy writer from the new independent input location.</div>

<h2>8. What remains before release</h2>
<p>The input workbook, Bloomberg formulas, applicability rules, reconciliation, and fail-closed build are implemented. What remains is operating data: the actual fund/holding values that enter XML, the policy choices that determine applicable sections, and reconciliation control totals/tolerances. Source metadata is optional. No U.S. Bank value may be used to fill an input. Until every applicable value and validation clears, the honest filing status is <span class="status review">NOT READY</span>.</p>
"""
    return shell("Comprehensive Final Audit", "What is prohibited, what is missing, where each gap must be fixed, and what remains before an independently built N-PORT filing can be released.", body)


def runbook_html() -> str:
    config_rows, filing_rows, holding_rows, trace_checks = trace_rows()
    review_location_table, gap_action_table = issue_tables()
    impact_rows = [
        ["XML value", "Yes", "FundFields or HoldingFields", "Value/format/requiredness blocks build"],
        ["Policy/applicability driver", "Indirectly", "FundFields targetFile=fund_config.txt", "Blocks because it changes dates, form, or XML sections"],
        ["Reconciliation control", "No", "ReconciliationInputs", "Blocks only when the calculated difference exceeds tolerance"],
        ["sourceId / Sources metadata", "No", "Optional", "Never blocks XML; retained only for diagnostics"],
        ["U.S. Bank/EagleSTAR reference", "No", "Do not input", "Rejected as a prohibited comparison-output input"],
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
    $prepareArgs = @("prepare", $fund, $period, "--positions", $positions)
    if (Test-Path -LiteralPath $orders) {
        $prepareArgs += @("--orders", $orders)
    }
    & $nport @prepareArgs
    if ($LASTEXITCODE -ne 0) { throw "prepare failed for $fund" }
}''')
    batch_build = escape(r'''$period = "2026-06"
$nport = ".\.venv\Scripts\nport.exe"

foreach ($book in Get-ChildItem -Path ".\data\funds\*\filings\$period\filing_inputs.xlsx" -File) {
    $fund = $book.Directory.Parent.Parent.Name.ToLowerInvariant()
    & $nport build $fund $period --from-inputs
    if ($LASTEXITCODE -ne 0) { throw "build failed for $fund" }
}''')
    body = fr"""
<h2>1. Purpose and non-negotiable boundary</h2>
<p>This runbook operates an N-PORT service built from independent sources. U.S. Bank custody exports, EagleSTAR attachments, prepared filings, email attachments, and prior master workbooks are benchmark outputs only. They may never be copied, merged, seeded, or used to clear a production exception.</p>
<div class="callout danger"><b>Stop rule:</b> if the only available answer comes from U.S. Bank, record the field as MISSING and keep the filing NOT READY.</div>

<h2>2. Status language</h2>
{t(["Status", "Use it when", "Operator action"], [
    ['<span class="status blocked">MISSING</span>', "A required XML value or policy/applicability input is unresolved.", "Complete the exact FundFields or HoldingFields row."],
    ['<span class="status review">NOT READY</span>', "One or more open inputs or validation errors remain.", "Fix the exact workbook row or upstream file printed by build."],
    ['<span class="status review">PROVIDED</span>', "A current or proposed value is ready for build.", "Set status; sourceId is optional."],
    ['<span class="status ok">CLEAR</span>', "XML fields, applicability, validation, and reconciliation pass.", "Retain the inputs and proceed."],
], ["14%", "43%", "43%"])}

<h2>3. What matters to the filing</h2>
<div class="callout good"><b>Release rule:</b> source labels do not appear in N-PORT XML. The build gates only XML values, policy/applicability inputs that change XML, reconciliation results, canonical validation, and XSD validation.</div>
{chunked_t(["Item", "Appears in XML", "Where the human acts", "Release effect"], impact_rows, ["22%", "16%", "30%", "32%"], "dense", 3)}

<h2>4. Exact operating workflow</h2>
<div class="callout good"><b>Use this order every time.</b> Do not skip ahead. If build reports an open input or validation error, correct the named workbook row or upstream file and rerun the same command.</div>
<div class="steps">
<div class="step"><h3>Step 1 - Check the input format</h3><p><span class="label">Run:</span></p><div class="cmd">Set-Location "C:\Users\damie\nportvalidation"
&amp; ".\.venv\Scripts\nport.exe" schema</div><p><span class="label">System:</span> Prints the required and conditional <code>positions.csv</code> columns.</p><p><span class="label">Human:</span> Export independent positions to <code>data/intake/&lt;period&gt;/&lt;fund&gt;/positions.csv</code>. If available, place the independent order file beside it as <code>create_redeem_orders.csv</code>.</p><p><span class="label">Stop if:</span> Either file came from or was derived from U.S. Bank or EagleSTAR.</p></div>
<div class="step"><h3>Step 2 - Run the preparation automation</h3><p><span class="label">Run:</span></p><div class="cmd">&amp; ".\.venv\Scripts\nport.exe" prepare FDRS 2026-06 --positions ".\data\intake\2026-06\fdrs\positions.csv" --orders ".\data\intake\2026-06\fdrs\create_redeem_orders.csv"</div><p><span class="label">System:</span> Creates <code>data/funds/fdrs/filings/2026-06/filing_inputs.xlsx</code>, calculates controls for the supplied files, and inserts Bloomberg formulas. Omit <code>--orders</code> when unavailable.</p><p><span class="label">Pass when:</span> The command prints the expected workbook path.</p></div>
<div class="step"><h3>Step 3 - Open and save on Bloomberg</h3><p><span class="label">Run:</span> Open <code>filing_inputs.xlsx</code> in Excel on a logged-in Bloomberg terminal.</p><p><span class="label">System:</span> The Bloomberg Excel Add-In calculates the visible formulas on the <code>Bloomberg</code> sheet.</p><p><span class="label">Human:</span> Wait until formulas show values or explicit Bloomberg errors, then save and close the workbook.</p><p><span class="label">Pass when:</span> The workbook is saved with calculated values; unresolved Bloomberg errors remain visible and will block.</p></div>
<div class="step"><h3>Step 4 - Complete the remaining inputs</h3><p><span class="label">Run:</span> Reopen <code>filing_inputs.xlsx</code>.</p><p><span class="label">Human:</span> Ignore <code>Sources</code> for XML completion. Filter <code>FundFields</code> and <code>HoldingFields</code> to MISSING. For PROVIDED, set <code>status</code> and enter <code>proposedValue</code> only when the automated/current value is absent or must be corrected; fund-config rows require proposedValue when applicable. For NOT_APPLICABLE, leave proposedValue blank and enter <code>status</code> plus a factual <code>comment</code>. In <code>ReconciliationInputs</code>, enter <code>controlValue</code>, <code>tolerance</code>, <code>status</code>, and <code>comment</code>. <code>sourceId</code> is optional everywhere.</p><p><span class="label">Pass when:</span> Build reports zero open XML inputs and validation/reconciliation errors.</p></div>
<div class="step"><h3>Step 5 - Run the final automation</h3><p><span class="label">Run:</span></p><div class="cmd">&amp; ".\.venv\Scripts\nport.exe" build FDRS 2026-06 --from-inputs</div><p><span class="label">System:</span> Checks XML values, policy/applicability, and reconciliation; writes a clean bundle; generates XML; and runs XSD validation.</p><p><span class="label">Human:</span> If NOT READY, correct the exact workbook row or upstream file printed by the command and rerun the same command.</p><p><span class="label">Pass when:</span> The clean bundle and validated XML are written.</p></div>
<div class="step"><h3>Step 6 - Optional aligned comparison</h3><p><span class="label">Run:</span></p><div class="cmd">
&amp; ".\.venv\Scripts\nport.exe" compare-reference --internal ".\output\FDRS_2026-06.xml" --reference "&lt;aligned-reference.xml&gt;"</div><p><span class="label">System:</span> Writes a versioned clean bundle under <code>data/builds/fdrs/2026-06/&lt;run-id&gt;/</code>, writes XML under <code>output/</code>, and performs a read-only comparison.</p><p><span class="label">Human:</span> Confirm the internal and reference outputs use the same fund identity and report date. Document gaps; never copy comparison values back into the filing.</p><p><span class="label">Pass when:</span> The clean bundle, receipt, validated XML, and documented comparison all exist.</p></div>
</div>

<h3>Run the workflow for every fund</h3>
<div class="callout"><b>Scope rule:</b> the service is not limited to FDRS. Each fund has its own positions file, input workbook, clean bundle, and XML.</div>
<p><b>Phase A - generate one input workbook per intake folder.</b> The folder name is the fund ticker.</p>
<div class="cmd">{batch_prepare}</div>
<p><b>Phase B - Bloomberg and remaining inputs.</b> Open, calculate, and save each workbook on Bloomberg; then fill each fund's remaining field rows and ReconciliationInputs control rows.</p>
<p><b>Phase C - build.</b> The loop stops at the first fund that is not ready.</p>
<div class="cmd">{batch_build}</div>

<h3>Complete command reference</h3>
{chunked_t(["Command", "Stage", "What it does", "Writes data?"], [
    [code("nport schema"), "Intake design", "Prints every canonical positions.csv column, type, and applicability rule.", "No"],
    [code("nport prepare <fund> <period> --positions <file> [--orders <file>]"), "Prepare", "Creates filing_inputs.xlsx, gap rows, reconciliation inputs, and Bloomberg formulas.", "Yes - filing_inputs.xlsx"],
    [code("nport build <fund> <period> --from-inputs"), "Validate and build", "Prints exact open inputs/errors or writes the clean bundle and schema-valid XML.", "Only when all inputs and validations clear"],
    [code("nport compare-reference --internal <xml> --reference <xml>"), "Post-build comparison", "Performs a read-only structural comparison after dates and fund identity are aligned.", "No filing inputs"],
    [code("nport check-schema"), "Maintenance", "Checks the local N-PORT schema files and version.", "Cache only when applicable"],
    [code("nport pull --ticker <ticker> --list"), "External research", "Lists recent EDGAR N-PORT filings; it is not an input adapter.", "No, unless an explicit output download is requested"],
], ["38%", "15%", "33%", "14%"], "dense", 4)}
<p><b>Disabled write paths:</b> masters, split, mergehumanreview, enrich, merge, new-filing, build-master, split-master, build-filing-master, and split-filing-master. Do not use them for the independent service.</p>

{human_handoff_html("5")}

<h2>6. Filing input workbook</h2>
{chunked_t(["Sheet", "Key", "What the human edits", "Result", "Release rule"], [
    ["Summary", "Fund + period", "Nothing", "Shows scope, stop rule, and next command", "Read-only"],
    ["Bloomberg", "targetFile + recordKey + fieldName", "Nothing; formulas calculate in Excel", "Supported returns and security/reference values", "Blank/error results remain MISSING"],
    ["GapGuide", "gapId", "Nothing", "Explains every tracked item, evidence template, and exact destination", "Read-only"],
    ["FundFields", "targetFile + fieldName", "PROVIDED: proposedValue if needed + status. N/A: status + factual comment. sourceId optional", "Config and filing-level XML values", "Candidate rows have status MISSING"],
    ["HoldingFields", "recordKey + fieldName", "PROVIDED: status + proposedValue only to supply/correct. N/A: status + factual comment. sourceId optional", "Holding XML exceptions", "Only generated candidate rows"],
    ["Sources", "sourceId", "Nothing required; optional trace only", "Diagnostic sidecar metadata", "Does not gate XML"],
    ["ReconciliationInputs", "checkId", "controlValue, tolerance, status, comment; sourceId optional", "Control side of position-to-GL, flows, and derivative checks", "Every generated difference is within tolerance"],
    ["Reconciliation", "check", "Nothing; correct upstream filed input or ReconciliationInputs", "Build-calculated actual, control, difference, tolerance, and result", "Every automated check passes"],
], ["15%", "17%", "30%", "23%", "15%"], "dense", 4)}
<div class="callout danger"><b>The workbook does not make data true.</b> Enter only known values; never infer from comparison output. Source metadata is optional and does not validate a value.</div>
<p><b>Fund-configuration safeguard:</b> for <code>targetFile=fund_config.txt</code>, enter <code>proposedValue</code>. The existing <code>currentValue</code> is reference-only and cannot be accepted by changing status alone.</p>

<h2>7. Status rules</h2>
    {chunked_t(["Value", "Exact meaning", "Required entry"], [
    ["MISSING", "No usable value has been supplied.", "The row remains an open input when applicable."],
    ["PROVIDED", "A current or proposed value is ready for the build.", "Resolved value and status. sourceId optional."],
    ["NOT_APPLICABLE", "A conditional field does not apply to this fund/holding.", "Status plus a factual reason in comment. sourceId optional."],
    ["SYSTEM_DERIVED", "The system calculates the value from validated period/policy inputs.", "No manual override."],
    ["SYSTEM_CONTROL", "The system owns the release-state value.", "No manual override."],
], ["20%", "40%", "40%"], "dense", 3)}
<p><code>sourceId</code>, <code>sourceAsOf</code>, hashes, and counts are optional diagnostic metadata. None appears in the XML.</p>

<h2>8. Current input checklist and exact fix location</h2>
<div class="callout good"><b>Centralized remediation:</b> use only this fund-period's <code>filing_inputs.xlsx</code>. Enter XML values/dispositions in FundFields or HoldingFields and controls in ReconciliationInputs. Do not create gap-specific templates or complete Sources for release.</div>
{review_location_table}
<h3>Exact fix location and proof</h3>
{gap_action_table}

<h2 class="page">9. How to read the field trace</h2>
<div class="callout danger"><b>Actual lineage is not authorization.</b> The second column states what the current/legacy code really used, including Bloomberg formulas, U.S. Bank custody, EagleSTAR, seeded review workbooks, constants, and no-feed fields. Those legacy writers are disabled or prohibited for the new production build. The fourth column is the only production workflow.</div>
<p>The trace is generated from the canonical config, filing, and holding field maps. Generation stops if field counts change or the verified lineage anchors no longer resolve.</p>
<p class="small">Verification performed: {escape('; '.join(trace_checks))}.</p>

<h2 class="page">10. Exhaustive field trace - fund configuration</h2>
<p>All {len(config_rows)} accepted fund-configuration fields are listed. <code>requiredSources</code>, <code>policySourceRef</code>, <code>policyApprovedBy</code>, and <code>policyApprovedAt</code> are compatibility/provenance keys: they are not requested by the workbook and do not affect XML.</p>
{chunked_t(trace_headers, config_rows, trace_widths, "dense", 4, "Fund configuration")}

<h2 class="page">11. Exhaustive field trace - filing-level data</h2>
<p>All {len(filing_rows)} accepted filing-level fields are listed. A legacy constant is reported as a constant; it is not silently reclassified as sourced data.</p>
{chunked_t(trace_headers, filing_rows, trace_widths, "dense", 4, "Filing-level data")}

<h2 class="page">12. Exhaustive field trace - holdings</h2>
<p>All {len(holding_rows)} accepted holdings fields are listed and grouped by filing condition. Present base values remain tied to the independent POSITIONS source; missing required and exception-sensitive values are surfaced in HoldingFields.</p>
{holding_trace}

<div class="keep"><h2>13. Release decision</h2>
<p><code>nport build &lt;fund&gt; &lt;period&gt; --from-inputs</code> writes output only after every applicable XML value and policy/applicability input is resolved, all reconciliations pass, canonical validation passes, and XSD validation passes. Source metadata does not gate release. Explicit U.S. Bank/EagleSTAR/prepared-filing input references remain prohibited.</p></div>
"""
    return shell("N-PORT In-House Runbook", "A field-by-field operating guide showing what supplies each value, exactly where it is entered, how the input workflow runs, and what blocks release.", body)


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "nport_final_inhouse_audit_2026-08-03.html").write_text(audit_html(), encoding="utf-8")
    (DOCS / "nport_runbook.html").write_text(runbook_html(), encoding="utf-8")


if __name__ == "__main__":
    main()
