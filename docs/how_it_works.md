# How the In-House N-PORT Service Works

An operator starts with an independent period-end positions export and optional
create/redeem export, then runs `nport prepare`. The command creates one workbook
at `data/funds/<fund>/filings/<period>/filing_inputs.xlsx`. Fund policy, filing
values, holding exceptions, and reconciliation controls have explicit rows.

The reviewer completes only XML values, policy/applicability inputs that change
the XML, and reconciliation controls. `sourceId`, Sources metadata, manifests,
hashes, counts, and source cutoffs are optional diagnostics; they do not appear
in XML and do not gate the build. `nport build <fund> <period> --from-inputs`
validates inputs, runs reconciliation and preflight, generates XML, runs the SEC
XSD, and writes a release manifest.

U.S. Bank custody, EagleSTAR, prepared filings, email attachments, and derived
workbooks/files are excluded from this flow. They may be compared only after an
independent XML is generated.

The local workflow is implemented, but it cannot invent missing accounting,
policy, risk, liquidity, trade, or position data. The NAV equation is automated;
other reconciliations require the actual control totals and tolerances entered in
`ReconciliationInputs`. See `NPORT_Runbook.pdf` and
`US_Bank_NPORT_Comprehensive_Final_Audit_2026-08-03.pdf`.
