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
- `fund_policy_approval.pdf` and `fund_static_data.csv`
- `swap_trade_export.csv` and `executed_swap_confirmations.pdf`
- `cash_ledger.csv`, `risk_metrics.csv`, `rule_18f4_results.csv`,
  `var_backtesting.csv`, and `monthly_return_categories.csv`
- `liquidity_classifications.csv` and, when applicable,
  `liquidity_circumstances.csv`
- `option_trade_terms.csv` and `option_delta.csv`
- `positions_to_gl_reconciliation.csv`, `flow_reconciliation.csv`, and
  `derivatives_reconciliation.csv`
- `source_origin_attestation.pdf`

These are naming conventions, not claims that the files exist. Do not create an
empty placeholder to clear a blocker; each file must contain genuine independent
evidence from the named internal owner.

After adding a source path to the fund-period workbook's `Sources` sheet, rerun
`nport prepare-review <fund> <period> ...` to calculate a blank SHA-256 and CSV
record count. The operator must still complete the source cutoff, acquisition
time, preparer, reviewer, review time, and approval.
