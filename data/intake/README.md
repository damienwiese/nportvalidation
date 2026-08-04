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

There are only two command-line intake roles:

- the independent position export passed with `--positions` (required); and
- the independent create/redeem order export passed with `--orders` (optional).

Those files may keep their real source-system names. All other remediation is
centralized in the generated `filing_inputs.xlsx`. Do not create gap-specific
workbooks or empty evidence templates. Register each real supporting file or
system once on `Sources`, then enter its supported value or disposition in the
named `FundFields`, `HoldingFields`, or `ReconciliationInputs` row.

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
