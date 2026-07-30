"""Refresh each per-fund filing_data.txt balance sheet from the EagleSTAR trial balance.

Why this exists: the normal monthly path is `nport masters` -> open the workbooks on a
Bloomberg terminal (so =BDP returns/LEIs calculate) -> `nport split`. The committed
2026-06 snapshot already has those terminal-calculated values baked into the per-fund
files, which openpyxl cannot reproduce off-terminal (saving an .xlsx drops cached formula
results). So to regenerate the snapshot for the swap-valuation fix WITHOUT regressing the
Bloomberg enrichment, this script rewrites ONLY the three balance-sheet lines
(totAssets / totLiabs / netAssets) in each filing_data.txt, sourced straight from the
EagleSTAR trial balance (the same source `nport masters` now uses via filing_master).

The custodian-derived balance sheet grossed a swap up to its notional and booked the
financing as a liability, inflating totAssets/totLiabs to ~2x reality on leveraged swap
funds. The trial balance carries only the swap's mark-to-market, so its TOTAL ASSETS /
NET ASSETS are the real GAAP numbers.

Everything else in filing_data.txt (returns, flows, dates, amtPay*) is left untouched.
Funds not covered by the trial balance (the template funds) are skipped.

Run:  uv run python scripts/regenerate_balance_sheet.py [period]   (default: latest custodian)
"""
import re
import sys
from pathlib import Path

from nport import eaglestar
from nport.cli import _resolve_fund_accounting, _resolve_period

_FUNDS = Path("data/funds")
_FUND_ACCT_DIR = Path("data/fund_accounting")
_BS_KEYS = ("totAssets", "totLiabs", "netAssets")


def _set_key(text: str, key: str, value: str) -> tuple[str, bool]:
    """Replace the value of ``key=...`` in a filing_data.txt; return (text, changed)."""
    pat = re.compile(rf"(?m)^({re.escape(key)})=(.*)$")
    m = pat.search(text)
    if not m or m.group(2).strip() == value:
        return text, False
    return pat.sub(lambda _m: f"{key}={value}", text, count=1), True


def main() -> None:
    period = _resolve_period(sys.argv[1] if len(sys.argv) > 1 else None)
    export = _resolve_fund_accounting(None)
    if not export:
        print(f"ERROR: no EagleSTAR export in {_FUND_ACCT_DIR}/", file=sys.stderr)
        sys.exit(1)
    print(f"Loading EagleSTAR {export.name} for {period} ...")
    eag = eaglestar.load(export, period)
    tb_as_of = (eag.as_of.get("realized_unreal_monthends") or [""])[-1]

    updated, skipped_no_tb, skipped_no_file, unchanged = [], [], [], []
    for d in sorted(_FUNDS.iterdir()):
        if not d.is_dir() or not (d / "fund_config.txt").is_file():
            continue
        ticker = d.name.upper()
        fd = d / "filings" / period / "filing_data.txt"
        if not fd.is_file():
            continue
        bs = eag.filing.get(ticker, {})
        if not all(k in bs for k in _BS_KEYS):
            skipped_no_tb.append(ticker)
            continue
        text = fd.read_text(encoding="utf-8")
        changed = False
        for k in _BS_KEYS:
            text, c = _set_key(text, k, bs[k])
            changed = changed or c
        if changed:
            fd.write_text(text, encoding="utf-8")
            updated.append((ticker, bs["totAssets"], bs["totLiabs"], bs["netAssets"]))
        else:
            unchanged.append(ticker)

    print(f"\nBalance sheet from EagleSTAR TB @ {tb_as_of}:")
    print(f"  updated:        {len(updated)}")
    print(f"  already current:{len(unchanged)}")
    print(f"  no TB coverage: {len(skipped_no_tb)} {skipped_no_tb if skipped_no_tb else ''}")
    for t, ta, tl, na in updated[:8]:
        print(f"    {t}: totAssets={ta} totLiabs={tl} netAssets={na}")
    if len(updated) > 8:
        print(f"    ... +{len(updated) - 8} more")
    print("\nNext: `nport build` to regenerate the output XMLs (swap valUSD comes from the build).")


if __name__ == "__main__":
    main()
