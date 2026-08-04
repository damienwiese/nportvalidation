# nport

Build SEC Form N-PORT XML from independently sourced, traceable data.

## Non-negotiable source boundary

U.S. Bank custody exports, EagleSTAR attachments, prepared filings, email
attachments, master workbooks, and files derived from them are comparison-only.
They cannot populate the in-house filing.

Bloomberg is permitted only through the Bloomberg formulas generated in the
fund-period input workbook. The legacy master-workbook path remains disabled.

## One-time setup

```powershell
Set-Location "C:\Users\damie\nportvalidation"
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
```

## Complete filing workflow

Replace `<fund>` and `<period>` with the real ticker and filing month. The
examples use `fdrs` and `2026-06` only to show the command format.

### 1. Place independent inputs

```text
data/intake/<period>/<fund>/positions.csv
data/intake/<period>/<fund>/create_redeem_orders.csv   # optional
```

### 2. Run the preparation automation

```powershell
& ".\.venv\Scripts\nport.exe" prepare fdrs 2026-06 `
  --positions ".\data\intake\2026-06\fdrs\positions.csv" `
  --orders ".\data\intake\2026-06\fdrs\create_redeem_orders.csv"
```

Omit `--orders` when there is no independent order export. The command creates:

```text
data/funds/fdrs/filings/2026-06/filing_inputs.xlsx
```

### 3. Open, populate, and complete the workbook

1. Open `filing_inputs.xlsx` on a Bloomberg terminal.
2. Wait for the `Bloomberg` sheet formulas to resolve, then save the workbook.
3. Ignore `Sources` for XML completion. Its labels, paths, dates, hashes, counts,
   and `sourceId` values are optional diagnostics and never serialize into XML.
4. On `FundFields` and `HoldingFields`, filter `status` to `MISSING`.
5. For a known value, enter or confirm the value and set `status` to `PROVIDED`.
6. For a genuinely inapplicable conditional field, set `NOT_APPLICABLE` and
   enter the factual reason in `comment`.
7. On `ReconciliationInputs`, complete every generated row with `controlValue`,
   policy-approved `tolerance`, `status`, and comment. The program calculates the
   filed-side actual and difference. `sourceId` is optional.

For `fund_config.txt` rows, always enter `proposedValue` when the field applies.
Any displayed `currentValue` is reference-only and cannot be released by changing
the status alone. SEC Part F signer fields and `dateSigned` remain because they
are XML filing values.

### 4. Run the final automation

```powershell
& ".\.venv\Scripts\nport.exe" build fdrs 2026-06 --from-inputs
```

This one command checks XML values, policy/applicability, and reconciliation;
rejects explicit prohibited comparison-input references; creates a clean
versioned bundle; builds the XML; and validates it against the SEC schema. If the filing is not ready, it classifies each item
as an open input, input correction, prohibited input, or validation error and
prints the exact workbook row or upstream file to fix. Correct it and run the
same build command again.

Successful outputs:

```text
data/builds/<fund>/<period>/<run-id>/
output/<FUND>_<PERIOD>.xml
```

### 5. Optional read-only comparison

Run this only after the independent XML exists and only when the reference uses
the same fund and report date:

```powershell
& ".\.venv\Scripts\nport.exe" compare-reference `
  --internal ".\output\FDRS_2026-06.xml" `
  --reference "<aligned-reference.xml>"
```

Never copy a comparison value back into `filing_inputs.xlsx`.

## Compatibility

During version `0.1.x`, `human_review.xlsx`, `prepare-review`, `review-status`,
`finalize-review`, and `--from-review` remain readable compatibility aliases and
print deprecation warnings. New work must use `filing_inputs.xlsx`, `prepare`,
and `build --from-inputs`.

See `docs/NPORT_Runbook.pdf` for field-level locations and
`docs/US_Bank_NPORT_Comprehensive_Final_Audit_2026-08-03.pdf` for the remaining
data gaps and exact fix locations.
