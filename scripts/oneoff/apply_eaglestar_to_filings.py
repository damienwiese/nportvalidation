"""Apply every EagleSTAR-owned field to each per-fund filing_data.txt (off-terminal regen).

Single-writer rule: EagleSTAR is authoritative for ALL dollar values — balance sheet
(totAssets/totLiabs/netAssets), monthly realized/unrealized gains, monthly capital flows
(TB subscriptions/redemptions — NOT the AP order book, which is now only a cross-check), and
real payables (amtPayOneYrOther). `eaglestar.load` folds all of these into ``eag.filing``.

This rewrites only those keys in each committed filing_data.txt (preserving returns, dates,
constants). It exists because the workbook path (`masters` -> Bloomberg -> split) can't run
off a Bloomberg terminal without dropping the cached =BDP results; on-terminal, `nport split`
produces the same values.

Run:  uv run python scripts/oneoff/apply_eaglestar_to_filings.py [period]
"""
import re
import sys
from pathlib import Path

from nport import eaglestar
from nport.cli import _resolve_fund_accounting, _resolve_period

_FUNDS = Path("data/funds")


def _set_key(text: str, key: str, value: str) -> tuple[str, bool]:
    pat = re.compile(rf"(?m)^({re.escape(key)})=(.*)$")
    m = pat.search(text)
    if not m or m.group(2).strip() == value:
        return text, False
    return pat.sub(lambda _m: f"{key}={value}", text, count=1), True


def main() -> None:
    period = _resolve_period(sys.argv[1] if len(sys.argv) > 1 else None)
    export = _resolve_fund_accounting(None)
    if not export:
        print("ERROR: no EagleSTAR export in data/fund_accounting/", file=sys.stderr)
        sys.exit(1)
    print(f"Loading EagleSTAR {export.name} for {period} ...")
    eag = eaglestar.load(export, period)

    updated, no_tb = 0, []
    for d in sorted(_FUNDS.iterdir()):
        if not d.is_dir() or not (d / "fund_config.txt").is_file():
            continue
        fd = d / "filings" / period / "filing_data.txt"
        if not fd.is_file():
            continue
        fields = eag.filing.get(d.name.upper())
        if not fields:
            no_tb.append(d.name.upper())
            continue
        text = fd.read_text(encoding="utf-8")
        changed = False
        for k, v in fields.items():
            if v in (None, "", "N/A"):
                continue
            text, c = _set_key(text, k, v)
            changed = changed or c
        if changed:
            fd.write_text(text, encoding="utf-8")
            updated += 1

    print(f"Applied EagleSTAR fields to {updated} filing_data.txt files "
          f"(balance sheet, gains, TB flows, payables).")
    if no_tb:
        print(f"  No EagleSTAR coverage ({len(no_tb)}): {no_tb}")
    print("Next: `nport build` to regenerate output XMLs.")


if __name__ == "__main__":
    main()
