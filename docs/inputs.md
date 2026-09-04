# Input workbook

The user-facing July 2026 workbook lives under:

`data/inputs/nport-v<schema>/`

Create it with:

```powershell
nport input-template 2026-07
```

The workbook covers the 197 tickers in `data/funds/fund_universe.csv`. Its 592
worksheets consist of exactly three adjacent input sheets per fund followed by
one consolidated create/redeem sheet at the end:

| Sheet pattern | Columns | Purpose |
|---|---|---|
| `<FUND>_Config` | `fieldName`, `value` | Static fund identity, signing, and policy inputs |
| `<FUND>_FundData` | `Period`, `fieldName`, `value` | July N-PORT fund values and `rtn1`-`rtn3` Bloomberg formulas |
| `<FUND>_Positions` | `Period`, `holdingId`, then canonical holding fields | July position-level inputs and controlled Bloomberg formulas |
| `Orders` | `Fund`, `Period`, `Ticker`, `Side`, `Trade Date`, `Notional`, `Status` | Consolidated create/redeem activity for every fund |

For example, the opening tabs are `ACLZ_Config`, `ACLZ_FundData`,
`ACLZ_Positions`, `ACMM_Config`, `ACMM_FundData`, and `ACMM_Positions`.
This pattern repeats through `YUNG_Positions`, then ends with `Orders`.

There are no index, reconciliation, source, documentation, helper, or hidden
sheets. Format, schema, period, and fund-universe metadata are stored in
workbook properties. Config and FundData sheets contain only keys and input
values; review status, attribution, system-derived fields, and reconciliation
controls are generated later in `filing_inputs.xlsx`.

The 16 active reviewed configurations are prefilled. The other 181 fund tabs
are included with blank Config values. Previously generated synthetic
configurations remain archived and are not treated as filing authority. A blank
configuration cannot enter the filing run path until authoritative values are
supplied and activated.

Enter position lookup identifiers, open the workbook in Bloomberg-enabled
Excel, wait for the pale-blue cells to resolve, and save. A pending or error
result remains missing. Copy the fund's July starter position row before adding
more positions so the controlled formulas copy with it.

Import one filing-ready fund with:

```powershell
nport prepare FDRS 2026-07 --input-workbook data\inputs\nport-v1.13\nport-inputs-v4_2026-07_nport-v1.13.xlsx
```

Import writes content-addressed normalized CSVs beneath `_normalized/` beside
the workbook and then invokes the ordinary preparation path. Part F / NPORT-EX
is not supported and has no input sheet or column.
