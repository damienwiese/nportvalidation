# nport

Build SEC Form N-PORT XML from independently sourced, traceable canonical data.

## Source boundary

U.S. Bank custody exports, EagleSTAR attachments, prepared filings, email
attachments, master workbooks, and every file derived from them are
comparison-only. They cannot populate the in-house filing.

The current repository contains historical comparison artifacts. Preserve them;
do not promote or manually relabel them as internal data.

## Current safe commands

```powershell
nport prepare-review <fund> <period> --positions <independent_positions.csv> [--orders <independent_orders.csv>]
nport review-status <fund> <period>
nport finalize-review <fund> <period>
nport build <fund> <period> --from-review
nport compare-reference --internal <internal.xml> --reference <external-reference.xml>
```

`<fund>` is any fund directory under `data/funds/`; FDRS is only an example.
Review commands deliberately process one fund at a time because source evidence
and approvals are fund-specific. For a full period, place each fund's independent
files under `data/intake/<period>/<fund>/` and use the all-fund PowerShell loops in
`docs/NPORT_Runbook.pdf`. Those loops prepare every workbook, stop and list blocked
funds, and build every review-ready fund without using legacy canonical files.

The complete monthly order is:

1. `nport schema` - confirm the positions CSV contract.
2. `nport prepare-review` - generate one workbook per fund.
3. Human review - complete Sources, FundFields, HoldingFields, and Approvals.
4. `nport review-status` - stop until every fund reports zero blockers.
5. `nport build --from-review --dry-run` - validate without retaining output.
6. `nport build --from-review` - write the clean bundle and XML.
7. `nport compare-reference` - compare only after the independent build.

The review workbook is written to
`data/funds/<fund>/filings/<period>/human_review.xlsx`. It contains exact
fund-field, holding-field, source-evidence, approval, and reconciliation
locations. `finalize-review` writes a clean versioned bundle under
`data/builds/<fund>/<period>/<run-id>/`; it does not overwrite the historical
canonical files.

No separate `fund_registry.csv` is required by this workflow. Effective-dated
policy is reviewed at fund level and written into the clean `fund_config.txt`.
Known U.S. Bank/EagleSTAR identifiers and legacy landing paths are rejected.

## Status

The local review, evidence, approval, provenance, clean finalization, basic
reconciliation, preflight, and build path are implemented. The code does not
invent business values. A filing remains **BLOCKED** until its independent
positions, accounting, policy, risk, liquidity, trade, and control evidence are
actually supplied and approved.

See `docs/NPORT_Runbook.pdf` for every accepted field and exact input location,
and `docs/US_Bank_NPORT_Comprehensive_Final_Audit_2026-08-03.pdf` for the open
gap register and remediation owners.
