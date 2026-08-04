# Independent intake only

Use this directory for locally exported inputs that were produced independently
of U.S. Bank and its N-PORT process. A typical period can contain positions,
create/redeem orders, internal accounting close support, policy evidence, risk
results, liquidity results, trade records, and reconciliation reports.

Do not place U.S. Bank custody exports, EagleSTAR files, prepared N-PORT filings,
forwarded U.S. Bank email attachments, or files derived from them here. Moving or
renaming a prohibited file does not make it an independent input.

Recommended layout:

`data/intake/<period>/<fund>/<source-file>`

Recommended file templates (use the actual source filename if different):

- `positions.csv`
- `accounting_close.csv` or `accounting_close.pdf`
- `create_redeem_orders.csv` and, when applicable, `reinvestment_support.csv`
- `fund_policy_record.pdf` and `fund_static_data.csv`
- `swap_trade_export.csv` and `executed_swap_confirmations.pdf`
- `cash_ledger.csv`, `risk_metrics.csv`, `rule_18f4_results.csv`,
  `var_backtesting.csv`, and `monthly_return_categories.csv`
- `liquidity_classifications.csv` and, when applicable,
  `liquidity_circumstances.csv`
- `option_trade_terms.csv` and `option_delta.csv`
- independent GL, flow, and derivatives control reports used to support the
  values entered on `ReconciliationInputs`

These are naming conventions, not claims that the files exist. Do not create an
empty placeholder to clear an input; each file must contain genuine independent
evidence from the named internal owner.

Run `nport prepare <fund> <period> --positions <file> [--orders <file>]` once to
create `filing_inputs.xlsx`. Add each additional real source directly to that
workbook's `Sources` sheet. Complete `sourceId`, `dataset`, `sourceType`,
`sourceSystem`, `sourcePath`, `sourceAsOf`, and `comment`; leave `sha256` and
`recordCount` blank when the program can calculate them from the file.

For G-012, enter the independent control total and approved tolerance in the
generated `ReconciliationInputs` row, together with its `sourceId`, status, and
comment. The control source must differ from the source used for the filed-side
value. The program calculates the filed-side actual, difference, and PASS/FAIL
result during `nport build <fund> <period> --from-inputs`.

No preparer, reviewer, signature, or approval columns are required by this
workflow.
