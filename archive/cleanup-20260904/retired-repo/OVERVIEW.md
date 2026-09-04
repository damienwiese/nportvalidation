# N-PORT In-House Service Overview

## Controlling rule

No file, value, mapping, seed, or pre-fill delivered by U.S. Bank may populate
the in-house filing. U.S. Bank output is used only after generation for a
read-only, apples-to-apples comparison aligned by fund, report date, fiscal
year-end, and submission type.

## Independent inputs required

1. Internal OMS/IBOR period-end positions.
2. Internal GL, NAV close, and accounting subledgers.
3. Internal create/redeem orders reconciled to the transfer agent and GL.
4. Approved internal security/reference data.
5. Internal liquidity classifications.
6. Internal trade capture, executed confirmations, and derivatives-risk results.
7. Effective-dated fund policy and fiscal calendar approved by Compliance.

Each source is recorded in the fund-period workbook's `Sources` sheet with its
system of record, file path, report-date cutoff, acquisition timestamp, SHA-256,
record count, preparer, reviewer, and approval. Finalization creates the source
manifest automatically.

## Canonical contract

- `data/funds/<ticker>/fund_config.txt` - static fund and signer identity.
- `data/funds/<ticker>/filings/<period>/filing_data.txt` - filing-level data.
- `data/funds/<ticker>/filings/<period>/holdings.csv` - Part C holdings and
  conditional debt/derivative/liquidity fields.

The final clean versions are written under `data/builds/<ticker>/<period>/<run-id>/`.
They are not a place to copy U.S. Bank values.

## Human review

The safe workbook is
`data/funds/<ticker>/filings/<period>/human_review.xlsx`. It has `FundFields`,
`HoldingFields`, `Sources`, `Approvals`, and `Reconciliation` sheets. A human may
enter a supported value or a supported `NOT_APPLICABLE` disposition. The system
requires source ID, cutoff, reviewer, review time, and a reason where applicable.
Two different people must approve the package. The base position population is
still file-supplied; it is never recreated manually in Excel.

## Missing versus blocking

- **Missing**: a value or required item is absent.
- **Blocking**: release must stop because an applicable item is missing, stale,
  invalid, unapproved, prohibited, or unreconciled.
- **Review**: a human decision is required. Review does not cure missing source
  evidence.

## Current command boundary

Safe: `prepare-review`, `review-status`, `finalize-review`, `build --from-review`,
provenance-gated explicit `generate`, validation/schema checks, and read-only
`compare-reference`.

Disabled: `masters`, `split`, `mergehumanreview`, `enrich`, `merge`, `new-filing`,
`build-master`, `split-master`, `build-filing-master`, and
`split-filing-master`.

The field-level source, exact destination, human action, and release effect are in
`docs/NPORT_Runbook.pdf`. The complete blocker register is in
`docs/US_Bank_NPORT_Comprehensive_Final_Audit_2026-08-03.pdf`.
