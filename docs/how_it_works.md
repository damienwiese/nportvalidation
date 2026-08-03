# How the In-House N-PORT Service Works

An operator starts with an independent period-end positions export and optional
create/redeem export, then runs `prepare-review`. The command creates one workbook
at `data/funds/<fund>/filings/<period>/human_review.xlsx`. Fund policy, filing
values, holding exceptions, source evidence, and approvals all have explicit
rows in that workbook. There is no separate fund registry in this path.

Every accepted value or not-applicable disposition must record source, cutoff,
reviewer, time, and evidence. Two different people approve the package.
`review-status` lists each remaining blocker. `finalize-review` writes a clean,
versioned canonical bundle, provenance file, reconciliation file, source manifest,
and review receipt. `build --from-review` also validates inputs, runs preflight,
generates XML, runs the SEC XSD, and writes a release manifest.

U.S. Bank custody, EagleSTAR, prepared filings, email attachments, and derived
workbooks/files are excluded from this flow. They may be compared only after an
independent XML is generated.

The local workflow is implemented, but it cannot invent missing accounting,
policy, risk, liquidity, trade, or position data. NAV-equation and position-count
checks are automated; the other independent reconciliations still require real
control reports. See `NPORT_Runbook.pdf` and
`US_Bank_NPORT_Comprehensive_Final_Audit_2026-08-03.pdf`.
