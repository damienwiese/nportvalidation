"""Refresh swap valUSD/pctVal in each per-fund security_master.csv to the mark-to-market.

Companion to regenerate_balance_sheet.py — same off-terminal snapshot-regeneration rationale
(see that file). A swap's reportable value IS its mark-to-market (the unrealizedAppr already
in the row), NOT the custodian MarketValue, which is the notional and belongs only in
notionalAmt. The build derives this at ingest time regardless, and the next `nport masters`
run rebuilds it via master_sheet; this just makes the committed CSVs internally consistent
with the output XMLs so a reviewer comparing them doesn't see the old notional in valUSD.

valUSD := unrealizedAppr ; pctVal := unrealizedAppr / netAssets * 100  (netAssets from the
period custodian). Only SWP rows are touched; nothing else in the CSV changes.

Run:  uv run python scripts/regenerate_swap_valuations.py [period]
"""
import csv
import sys
from pathlib import Path

from nport.cli import _resolve_custodian, _resolve_period
from nport.custodian import _parse_float, parse_custodian_csv

_FUNDS = Path("data/funds")


def main() -> None:
    period = _resolve_period(sys.argv[1] if len(sys.argv) > 1 else None)
    rows = parse_custodian_csv(_resolve_custodian(None, period))
    net_by_acct: dict[str, float] = {}
    for r in rows:
        net_by_acct.setdefault(r.account.upper(), _parse_float(r.net_assets))

    updated = 0
    for sm in sorted(_FUNDS.glob("*/security_master.csv")):
        acct = sm.parent.name.upper()
        na = net_by_acct.get(acct, 0.0)
        with open(sm, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            recs = list(reader)
        if "valUSD" not in fieldnames:
            continue
        changed = False
        for rec in recs:
            if (rec.get("derivCat") or "").strip() != "SWP":
                continue
            ua = (rec.get("unrealizedAppr") or "").strip()
            new_val = ua
            new_pct = f"{_parse_float(ua) / na * 100:.2f}" if ua and na else ""
            if rec.get("valUSD") != new_val or rec.get("pctVal") != new_pct:
                rec["valUSD"], rec["pctVal"] = new_val, new_pct
                changed = True
        if changed:
            with open(sm, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(recs)
            updated += 1
    print(f"Updated swap valUSD/pctVal in {updated} per-fund security_master.csv files.")


if __name__ == "__main__":
    main()
