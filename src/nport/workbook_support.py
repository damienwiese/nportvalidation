"""Bloomberg formula and normalization helpers for filing input workbooks."""

from __future__ import annotations

import calendar
import re
from datetime import datetime

BLOOMBERG_SPECS = {
    "EC": (
        lambda row: f"{(row.get('ticker') or '').strip()} US Equity",
        {"isin": ("ID_ISIN", "value"), "lei": ("LEGAL_ENTITY_IDENTIFIER", "value"),
         "invCountry": ("CNTRY_OF_DOMICILE", "value")},
    ),
    "STIV": (
        lambda row: f"{(row.get('ticker') or '').strip()} US Equity",
        {"isin": ("ID_ISIN", "value"), "lei": ("LEGAL_ENTITY_IDENTIFIER", "value"),
         "invCountry": ("CNTRY_OF_DOMICILE", "value")},
    ),
    "DBT_UST": (
        lambda row: f"{(row.get('cusip') or '').strip()} Govt",
        {"isin": ("ID_ISIN", "value"), "lei": ("LEGAL_ENTITY_IDENTIFIER", "value"),
         "invCountry": ("CNTRY_OF_DOMICILE", "value"), "maturityDt": ("MATURITY", "date"),
         "annualizedRt": ("CPN", "value"), "couponKind": ("CPN_TYP", "couponKind")},
    ),
    "DBT_CORP": (
        lambda row: f"{(row.get('cusip') or '').strip()} Corp",
        {"isin": ("ID_ISIN", "value"), "lei": ("LEGAL_ENTITY_IDENTIFIER", "value"),
         "invCountry": ("CNTRY_OF_DOMICILE", "value"), "maturityDt": ("MATURITY", "date"),
         "annualizedRt": ("CPN", "value"), "couponKind": ("CPN_TYP", "couponKind")},
    ),
    "SWP_REF": (
        lambda row: f"{(row.get('refCusip') or '').strip()} Equity",
        {"refIsin": ("ID_ISIN", "value"), "refTicker": ("TICKER", "value"),
         "refIssuerName": ("ISSUER", "value"), "refIssueTitle": ("NAME", "value")},
    ),
}

_COUPON_KIND_MAP = {
    "FIXED": "Fixed", "FLOATING": "Floating", "VARIABLE": "Variable",
    "NONE": "None", "ZERO": "None", "ZERO COUPON": "None", "ZERO CPN": "None",
    "PAY-IN-KIND": "Fixed", "PAY IN KIND": "Fixed", "PIK": "Fixed",
}


def normalize_date(value: str) -> str:
    text = (value or "").strip()
    if not text or re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def normalize_coupon_kind(value: str) -> str:
    text = (value or "").strip()
    return _COUPON_KIND_MAP.get(text.upper(), text) if text else ""


def bloomberg_spec_key(row: dict[str, str]) -> str | None:
    if (row.get("derivCat") or "").strip() == "SWP" and (row.get("refCusip") or "").strip():
        return "SWP_REF"
    asset = (row.get("assetCat") or "").strip()
    if asset in {"EC", "STIV"}:
        return asset
    if asset == "DBT":
        issuer = (row.get("issuerCat") or "").strip()
        if not issuer:
            return None
        return "DBT_UST" if issuer == "UST" else "DBT_CORP"
    return None


def bloomberg_formula(mnemonic: str, key_cell: str, kind: str) -> str:
    call = f'BDP({key_cell},"{mnemonic}")'
    return f'=TEXT({call},"yyyy-mm-dd")' if kind == "date" else f"={call}"


def month_ranges(period: str) -> list[tuple[str, str]]:
    year, month = (int(part) for part in period.split("-"))
    ranges: list[tuple[str, str]] = []
    for back in (2, 1, 0):
        yy, mm = year, month - back
        while mm <= 0:
            mm += 12
            yy -= 1
        last = calendar.monthrange(yy, mm)[1]
        ranges.append((f"{yy:04d}{mm:02d}01", f"{yy:04d}{mm:02d}{last:02d}"))
    return ranges


def return_formula(bbgid_cell: str, start: str, end: str) -> str:
    return (f'=BDP({bbgid_cell},"CUST_TRR_RETURN_HOLDING_PER",'
            f'"CUST_TRR_START_DT","{start}","CUST_TRR_END_DT","{end}","CUST_TRR_CRNCY","USD")')
