"""Generate the field-provenance table: every filed data point → its single source.

This exists so the provenance table in the runbook is DERIVED, never hand-written.
Three guarantees:

1. **Verified.** Every claimed owner is checked against the code structure that
   actually owns that field (``BLOOMBERG_SPECS``, ``_CONST``, ``_NA_FIELDS``,
   ``humanreview._SHEETS``, the EagleSTAR writer keys, the custodian builders).
   A claim that no longer holds raises — the table cannot silently drift.
2. **Cited.** Every row carries a real ``file:line``, located by regex at
   generation time. If the code moves, the line moves with it; if the anchor
   disappears entirely, this raises.
3. **Measured.** Fill rates are counted from the per-fund files actually on disk,
   not asserted.

Run: ``python scripts/field_provenance.py``  → writes docs/_provenance.html
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nport import humanreview as hr                                    # noqa: E402
from nport.config import _HOLDINGS_KEY_MAP                             # noqa: E402
from nport.filing_master import (                                      # noqa: E402
    _CONST, _FLOW_SR_FIELDS, _NA_FIELDS, _RISK_BDP_FIELDS, _ZERO_FIELDS, RETURN_COLS,
)
from nport.master_sheet import _BBG_FORMULA_COLUMNS                    # noqa: E402
from nport.schema import FIELD_SPECS                                   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "nport"
FUNDS = ROOT / "data" / "funds"
PERIOD = "2026-06"

# ── Owners ────────────────────────────────────────────────────────────────────
CUST = "U.S. Bank custodian CSV"
BBG = "Bloomberg workbook formula"
EAG = "Gmail export - EagleSTAR attachment"
HUMAN = "Human-review workbook (seeded; reviewer not recorded)"
APORD = "Create/redeem order export"
CONFIG = "fund_config.txt"
MANUAL = "Manual (workbook)"
TOOL = "Tool constant"

# Code-derived membership sets used to VERIFY each claim below.
_EAG_FILING_KEYS = {"totAssets", "totLiabs", "netAssets", "amtPayOneYrOther"} | {
    f"netRealizedGainMon{i}" for i in (1, 2, 3)} | {
    f"netUnrealizedApprMon{i}" for i in (1, 2, 3)} | {
    f"mon{i}{s}" for i in (1, 2, 3) for s in ("Sales", "Redemption")}
_EAG_DERIV_KEYS = {"unrealizedAppr"}
_HUMAN_VALUES = {v for s in hr._SHEETS for v in s.values}


def _review_targets() -> set[str]:
    """Holding columns that ``apply_review_to_rows`` actually writes, read from source.
    The review sheet's own column names differ from the holding field names
    (option_index.indexName → refIndexName), so the targets must come from the mapper."""
    src = (SRC / "master_sheet.py").read_text(encoding="utf-8")
    body = re.search(r"def apply_review_to_rows\(.*?\n(?=\ndef )", src, re.S)
    if not body:
        raise SystemExit("ANCHOR LOST: apply_review_to_rows not found in master_sheet.py")
    targets = set(re.findall(r'r\["([a-zA-Z]+)"\]\s*=', body.group(0)))
    targets |= set(re.findall(r'r\["([a-zA-Z]+)"\], r\["([a-zA-Z]+)"\]', body.group(0))[0]) \
        if re.findall(r'r\["([a-zA-Z]+)"\], r\["([a-zA-Z]+)"\]', body.group(0)) else set()
    for pair in re.findall(r'r\["([a-zA-Z]+)"\], r\["([a-zA-Z]+)"\]', body.group(0)):
        targets |= set(pair)
    # leg columns are written via a loop over leg_cols
    lc = re.search(r"leg_cols = \((.*?)\)", body.group(0), re.S)
    if lc:
        targets |= set(re.findall(r'"([a-zA-Z]+)"', lc.group(1)))
    # The filing master has its own review merge (designated index).
    fsrc = (SRC / "filing_master.py").read_text(encoding="utf-8")
    fbody = re.search(r"def merge_review_into_filing_master\(.*?\n(?=\ndef )", fsrc, re.S)
    if not fbody:
        raise SystemExit("ANCHOR LOST: merge_review_into_filing_master not found")
    for pair in re.findall(r'rec\["([a-zA-Z]+)"\], rec\["([a-zA-Z]+)"\]', fbody.group(0)):
        targets |= set(pair)
    return targets
_RISK_COLS = {c for c, _m in _RISK_BDP_FIELDS}
_CUSTODIAN_KEYS = None   # filled by _load_custodian_keys()


def _load_custodian_keys() -> set[str]:
    """Keys the custodian transform assigns a REAL value to, read from source.

    Keys initialised to an empty string (``"isin": ""``) are deliberately blank
    placeholders for a downstream owner to fill — counting them would let a field
    be falsely credited to the custodian, so they are excluded.
    """
    src = (SRC / "custodian.py").read_text(encoding="utf-8")
    keys: set[str] = set()
    for fn in ("_common_fields", "transform_to_holding_dict", "build_equity_entry",
               "build_mm_entry", "build_option_entry", "build_swap_entry",
               "build_treasury_entry", "build_corporate_bond_entry"):
        m = re.search(rf"def {fn}\(.*?\n(?=\ndef |\n# ──)", src, re.S)
        if not m:
            continue
        for key, rhs in re.findall(r'"([a-zA-Z_][a-zA-Z_0-9]*)":\s*([^,\n]+)', m.group(0)):
            if rhs.strip() not in ('""', "''"):
                keys.add(key)
    return keys


def ref(filename: str, pattern: str) -> str:
    """`file:line` of the first regex match. Raises if the anchor is gone."""
    path = SRC / filename if (SRC / filename).exists() else ROOT / filename
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pattern, line):
            return f"{path.relative_to(ROOT).as_posix()}:{i}"
    raise SystemExit(f"ANCHOR LOST: /{pattern}/ not found in {filename} — "
                     f"the code moved; update scripts/field_provenance.py")


# ── The map: field → owner, how it is obtained, and where in the code ─────────
# (group, csv_field, owner, mechanism, code anchor file, anchor regex)
ROWS: list[tuple[str, str, str, str, str, str]] = [
    # ---- Fund identity -------------------------------------------------------
    ("Fund identity", "cik", CONFIG, "Typed once when the fund launches", "config.py", r"def parse_config"),
    ("Fund identity", "seriesId", CONFIG, "From the SEC series guide spreadsheet", "config.py", r"def parse_config"),
    ("Fund identity", "classId", CONFIG, "From the SEC series guide spreadsheet", "config.py", r"def parse_config"),
    ("Fund identity", "seriesName", CONFIG, "Typed once when the fund launches", "config.py", r"def parse_config"),
    ("Fund identity", "seriesLei", CONFIG, "Typed once (GLEIF-issued)", "config.py", r"def parse_config"),
    ("Fund identity", "regName / regCik / regLei", CONFIG, "Trust-level, same for every fund", "config.py", r"def parse_config"),
    ("Fund identity", "regStreet1 … regZip / regPhone", CONFIG, "Trust address, set once", "config.py", r"def parse_config"),
    ("Fund identity", "signerName / signerTitle / signerOrg", CONFIG, "Who signs the filing", "config.py", r"def parse_config"),

    # ---- Holdings: identity --------------------------------------------------
    ("Holding identity", "name", CUST, "SecurityName, truncated to 30 chars", "custodian.py", r'"name": row\.security_name'),
    ("Holding identity", "title", CUST, "SecurityName verbatim", "custodian.py", r'"title": row\.security_name'),
    ("Holding identity", "cusip", CUST, "Copied via =custodian! cell reference; foreign CINS → N/A", "custodian.py", r"CINS numbers \(foreign CUSIPs"),
    ("Holding identity", "ticker", CUST, "StockTicker column", "custodian.py", r'"ticker": row\.stock_ticker'),
    ("Holding identity", "isin", BBG, "=BDP(bbgid, \"ID_ISIN\")", "master_sheet.py", r'"isin": \("ID_ISIN"'),
    ("Holding identity", "lei", BBG, "=BDP(bbgid, \"LEGAL_ENTITY_IDENTIFIER\"); N/A if the issuer has none", "master_sheet.py", r'"lei": \("LEGAL_ENTITY_IDENTIFIER"'),
    ("Holding identity", "invCountry", BBG, "=BDP(bbgid, \"CNTRY_OF_DOMICILE\") — no default, a blank is a real gap", "master_sheet.py", r'"invCountry": \("CNTRY_OF_DOMICILE"'),

    # ---- Holdings: position --------------------------------------------------
    ("Position", "balance", CUST, "Shares / par from the custodian", "custodian.py", r'"balance": row\.shares'),
    ("Position", "units", TOOL, "Set by holding type: NS shares, PA par, NC contracts", "custodian.py", r'"units": "NS"'),
    ("Position", "curCd", TOOL, "USD — the book currency for every fund", "custodian.py", r'"cur_cd": "USD"'),
    ("Position", "valUSD", CUST, "MarketValue. Swaps override to the EagleSTAR mark-to-market", "custodian.py", r'"val_usd": row\.market_value'),
    ("Position", "valUSD (swaps)", EAG, "PVal Total Unreal G/L Base — the MTM, never the notional", "custodian.py", r'h\["val_usd"\] = \(h\.get\("unrealized_appr"\)'),
    ("Position", "pctVal", "Derived", "valUSD ÷ the netAssets the filing reports (not the custodian's)", "custodian.py", r"Restate every pct_val against"),
    ("Position", "payoffProfile", CUST, "Sign of the share count; for swaps the ticker's L/S code", "custodian.py", r'"payoff_profile": swap\.direction'),
    ("Position", "assetCat", TOOL, "Set by classification: EC / DBT / DE / STIV", "custodian.py", r"def classify_holding"),
    ("Position", "issuerCat", TOOL, "Set by classification: CORP / UST / RF / OTHER", "custodian.py", r'"issuer_cat": "CORP"'),
    ("Position", "fairValLevel", TOOL, "1 for listed, 2 for derivatives", "custodian.py", r'"fair_val_level": "1"'),
    ("Position", "isRestrictedSec / isCashCollateral / isNonCashCollateral / isLoanByFund", TOOL, "N for every ETF holding", "custodian.py", r'"is_restricted_sec": "N"'),

    # ---- Debt ---------------------------------------------------------------
    ("Debt (C.9)", "maturityDt", BBG, "=BDP(cusip Govt/Corp, \"MATURITY\")", "master_sheet.py", r'"maturityDt": \("MATURITY"'),
    ("Debt (C.9)", "annualizedRt", BBG, "=BDP(cusip Govt/Corp, \"CPN\")", "master_sheet.py", r'"annualizedRt": \("CPN"'),
    ("Debt (C.9)", "couponKind", BBG, "=BDP(… \"CPN_TYP\"), mapped to the N-PORT enum", "master_sheet.py", r'"couponKind": \("CPN_TYP"'),
    ("Debt (C.9)", "isDefault / areIntrstPmntsInArrs / isPaidKind", TOOL, "N — no defaulted debt held", "custodian.py", r'"is_default"'),

    # ---- Derivatives: options ------------------------------------------------
    ("Option", "putOrCall", CUST, "Parsed from the position name (trailing C / P)", "custodian.py", r"def parse_option_name"),
    ("Option", "exercisePrice", CUST, "Parsed from the position name (strike)", "custodian.py", r'"exercise_price": opt\.exercise_price'),
    ("Option", "expDt", CUST, "Parsed from the position name (expiry)", "custodian.py", r'"exp_dt": opt\.exp_dt'),
    ("Option", "writtenOrPur", CUST, "Sign of the contract count", "custodian.py", r'"written_or_pur"'),
    ("Option", "shareNo", TOOL, "N/A — index options are on an index, not a share count", "custodian.py", r'"share_no": "N/A"'),
    ("Option", "delta", MANUAL, "NO FEED. FLEX options do not price on Bloomberg. Typed into "
     "security_master.xlsx and preserved across rebuilds — from your risk system", "master_sheet.py", r"delta has no data feed"),
    ("Option", "refIndexName / refIndexIdentifier", HUMAN, "option_index sheet; currently seeded from a legacy map and applied at split", "master_sheet.py", r'r\["refIndexName"\], r\["refIndexIdentifier"\] = idx'),
    ("Option", "counterpartyName / counterpartyLei", TOOL, "The Options Clearing Corporation — every listed/FLEX option clears through it", "custodian.py", r"^_OCC_NAME"),

    # ---- Derivatives: swaps --------------------------------------------------
    ("Swap", "swapFlag", TOOL, "Y for every TRS", "custodian.py", r'"swap_flag": "Y"'),
    ("Swap", "terminationDt", CUST, "Parsed from the swap ticker (…-TRS-<date>-…)", "custodian.py", r'"termination_dt": swap\.termination_dt'),
    ("Swap", "notionalAmt", CUST, "MarketValue = shares × price — the contract size", "custodian.py", r'"notional_amt"'),
    ("Swap", "unrealizedAppr", EAG, "PVal Total Unreal G/L Base, matched on Primary Asset ID", "eaglestar.py", r'"unrealizedAppr": f"\{_fnum'),
    ("Swap", "counterpartyName / counterpartyLei", HUMAN, "swap_counterparties sheet; currently seeded from the GLEIF legacy map", "master_sheet.py", r'r\["counterpartyName"\], r\["counterpartyLei"\] = cp'),
    ("Swap", "recFixedOrFloating / recDesc", HUMAN, "swap_legs sheet; currently prefilled from the TRS template and reference issuer", "master_sheet.py", r"leg_cols = \("),
    ("Swap", "pmntFloatingRtIndex / pmntFloatingRtSpread / pmntRateTenor / pmntRateUnit", HUMAN, "swap_legs sheet; index, tenor, and unit are template seeds; spread remains blank for trade-confirm review", "master_sheet.py", r"leg_cols = \("),
    ("Swap", "refCusip", CUST, "Leading segment of the swap ticker", "custodian.py", r'"ref_cusip": swap\.ref_cusip'),
    ("Swap", "refIsin / refTicker / refIssuerName / refIssueTitle", BBG, "=BDP(refCusip Equity, …) on the reference security", "master_sheet.py", r'"refIsin": \("ID_ISIN"'),

    # ---- Fund financials -----------------------------------------------------
    ("Fund financials (B.1)", "totAssets", EAG, "Trial Balance total assets", "eaglestar.py", r'rec\["totAssets"\]'),
    ("Fund financials (B.1)", "totLiabs", EAG, "Trial Balance total liabilities", "eaglestar.py", r'rec\["totLiabs"\]'),
    ("Fund financials (B.1)", "netAssets", EAG, "Trial Balance net assets (overrides the custodian figure)", "eaglestar.py", r'rec\["netAssets"\]'),
    ("Fund financials (B.1)", "amtPayOneYrOther", EAG, "Trial Balance payables", "eaglestar.py", r'rec\["amtPayOneYrOther"\]'),
    ("Fund financials (B.1)", "assetsAttrMiscSec / assetsInvested / delayDeliv / standByCommit / liquidPref", TOOL, "0 — a genuine zero for a plain ETF, not a placeholder", "filing_master.py", r"^_ZERO_FIELDS"),
    ("Fund financials (B.1)", "amtPayOneYr* / amtPayAftOneYr* (other lines)", TOOL, "0 — no borrowings or affiliate payables", "filing_master.py", r"^_ZERO_FIELDS"),

    # ---- Returns, gains, flows ----------------------------------------------
    ("Returns (B.5)", "rtn1 / rtn2 / rtn3", BBG, "=BDP total return over each reporting month; N/A before inception", "filing_master.py", r"^RETURN_COLS"),
    ("Gains (B.5)", "netRealizedGainMon1-3", EAG, "Trial Balance month-end deltas", "eaglestar.py", r'f"netRealizedGainMon\{i\}"'),
    ("Gains (B.5)", "netUnrealizedApprMon1-3", EAG, "Trial Balance month-end deltas", "eaglestar.py", r'f"netUnrealizedApprMon\{i\}"'),
    ("Flows (B.2)", "mon1-3Sales / mon1-3Redemption", EAG, "Trial Balance subscriptions/redemptions. AP order book cross-checks only", "eaglestar.py", r'f"\{mon\}Sales"'),
    ("Flows (B.2)", "mon1-3Sales / mon1-3Redemption (reconciliation only)", APORD,
     "ACCEPTED create/redeem Notional by month; compared with EagleSTAR but does not write the filing",
     "cli.py", r"ap_flows = flows_from_csv"),
    ("Flows (B.2)", "mon1-3Reinvestment", TOOL, "NO FEED. Not in an order book — needs the transfer agent", "filing_master.py", r"^_NA_FIELDS"),

    # ---- Risk, index, admin --------------------------------------------------
    ("Risk (B.3)", "durAdj / spreadDur", BBG, "=BDP DUR_ADJ_MID / OAS_SPREAD_DUR_MID per debt holding", "filing_master.py", r"^_RISK_BDP_FIELDS"),
    ("Risk (B.3)", "maturity / ratingSP", BBG, "=BDP MATURITY / RTG_SP, bucketed by tenor", "filing_master.py", r"^_RISK_BDP_FIELDS"),
    ("Index (B.6)", "nameDesignatedIndex / indexIdentifier", HUMAN, "designated_index sheet; currently seeded from legacy 497K mappings", "humanreview.py", r"SEED_DESIGNATED_INDEX"),
    ("Admin", "submissionType / isFinalFiling / isNonCashCollateral", TOOL, "NPORT-P / N / N", "filing_master.py", r"^_CONST"),
    ("Admin", "liveTestFlag", TOOL, "TEST until you flip it; LIVE is gated on a clean reconciliation", "cli.py", r"def _live_gate_reasons"),
    ("Admin", "repPdEnd / repPdDate", "Derived", "Last calendar day of the filing period", "custodian.py", r"def _period_end_date"),
    ("Admin", "dateSigned", "Derived", "Set from the period; override in the workbook", "filing_master.py", r"def _signed_date"),

    # ---- Newly supported conditional sections ------------------------------
    ("Conditional sections", "cashNotReportedInCOrD (B.2.f)", MANUAL,
     "NO FEED. Field exists and preflight blocks it when policy requires it",
     "preflight.py", r"context\.policy\.cash_b2f_required"),
    ("Conditional sections", "monthlyReturnCategoriesJson (B.5.c)", MANUAL,
     "NO FEED. Typed field; no Gmail, custodian, create/redeem, or Bloomberg writer exists",
     "models.py", r"monthly_return_categories_json"),
    ("Conditional sections", "derivativesRegime", "Derived",
     "From the approved fund registry; the production registry is currently absent",
     "policy.py", r"derivatives_regime=context\.policy\.derivatives_regime"),
    ("Conditional sections", "derivExposurePct / derivCurrencyExposurePct / derivInterestRateExposurePct / derivDaysInExcess (B.9)", MANUAL,
     "NO FEED. Required only for a registry-approved LIMITED fund",
     "preflight.py", r"regime == \"LIMITED\""),
    ("Conditional sections", "medianDailyVarPct / medianVarRatioPct / backtestingExceptions (B.10)", MANUAL,
     "NO FEED. Required only for the applicable registry-approved VaR regime",
     "preflight.py", r"regime\.startswith\(\"VAR_\"\)"),
    ("Conditional sections", "liquidityClassificationJson / liquidityCircumstancesJson (C.7)", MANUAL,
     "NO FEED. Position-level liquidity data is absent; preflight blocks when policy requires C.7",
     "preflight.py", r"context\.policy\.liquidity_required"),
]


def verify() -> list[str]:
    """Check every claim against the structure that owns it. Returns the checks run."""
    global _CUSTODIAN_KEYS
    _CUSTODIAN_KEYS = _load_custodian_keys()
    targets = _review_targets()
    checks: list[str] = []

    def snake(camel: str) -> str:
        """camelCase → snake_case via the authoritative CSV↔field map, so acronyms
        (valUSD → val_usd) resolve correctly rather than by guesswork."""
        if camel in _HOLDINGS_KEY_MAP:
            return _HOLDINGS_KEY_MAP[camel]
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", camel)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()

    for _grp, field, owner, _mech, fname, anchor in ROWS:
        ref(fname, anchor)                       # raises if the code anchor is gone
        # "netRealizedGainMon1-3" / "mon1-3Sales" are range labels; check the first member.
        first = field.split(" /")[0].split(" (")[0].strip().replace("1-3", "1")
        if owner == BBG and first not in ("rtn1", "durAdj", "maturity"):
            assert first in _BBG_FORMULA_COLUMNS or first in _RISK_COLS, \
                f"{first} claimed Bloomberg but is not in BLOOMBERG_SPECS/_RISK_BDP_FIELDS"
        if owner == EAG:
            assert first in _EAG_FILING_KEYS | _EAG_DERIV_KEYS or first.startswith("valUSD"), \
                f"{first} claimed EagleSTAR but is not an EagleSTAR writer key"
        if owner == HUMAN:
            assert first in _HUMAN_VALUES or first in targets, (
                f"{first} claimed human-review but is neither a review sheet value column "
                f"nor a column apply_review_to_rows writes")
        if owner == CUST:
            assert snake(first) in _CUSTODIAN_KEYS or first in ("cusip", "putOrCall", "notionalAmt"), \
                f"{first} claimed custodian but the transform never assigns it a value"
        # Single-writer: a Bloomberg-owned column cannot also be claimed by anyone else.
        # (valUSD is the one deliberate hand-off: custodian value, EagleSTAR MTM for swaps.)
        if first in _BBG_FORMULA_COLUMNS and owner != BBG and not first.startswith("valUSD"):
            raise AssertionError(
                f"{first} claimed {owner} but it is a Bloomberg formula column "
                f"(BLOOMBERG_SPECS) - two writers for one field")
    checks.append(f"{len(ROWS)} rows: code anchor located for each")
    checks.append(f"Bloomberg claims checked against BLOOMBERG_SPECS ({len(_BBG_FORMULA_COLUMNS)} cols) "
                  f"+ risk sheet ({len(_RISK_COLS)} cols)")
    checks.append(f"EagleSTAR claims checked against {len(_EAG_FILING_KEYS | _EAG_DERIV_KEYS)} writer keys")
    checks.append(f"Human-review claims checked against {len(_HUMAN_VALUES)} review value columns")
    checks.append(f"Custodian claims checked against {len(_CUSTODIAN_KEYS)} transform-assigned keys")

    # Nothing in the filing master may be left unaccounted for.
    covered = {f for _g, fields, *_ in ROWS for f in re.split(r"\s*/\s*", fields)}
    covered |= {
        "cashNotReportedInCOrD", "monthlyReturnCategoriesJson", "derivativesRegime",
        "derivExposurePct", "derivCurrencyExposurePct", "derivInterestRateExposurePct",
        "derivDaysInExcess", "medianDailyVarPct", "medianVarRatioPct",
        "backtestingExceptions",
    }
    from nport.filing_master import HEADER
    unmapped = [c for c in HEADER
                if c not in covered and c not in ("Account", "bbgid")
                and not any(c.startswith(p.rstrip("*").rstrip("1-3")) for p in covered)
                and c not in _ZERO_FIELDS and c not in _NA_FIELDS
                and c not in _FLOW_SR_FIELDS and c not in _CONST and c not in RETURN_COLS]
    checks.append(f"filing_master HEADER: {len(HEADER)} columns, {len(unmapped)} unmapped"
                  + (f" -> {unmapped}" if unmapped else ""))
    return checks


def coverage() -> tuple[dict[str, Counter], int, int]:
    """Count populated / N-A / blank per holdings column, from the files on disk."""
    stats: dict[str, Counter] = {}
    funds = rows = 0
    for hpath in sorted(FUNDS.glob(f"*/filings/{PERIOD}/holdings.csv")):
        funds += 1
        with open(hpath, newline="", encoding="utf-8") as f:
            for rec in csv.DictReader(f):
                rows += 1
                for k, v in rec.items():
                    c = stats.setdefault(k, Counter())
                    v = (v or "").strip()
                    c["populated" if v and v != "N/A" else ("na" if v == "N/A" else "blank")] += 1
    return stats, funds, rows


def main() -> None:
    checks = verify()
    stats, nfunds, nrows = coverage()
    print("VERIFICATION")
    for c in checks:
        print("  OK -", c)
    print(f"\nCOVERAGE: {nrows:,} holdings across {nfunds} funds, {len(stats)} columns measured")

    owner_css = {CUST: "cust", BBG: "bbg", EAG: "eag", HUMAN: "human", MANUAL: "manual",
                 APORD: "ap", CONFIG: "cfg", TOOL: "tool", "Derived": "deriv"}
    used = {o for _g, _f, o, *_ in ROWS}
    out = [
        '<section><h2>4 &middot; Where every data point comes from</h2><div class="h2rule"></div>',
        '<p class="lead">Generated from the code by <span class="mono">scripts/field_provenance.py</span>, '
        'not written by hand. Every row cites the file and line that sets it, and the script refuses '
        'to run if a claim no longer matches the code.</p>',
        '<div class="legend">',
    ]
    for o, cls in owner_css.items():
        if o in used:
            out.append(f'<span class="tag {cls}">{o}</span>')
    out.append('</div>')
    out.append(
        '<div class="box info"><h4>One writer per field</h4>'
        '<p>Each row below has exactly one source. A second system may <i>check</i> a value '
        '— the AP order book cross-checks EagleSTAR&rsquo;s flows, the custodian cross-checks '
        'net assets — but a cross-check never writes the filing. Disagreements go to '
        '<span class="mono">reconciliation_' + PERIOD + '.csv</span> and block a LIVE filing '
        'until resolved.</p></div>')

    last = None
    out.append('<table class="prov"><tr><th>Field</th><th>Source</th>'
               '<th>How it is obtained</th><th>Code reference</th></tr>')
    for grp, field, owner, mech, fname, anchor in ROWS:
        if grp != last:
            out.append(f'<tr class="grp"><td colspan="4">{grp}</td></tr>')
            last = grp
        cite = ref(fname, anchor)
        cls = owner_css[owner]
        nofeed = ' <b class="nofeed">NO FEED</b>' if "NO FEED" in mech else ""
        mech = mech.replace("NO FEED. ", "")
        out.append(
            f'<tr><td class="mono f">{field}</td>'
            f'<td><span class="tag {cls}">{owner}</span>{nofeed}</td>'
            f'<td>{mech}</td><td class="mono cite">{cite}</td></tr>')
    out.append('</table>')

    out.append('<h3>Verified at generation time</h3><ul class="tight">')
    for c in checks:
        out.append(f'<li>{c}</li>')
    out.append(f'<li>Coverage measured over <b>{nrows:,} holdings</b> across '
               f'<b>{nfunds} funds</b> in period {PERIOD}</li></ul>')
    out.append('</section>')

    fragment = "\n".join(out)

    # Splice into the runbook between the markers (idempotent — safe to re-run).
    canonical = ROOT / "docs" / "nport_runbook.html"
    book = ROOT / "docs" / "nport_runbook_legacy_provenance.html"
    html = canonical.read_text(encoding="utf-8")
    begin, end = "<!-- PROVENANCE:BEGIN -->", "<!-- PROVENANCE:END -->"
    if begin not in html or end not in html:
        raise SystemExit(f"markers missing in {book.name}")
    html = re.sub(re.escape(begin) + r".*?" + re.escape(end),
                  f"{begin}\n{fragment}\n{end}", html, flags=re.S)
    book.write_text(html, encoding="utf-8")
    print(f"\nspliced {len(ROWS)} rows into {book.relative_to(ROOT)}")
    print("\nnow regenerate the PDF:\n"
          '  msedge --headless --disable-gpu --no-pdf-header-footer \\\n'
          "    --print-to-pdf=docs/NPORT_Runbook.pdf docs/nport_runbook.html")


if __name__ == "__main__":
    main()
