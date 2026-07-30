"""Human-review workbook — the one sanctioned place a non-feed value enters a filing.

``data/humanreview/<period>_review.xlsx``, one sheet per category. The pipeline surfaces
two things here for a person to handle:

* **gaps** — a required field with no reliable feed (a security Bloomberg has no country
  for, a swap with no leg economics, a fund with no designated index), and
* **sus values** — low-confidence values that are ideal for a human to confirm.

The operator fills/edits the value cells; ``split``/``build`` read them back as a traceable
``REVIEWED`` source (recorded in the provenance manifest). An unfilled REQUIRED cell stays
blank → tagged ``GAP`` → blocks LIVE (see the reconciliation/LIVE gate).

The reference categories (designated index, swap counterparties, option underlying index)
are the hardcoded maps that USED to live in ``custodian.py`` / ``filing_master.py``; they are
seeded ONCE from the legacy literals below and thereafter owned by the workbook — no
code-embedded guessing. Per-item categories (swap legs, invCountry, isin, sus) are generated
from the current holdings each run, pre-filled with what's known, blank where a human must act.

Rebuild preserves operator edits: an existing workbook's filled cells survive; only new
rows/categories are added (same keep-manual contract as the master workbooks). Read at
split/build needs no Bloomberg terminal — the workbook is plain xlsx.
"""
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook, load_workbook

# ── Legacy literals, relocated here as ONE-TIME migration seeds ────────────────
# These were hardcoded maps in custodian.py / filing_master.py. They seed a fresh
# workbook; once the operator has reviewed/saved, the workbook is the source of truth.

SEED_SWAP_COUNTERPARTIES = {
    # code -> (legalName, lei)  — GLEIF-verified
    "CANT": ("Cantor Fitzgerald & Co.", "5493004J7H4GCPG6OB62"),
    "CLST": ("Clear Street LLC", "549300KNQS43Y7TO3X67"),
    "CS": ("Clear Street LLC", "549300KNQS43Y7TO3X67"),
    "MREX": ("Marex Capital Markets Inc.", "5493006BWPDUCYG6EQ34"),
}

SEED_OPTION_INDEX = {
    # option underlying -> (indexName, indexIdentifier)
    "SPY": ("S&P 500 Index", "SPX"),
    "QQQ": ("NASDAQ 100 Index", "NDX"),
    "IWM": ("Russell 2000 Index", "RTY"),
    "EEM": ("MSCI Emerging Markets Index", "MXEF"),
    "EFA": ("MSCI EAFE Index", "MXEA"),
}

# The default total-return-swap leg economics that custodian.build_swap_entry used to
# hardcode for EVERY swap. Used to pre-fill the swap_legs sheet (recDesc is per-swap, so
# it's filled from the reference issuer at generation time, not seeded here).
SEED_SWAP_LEG_TEMPLATE = {
    "recFixedOrFloating": "Other",
    "pmntFloatingRtIndex": "USD-SOFR",
    "pmntFloatingRtSpread": "",          # from the swap confirm — operator fills
    "pmntRateTenor": "Month",
    "pmntRateUnit": "3",
}

# Designated broad-based index per fund (ticker -> (indexName, indexIdentifier)).
# Relocated from filing_master._DESIGNATED_INDEX (sourced from each fund's 497K).
_SEED_INDEX_NAME = {
    "SPX": "S&P 500 Index", "SPXT": "S&P 500 Total Return Index",
    "NDX": "Nasdaq-100 Index", "RTY": "Russell 2000 Index",
    "MXWD": "MSCI ACWI Index", "MXEF": "MSCI Emerging Markets Index", "MXEA": "MSCI EAFE Index",
    "CFIIBL3P": "FTSE US Treasury Bill 3-12 Months Index",
    "SBMMTB3": "FTSE 3-Month US Treasury Bill Index",
    "CFIIH52C": "FTSE US High-Yield Market 0-5 Years 2% Capped Index",
    "CFIIBD37": "FTSE US Treasury 3-7 Years Index",
    "SBUSC15U": "FTSE US Broad Investment-Grade Corporate Bond 1-5 Years Index",
    "SBUST13U": "FTSE US Treasury 1-3 Years Index",
}
_SEED_BENCHMARK_FUNDS = {
    "SPX": ("AV BAY BLCK BREW BZZ CBOT CJUN CMAG CQTM CTJN DIPR EUV EUVX EYES GASZ GLAM GNMX "
            "HJUN HMAY HULL JOUL JUNC KYC LATR NYNY ODDZ OWN PTNT STYL USX VBX VOOX WATS WNDR "
            "WR XA XAGI XBIX XCOM XHOA XIWC XKRE XLBX XLEX XLFX XLKX XLPX XLUX XLVX XLYX XPAV "
            "XSEM XVO XVUG YUNG "
            "ACLZ ACMM CAMC CARX CRUC KEYX LASC LRNX MNSX MSIX ONTX SIMX TPLX UMCX"),
    "SPXT": "FDRS GPTZ CMAY MAYC",
    "NDX": "QJN QMY QQJN QQMY",
    "RTY": "SCJN SCMY",
    "MXWD": "BRZX CCPX EMXX KRWX TAJX WEBX WX XW XTAI",
    "MXEF": "EMJN EMMY",
    "MXEA": "IDJN IDMY",
    "CFIIBL3P": "CBIL", "SBMMTB3": "CGOV", "CFIIH52C": "CHYG",
    "CFIIBD37": "CIEI", "SBUSC15U": "CIVG", "SBUST13U": "CUST",
}
SEED_DESIGNATED_INDEX = {
    t: (_SEED_INDEX_NAME[bench], bench)
    for bench, funds in _SEED_BENCHMARK_FUNDS.items()
    for t in funds.split()
}


# ── Sheet schema ───────────────────────────────────────────────────────────────
# Each sheet: key columns (identify the row, never edited) + value columns (operator
# fills/edits) + a trailing ``sourceNote``. ``required`` value columns that stay blank are
# GAPs that block LIVE.

@dataclass
class SheetSpec:
    name: str
    keys: list[str]
    values: list[str]
    required: list[str]          # subset of values whose blank = GAP


_SHEETS = [
    SheetSpec("designated_index", ["ticker"], ["indexName", "indexIdentifier"], []),
    SheetSpec("swap_counterparties", ["code"], ["legalName", "lei"], ["legalName", "lei"]),
    SheetSpec("option_index", ["underlying"], ["indexName", "indexIdentifier"],
              ["indexName", "indexIdentifier"]),
    SheetSpec("swap_legs", ["fund", "swapTicker"],
              ["recFixedOrFloating", "recDesc", "pmntFloatingRtIndex",
               "pmntFloatingRtSpread", "pmntRateTenor", "pmntRateUnit"],
              ["recFixedOrFloating", "recDesc", "pmntFloatingRtIndex", "pmntRateTenor", "pmntRateUnit"]),
    SheetSpec("invCountry", ["fund", "ticker", "cusip", "name"], ["invCountry"], ["invCountry"]),
    # isin is optional enrichment — a missing ISIN is filed as other=CUSIP, so it is NOT a
    # blocking gap (required=[]).
    SheetSpec("isin", ["fund", "ticker", "cusip", "name"], ["isin"], []),
    SheetSpec("sus_review", ["fund", "field"], ["value", "reason", "confirmed"], []),
]
_SHEET_BY_NAME = {s.name: s for s in _SHEETS}


@dataclass
class Review:
    """Reviewed values read back from the workbook, keyed for direct lookup."""
    sheets: dict[str, list[dict[str, str]]] = field(default_factory=dict)

    def _rows(self, sheet: str) -> list[dict[str, str]]:
        return self.sheets.get(sheet, [])

    def designated_index(self) -> dict[str, tuple[str, str]]:
        return {r["ticker"]: (r["indexName"], r["indexIdentifier"])
                for r in self._rows("designated_index")
                if r.get("ticker") and r.get("indexName") and r.get("indexIdentifier")}

    def swap_counterparties(self) -> dict[str, tuple[str, str]]:
        return {r["code"].upper(): (r["legalName"], r["lei"])
                for r in self._rows("swap_counterparties")
                if r.get("code") and r.get("legalName")}

    def option_index(self) -> dict[str, tuple[str, str]]:
        return {r["underlying"]: (r["indexName"], r["indexIdentifier"])
                for r in self._rows("option_index")
                if r.get("underlying") and r.get("indexName")}

    def swap_legs(self) -> dict[tuple[str, str], dict[str, str]]:
        return {(r["fund"], r["swapTicker"]): r
                for r in self._rows("swap_legs") if r.get("swapTicker")}

    def inv_country(self) -> dict[tuple[str, str], str]:
        return {(r["fund"], r["cusip"] or r["ticker"]): r["invCountry"]
                for r in self._rows("invCountry") if r.get("invCountry")}

    def isin(self) -> dict[tuple[str, str], str]:
        return {(r["fund"], r["cusip"] or r["ticker"]): r["isin"]
                for r in self._rows("isin") if r.get("isin")}


# ── I/O ────────────────────────────────────────────────────────────────────────


def _row_key(spec: SheetSpec, row: dict[str, str]) -> tuple:
    return tuple((row.get(k) or "").strip() for k in spec.keys)


def read_review(path: Path) -> Review:
    """Read the workbook into a ``Review``; an absent file yields an empty review."""
    path = Path(path)
    if not path.is_file():
        return Review()
    wb = load_workbook(path, data_only=True)
    sheets: dict[str, list[dict[str, str]]] = {}
    for spec in _SHEETS:
        if spec.name not in wb.sheetnames:
            continue
        ws = wb[spec.name]
        raw = list(ws.iter_rows(values_only=True))
        if not raw:
            continue
        header = [str(h).strip() if h is not None else "" for h in raw[0]]
        rows = []
        for r in raw[1:]:
            if r is None or all(c is None for c in r):
                continue
            rec = {header[i]: ("" if r[i] is None else str(r[i]))
                   for i in range(min(len(header), len(r)))}
            rows.append(rec)
        sheets[spec.name] = rows
    return Review(sheets=sheets)


def build_review_workbook(path: Path, generated: dict[str, list[dict[str, str]]]) -> dict[str, int]:
    """Write/refresh the review workbook, preserving operator edits.

    ``generated`` maps a sheet name → the rows the current run wants present (keys + any
    known pre-fill values + sourceNote). Reference sheets not in ``generated`` are seeded
    from the legacy literals. For every sheet, an existing row (matched by its key columns)
    keeps the operator's filled value cells; new rows are added; rows no longer generated
    are dropped (except reference sheets, which persist). Returns ``{sheet: gap_count}``.
    """
    path = Path(path)
    existing = read_review(path).sheets if path.is_file() else {}
    generated = generated or {}

    wb = Workbook()
    wb.remove(wb.active)
    gaps: dict[str, int] = {}

    for spec in _SHEETS:
        cols = spec.keys + spec.values + ["sourceNote"]
        prior = {_row_key(spec, r): r for r in existing.get(spec.name, [])}
        wanted = generated.get(spec.name)
        if wanted is None:
            wanted = _seed_rows(spec.name)            # reference sheet → seed/persist
            if not wanted and prior:                  # nothing seeded but operator has rows
                wanted = list(prior.values())
        out_rows: list[dict[str, str]] = []
        gap_count = 0
        for row in wanted:
            key = _row_key(spec, row)
            merged = dict(row)
            if key in prior:                          # keep operator's filled values
                for v in spec.values:
                    if (prior[key].get(v) or "").strip():
                        merged[v] = prior[key][v]
            out_rows.append(merged)
            if any(not (merged.get(v) or "").strip() for v in spec.required):
                gap_count += 1
        gaps[spec.name] = gap_count

        ws = wb.create_sheet(spec.name)
        ws.append(cols)
        for row in out_rows:
            ws.append([row.get(c, "") for c in cols])
        for r in range(2, ws.max_row + 1):            # keep identifiers as text
            for c in range(1, len(cols) + 1):
                ws.cell(row=r, column=c).number_format = "@"

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".xlsx")
    os.close(fd)
    try:
        wb.save(tmp)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return gaps


def generate_from_master_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Build the per-item review rows from the Bloomberg-populated master rows.

    Called at split (AFTER the operator has populated the workbook on the Bloomberg machine),
    so it surfaces only the residual gaps that custodian + Bloomberg + EagleSTAR could not
    fill. Reference sheets (designated_index, swap_counterparties, option_index) are seeded
    separately by ``build_review_workbook``.

    * ``swap_legs`` — one row per swap, pre-filled with the TRS template + a recDesc derived
      from the reference issuer (so it's reviewable, not a hidden hardcode).
    * ``invCountry`` — every holding still missing a country (a real gap that blocks LIVE).
    * ``isin``       — securities still missing an ISIN (optional enrichment; not a hard gap).
    """
    swap_legs, inv_country, isin_rows = [], [], []
    for r in rows:
        acct = (r.get("Account") or "").strip()
        dc = (r.get("derivCat") or "").strip()
        asset = (r.get("assetCat") or "").strip()
        if dc == "SWP":
            issuer = (r.get("refIssuerName") or r.get("title") or "").strip()
            leg = {"fund": acct, "swapTicker": (r.get("ticker") or "").strip(),
                   "recDesc": f"Total return of {issuer}" if issuer else "",
                   "sourceNote": "seed: TRS template — confirm against swap confirm"}
            leg.update(SEED_SWAP_LEG_TEMPLATE)
            swap_legs.append(leg)
        if asset and dc not in ("SWP", "OPT") and not (r.get("invCountry") or "").strip():
            inv_country.append({
                "fund": acct, "ticker": (r.get("ticker") or "").strip(),
                "cusip": (r.get("cusip") or "").strip(), "name": (r.get("name") or "").strip(),
                "invCountry": "", "sourceNote": "no country from Bloomberg — enter ISO-2"})
        if asset in ("EC", "DBT") and not (r.get("isin") or "").strip():
            isin_rows.append({
                "fund": acct, "ticker": (r.get("ticker") or "").strip(),
                "cusip": (r.get("cusip") or "").strip(), "name": (r.get("name") or "").strip(),
                "isin": "", "sourceNote": "no ISIN from Bloomberg (optional; CUSIP is filed)"})
    return {"swap_legs": swap_legs, "invCountry": inv_country, "isin": isin_rows}


def _seed_rows(sheet: str) -> list[dict[str, str]]:
    """Seed rows for a reference sheet from the legacy literals (empty for per-item sheets)."""
    if sheet == "designated_index":
        return [{"ticker": t, "indexName": n, "indexIdentifier": i, "sourceNote": "seed: 497K"}
                for t, (n, i) in sorted(SEED_DESIGNATED_INDEX.items())]
    if sheet == "swap_counterparties":
        return [{"code": c, "legalName": n, "lei": lei, "sourceNote": "seed: GLEIF"}
                for c, (n, lei) in sorted(SEED_SWAP_COUNTERPARTIES.items())]
    if sheet == "option_index":
        return [{"underlying": u, "indexName": n, "indexIdentifier": i, "sourceNote": "seed: legacy map"}
                for u, (n, i) in sorted(SEED_OPTION_INDEX.items())]
    return []
