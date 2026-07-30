"""US Bank EagleSTAR fund-accounting export -> per-fund N-PORT pre-fill.

Mirrors ``ap_orders.py``: drop the Google Takeout ``.zip`` (or a raw ``.mbox``)
into ``data/fund_accounting/`` and ``masters`` extracts the daily PVal /
Trial Balance / NAV attachments and pre-fills the N-PORT fields the custodian +
Bloomberg cannot supply:

* derivative ``unrealizedAppr`` (PVal ``Total Unreal G/L Base``; swaps from the
  ``_R`` leg only),
* monthly realized / unrealized gains (Trial Balance month-end deltas),
* real balance-sheet liabilities (Trial Balance payable accounts).

The entity<->ticker bridge is the NAV ``NASDAQ`` column. 100% additive: an empty
or absent drop folder is a no-op, so funds with no EagleSTAR data are unchanged.

Extraction writes intermediate per-day CSVs to a git-ignored build cache
(``data/fund_accounting/.cache/<type>/<YYYYMMDD>.csv``) and is idempotent: a marker
of the source archive lets a re-run skip the decode. Stdlib only.
"""
import csv
import io
import mailbox
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from nport.numbers import fnum as _fnum

# ── Trial Balance cryptic columns (verified) ───────────────────
_TB_NAME = "F1086"        # GL account name
_TB_END = "F64008"        # ending balance (signed)
_TB_ENTITY = "F5"         # entity number

# ── Account-name crosswalk (exact strings verified against the real TB) ──
# Realized gain/loss accounts (cumulative), excluding accumulated-undistributed.
_REALIZED_RE = re.compile(r"REALIZED (GAIN|LOSS)", re.I)
# Net unrealized appreciation/depreciation (investments + swaps), excluding ACCUM.
_UNREAL_RE = re.compile(r"(NET UNREAL (APPR|DEPR)|SWAP UNREALIZED (APPRECIATION|DEPRECIATION))", re.I)
_ACCUM_RE = re.compile(r"\bACCUM", re.I)   # ACCUM / ACCUMULATED ... -> excluded everywhere
# Real liabilities that roll into amtPayOneYrOther.
_PAYABLE_RE = re.compile(
    r"(INVESTMENT PAYABLE|SWAP PAYABLE|ACCRUED .*FEE|ACCOUNTS PAYABLE REDEMPTIONS"
    r"|BROKER INTEREST PAYABLE|TAX PAYABLE|EXPENSE REIMBURSEMENT PAYABLE)", re.I)
_TOTAL_LIABS_RE = re.compile(r"TOTAL LIABILITIES", re.I)
# Balance-sheet totals, anchored so they match the single subtotal line (not e.g.
# "TOTAL ASSETS ATTRIBUTABLE TO ..."). NET ASSETS appears twice in the TB (asset/
# liability section and capital section, equal by construction) → take last, not sum.
_TOTAL_ASSETS_RE = re.compile(r"^TOTAL ASSETS$", re.I)
_NET_ASSETS_RE = re.compile(r"^NET ASSETS$", re.I)
_SUBSCRIPTIONS_RE = re.compile(r"^SUBSCRIPTIONS$", re.I)
_REDEMPTIONS_RE = re.compile(r"^REDEMPTIONS$", re.I)

# Sign applied to the signed TB ending-balance sum when reporting N-PORT gains.
# Validated against FDRS 2026-06; flip here if the sign convention proves inverted.
_GAIN_SIGN = 1

_FLOW_MONTHS = ("mon1", "mon2", "mon3")
_DATE_RE = re.compile(r"(\d{8})")
_TYPES = {"PVal": "pval", "Trial_Balance": "tb", "NAV_Sum": "nav"}


def _period_months(period: str) -> list[str]:
    """The 3 reporting-period months 'YYYY-MM', chronological (mon1 .. mon3)."""
    y, m = int(period[:4]), int(period[5:7])
    out = []
    for back in (2, 1, 0):
        yy, mm = y, m - back
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def _baseline_month(period: str) -> str:
    """The month before mon1 (m-3) — the baseline for the first monthly delta."""
    y, m = int(period[:4]), int(period[5:7])
    yy, mm = y, m - 3
    while mm <= 0:
        mm += 12
        yy -= 1
    return f"{yy:04d}-{mm:02d}"


# ── Discovery ──────────────────────────────────────────────────


def resolve_export(folder: Path) -> Path | None:
    """The newest ``*.zip`` or ``*.mbox`` in ``folder``; None if there isn't one.

    Ordered by NAME, not mtime: the exports are timestamped filenames
    (``takeout-YYYYMMDD...``), so name order is chronological AND deterministic across
    machines/checkouts (git doesn't preserve mtime), which mtime ordering is not.
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None
    cands = sorted(
        p for p in folder.glob("*") if p.suffix.lower() in (".zip", ".mbox")
    )
    return cands[-1] if cands else None


# ── Extraction to the build cache ──────────────────────────────


def _source_marker(export: Path) -> str:
    st = export.stat()
    return f"{export.name}:{st.st_size}:{int(st.st_mtime)}"


def extract_to_cache(export: Path, cache_dir: Path) -> Path:
    """Decode the export's PVal/TB/NAV attachments to ``cache_dir/<type>/<date>.csv``.

    Idempotent: if the cache's source marker already matches ``export``, the decode
    is skipped. Returns ``cache_dir``.
    """
    export, cache_dir = Path(export), Path(cache_dir)
    marker_path = cache_dir / ".source"
    marker = _source_marker(export)
    if marker_path.is_file() and marker_path.read_text(encoding="utf-8").strip() == marker:
        return cache_dir   # cache already current — skip

    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    for sub in _TYPES.values():
        (cache_dir / sub).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        if export.suffix.lower() == ".zip":
            with zipfile.ZipFile(export) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".mbox")]
                if not names:
                    raise ValueError(f"No .mbox inside {export.name}")
                z.extract(names[0], td)
                mbox_path = Path(td) / names[0]
        else:
            mbox_path = export
        _decode_mbox(mbox_path, cache_dir)

    marker_path.write_text(marker, encoding="utf-8")
    return cache_dir


def _decode_mbox(mbox_path: Path, cache_dir: Path) -> None:
    mb = mailbox.mbox(str(mbox_path))
    for msg in mb:
        for part in msg.walk():
            fn = part.get_filename() or ""
            sub = next((s for key, s in _TYPES.items() if key in fn), None)
            if not sub:
                continue
            m = _DATE_RE.search(fn)
            if not m:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            (cache_dir / sub / f"{m.group(1)}.csv").write_bytes(payload)


# ── Cache readers ──────────────────────────────────────────────


def _dates(cache_dir: Path, sub: str) -> list[str]:
    d = Path(cache_dir) / sub
    return sorted(p.stem for p in d.glob("*.csv")) if d.is_dir() else []


def _read(cache_dir: Path, sub: str, date: str) -> list[dict]:
    p = Path(cache_dir) / sub / f"{date}.csv"
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _latest_in_month(dates: list[str], ym: str) -> str | None:
    """The latest YYYYMMDD snapshot whose calendar month is ``ym`` ('YYYY-MM')."""
    pref = ym.replace("-", "")
    hits = [d for d in dates if d.startswith(pref)]
    return max(hits) if hits else None


def entity_ticker_map(cache_dir: Path) -> dict[str, str]:
    """``{entity_number: NASDAQ ticker}`` from the latest NAV snapshot."""
    dates = _dates(cache_dir, "nav")
    if not dates:
        return {}
    out = {}
    for r in _read(cache_dir, "nav", dates[-1]):
        ent = (r.get("Entity Number") or "").strip()
        tic = (r.get("NASDAQ") or "").strip().upper()
        if ent and tic:
            out[ent] = tic
    return out


# ── Derivatives (PVal) ─────────────────────────────────────────


def derivative_values(
    cache_dir: Path, period: str, ent_tic: dict[str, str],
) -> tuple[dict[tuple[str, str], dict[str, str]], str | None]:
    """``({(ticker, asset_id): {'unrealizedAppr': value}}, snapshot_date)`` from the period-end PVal.

    Options: ``Total Unreal G/L Base`` directly. Swaps: only the ``_R`` leg (the
    base/``_P`` legs are 0); the leg suffix is on ``Issue Name``, while
    ``Primary Asset ID`` already equals the custodian StockTicker.

    Always returns a 2-tuple; the no-PVal path returns ``({}, None)`` (the caller
    unpacks ``derivs, pval_date = derivative_values(...)``, so a bare ``{}`` here
    would crash the whole ``masters`` run with a ValueError).
    """
    dates = _dates(cache_dir, "pval")
    snap = _latest_in_month(dates, _period_months(period)[-1]) or (dates[-1] if dates else None)
    if not snap:
        return {}, None
    out: dict[tuple[str, str], dict[str, str]] = {}
    for r in _read(cache_dir, "pval", snap):
        typ = (r.get("Investment Type Desc") or "").strip()
        if typ not in ("Options", "SWAPS"):
            continue
        if typ == "SWAPS" and not (r.get("Issue Name") or "").strip().endswith("_R"):
            continue
        ticker = ent_tic.get((r.get("Entity/Sector Number") or "").strip())
        asset_id = (r.get("Primary Asset ID") or "").strip()
        if not ticker or not asset_id:
            continue
        out[(ticker, asset_id)] = {"unrealizedAppr": f"{_fnum(r.get('Total Unreal G/L Base')):.2f}"}
    return out, snap


# ── Filing-level (Trial Balance) ───────────────────────────────


def _tb_sum(rows: list[dict], pattern: re.Pattern) -> dict[str, float]:
    """Σ ending balance per entity over accounts matching ``pattern`` (excl. ACCUM)."""
    sums: dict[str, float] = {}
    for r in rows:
        name = (r.get(_TB_NAME) or "")
        if not pattern.search(name) or _ACCUM_RE.search(name):
            continue
        ent = (r.get(_TB_ENTITY) or "").strip()
        sums[ent] = sums.get(ent, 0.0) + _fnum(r.get(_TB_END))
    return sums


def _tb_snapshot_sums(cache_dir: Path, date: str, pattern: re.Pattern) -> dict[str, float]:
    return _tb_sum(_read(cache_dir, "tb", date), pattern) if date else {}


def filing_values(cache_dir: Path, period: str, ent_tic: dict[str, str]) -> tuple[dict, dict, dict]:
    """Per-ticker filing pre-fills + reconciliation sidecars.

    Returns ``(values, tb_total_liabs, as_of)`` where ``values`` is
    ``{ticker: {netRealizedGainMon1-3, netUnrealizedApprMon1-3, amtPayOneYrOther}}``,
    ``tb_total_liabs`` is ``{ticker: TB TOTAL LIABILITIES}`` for reconciliation, and
    ``as_of`` records the snapshot dates used.
    """
    tb_dates = _dates(cache_dir, "tb")
    months = [_baseline_month(period)] + _period_months(period)   # [m-3, m-2, m-1, m]
    snaps = [_latest_in_month(tb_dates, ym) for ym in months]

    realized = [_tb_snapshot_sums(cache_dir, s, _REALIZED_RE) for s in snaps]
    unreal = [_tb_snapshot_sums(cache_dir, s, _UNREAL_RE) for s in snaps]

    # Period-end snapshot drives liabilities, the balance-sheet totals, and the
    # TOTAL LIABILITIES tie-out.
    end_snap = snaps[-1]
    payables = _tb_snapshot_sums(cache_dir, end_snap, _PAYABLE_RE)
    end_rows = _read(cache_dir, "tb", end_snap) if end_snap else []
    # Authoritative GAAP balance sheet straight from the trial balance. These REPLACE
    # the custodian-derived gross-up in the filing master: for a swap fund the custodian
    # carries the swap at notional and plugs the financing into a negative "Cash&Other",
    # which inflates totAssets/totLiabs to ~2x reality. The TB carries only the swap's
    # mark-to-market, so its TOTAL ASSETS / NET ASSETS are the real numbers.
    total_assets: dict[str, float] = {}
    total_liabs: dict[str, float] = {}
    net_assets_bs: dict[str, float] = {}
    for r in end_rows:
        name = r.get(_TB_NAME) or ""
        ent = (r.get(_TB_ENTITY) or "").strip()
        val = _fnum(r.get(_TB_END))
        if _TOTAL_ASSETS_RE.match(name):
            total_assets[ent] = val            # last wins (single subtotal line)
        elif _TOTAL_LIABS_RE.search(name):
            total_liabs[ent] = val
        elif _NET_ASSETS_RE.match(name):
            net_assets_bs[ent] = val            # appears twice, equal → last wins

    values: dict[str, dict[str, str]] = {}
    liab_xcheck: dict[str, float] = {}
    for ent, ticker in ent_tic.items():
        rec: dict[str, str] = {}
        for i, mon in enumerate(_FLOW_MONTHS, start=1):   # delta vs prior month-end
            dr = realized[i].get(ent, 0.0) - realized[i - 1].get(ent, 0.0)
            du = unreal[i].get(ent, 0.0) - unreal[i - 1].get(ent, 0.0)
            rec[f"netRealizedGainMon{i}"] = f"{_GAIN_SIGN * dr:.2f}"
            rec[f"netUnrealizedApprMon{i}"] = f"{_GAIN_SIGN * du:.2f}"
        pay = payables.get(ent, 0.0)
        if pay > 0:
            rec["amtPayOneYrOther"] = f"{pay:.2f}"
        # Authoritative balance sheet (overrides the custodian gross-up in the filing master).
        if ent in total_assets:
            rec["totAssets"] = f"{total_assets[ent]:.2f}"
        if ent in total_liabs:
            rec["totLiabs"] = f"{total_liabs[ent]:.2f}"
        if ent in net_assets_bs:
            rec["netAssets"] = f"{net_assets_bs[ent]:.2f}"
        # Emit a fund that appears in the TB snapshots (gains, payables, or a balance sheet).
        if (any(ent in realized[i] or ent in unreal[i] for i in range(len(snaps)))
                or pay or ent in total_assets):
            values[ticker] = rec
            if ent in total_liabs:
                liab_xcheck[ticker] = total_liabs[ent]
    as_of = {"realized_unreal_monthends": snaps, "liabilities": end_snap}
    return values, liab_xcheck, as_of


# ── Flows (Trial Balance, for reconciliation only) ─────────────


def flow_values(cache_dir: Path, period: str, ent_tic: dict[str, str]) -> dict[str, dict[str, str]]:
    """Gross monthly creations/redemptions from cumulative TB SUBSCRIPTIONS/REDEMPTIONS
    month-end deltas. For reconciling the AP order book — NOT written to the filing."""
    tb_dates = _dates(cache_dir, "tb")
    months = [_baseline_month(period)] + _period_months(period)
    snaps = [_latest_in_month(tb_dates, ym) for ym in months]
    subs = [_tb_snapshot_sums(cache_dir, s, _SUBSCRIPTIONS_RE) for s in snaps]
    reds = [_tb_snapshot_sums(cache_dir, s, _REDEMPTIONS_RE) for s in snaps]
    out: dict[str, dict[str, str]] = {}
    for ent, ticker in ent_tic.items():
        rec = {}
        for i, mon in enumerate(_FLOW_MONTHS, start=1):
            rec[f"{mon}Sales"] = f"{subs[i].get(ent, 0.0) - subs[i - 1].get(ent, 0.0):.2f}"
            rec[f"{mon}Redemption"] = f"{abs(reds[i].get(ent, 0.0) - reds[i - 1].get(ent, 0.0)):.2f}"
        out[ticker] = rec
    return out


def nav_net_assets(cache_dir: Path, period: str, ent_tic: dict[str, str]) -> dict[str, float]:
    """``{ticker: NAV Total Net Assets}`` from the period-end NAV (reconcile netAssets)."""
    dates = _dates(cache_dir, "nav")
    snap = _latest_in_month(dates, _period_months(period)[-1]) or (dates[-1] if dates else None)
    if not snap:
        return {}
    out = {}
    for r in _read(cache_dir, "nav", snap):
        tic = (r.get("NASDAQ") or "").strip().upper()
        if tic:
            out[tic] = _fnum(r.get("Total Net Assets"))
    return out


# ── Bundle ─────────────────────────────────────────────────────


@dataclass
class EagleStarData:
    filing: dict[str, dict[str, str]] = field(default_factory=dict)        # ticker -> filing fields
    derivatives: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    flows: dict[str, dict[str, str]] = field(default_factory=dict)         # reconcile only
    tb_total_liabs: dict[str, float] = field(default_factory=dict)         # reconcile only
    nav_net_assets: dict[str, float] = field(default_factory=dict)         # reconcile only
    entity_ticker: dict[str, str] = field(default_factory=dict)
    as_of: dict = field(default_factory=dict)


def load(export: Path, period: str, cache_dir: Path | None = None) -> EagleStarData:
    """Extract once and build every map — the analogue of ``flows_from_csv``."""
    export = Path(export)
    cache_dir = Path(cache_dir) if cache_dir else export.parent / ".cache"
    extract_to_cache(export, cache_dir)
    ent_tic = entity_ticker_map(cache_dir)
    derivs, pval_date = derivative_values(cache_dir, period, ent_tic)
    filing, liabs, as_of = filing_values(cache_dir, period, ent_tic)
    as_of["pval"] = pval_date
    flows = flow_values(cache_dir, period, ent_tic)
    # TB subscriptions/redemptions are the authoritative flow WRITER — they tie to the
    # same trial balance that produces netAssets/gains. Fold them into the per-fund filing
    # fields for every TB-covered fund so the filing master writes them; the AP order book
    # remains an x-check only (kept on .flows for the reconciliation report).
    for tic in filing:
        if tic in flows:
            filing[tic].update(flows[tic])
    return EagleStarData(
        filing=filing,
        derivatives=derivs,
        flows=flows,
        tb_total_liabs=liabs,
        nav_net_assets=nav_net_assets(cache_dir, period, ent_tic),
        entity_ticker=ent_tic,
        as_of=as_of,
    )
