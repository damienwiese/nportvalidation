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
workbooks or empty evidence templates. Enter the value/disposition in the named
`FundFields` or `HoldingFields` row and control totals in `ReconciliationInputs`.

Run `nport prepare <fund> <period> --positions <file> [--orders <file>]` once to
create `filing_inputs.xlsx`. The `Sources` sheet is optional diagnostic metadata.
No reviewer entry there is required for XML generation.

For G-012, enter the independent control total and approved tolerance in the
generated `ReconciliationInputs` row, together with status and comment.
`sourceId` is optional. The program calculates the filed-side actual, difference,
and PASS/FAIL result during `nport build <fund> <period> --from-inputs`.

No preparer, reviewer, signature, or approval columns are required by this
workflow.
