# N-PORT filing pipeline

This repository has one supported operating path:

```text
multi-fund input workbook OR canonical positions + optional orders
    -> immutable normalized CSVs
    -> filing_inputs.xlsx
    -> Bloomberg calculation and human review
    -> status / preflight / validation
    -> versioned canonical bundle
    -> SEC-XSD-valid XML and release manifest
```

It does not connect to mailboxes, SFTP servers, accounting systems, Bloomberg
APIs, or EDGAR. Source files are acquired outside the application. Bloomberg
enrichment occurs when an operator opens and saves the generated workbook on a
Bloomberg-enabled Excel workstation.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Monthly commands

```powershell
# Create the July workbook covering the complete 197-fund universe.
nport input-template 2026-07

# After completing it, select one fund-period into the normal review path.
nport prepare FDRS 2026-07 --input-workbook data\inputs\nport-v1.13\nport-inputs-v4_2026-07_nport-v1.13.xlsx

# The direct CSV entry point remains available for system exports.
nport prepare FDRS 2026-07 --positions C:\intake\fdrs_positions.csv --orders C:\intake\orders.csv
nport status FDRS 2026-07
nport preflight FDRS 2026-07
nport validate FDRS 2026-07
nport build FDRS 2026-07 --dry-run
nport build FDRS 2026-07
```

The input workbook contains three fund-specific sheets for every registered
fund—`<FUND>_Config`, `<FUND>_FundData`, and `<FUND>_Positions`—plus one
consolidated `Orders` sheet. It has only identifiers and values to enter; review
statuses, provenance, and reconciliation controls are downstream. Controlled
Bloomberg formulas populate the three fund returns and allowlisted position
reference fields after the lookup identifiers are entered and the workbook is
calculated and saved in Bloomberg-enabled Excel. Importing it writes
content-hashed, immutable normalized CSVs beside the workbook, then invokes the
same `prepare` implementation as the direct CSV path.

`prepare` writes
`data/funds/<fund>/filings/<period>/filing_inputs.xlsx`. Open that workbook on
Bloomberg, save calculated results, and complete every `MISSING` row in
`FundFields`, `HoldingFields`, and `ReconciliationInputs`.

`build` has no direct-file bypass. It always evaluates the reviewed workbook,
applies policy from the fund's reviewed configuration, requires reconciliation
to pass, validates the serialized canonical bundle, and validates the XML
against the bundled SEC schema.

Successful builds write:

```text
data/builds/<fund>/<period>/nport-v<SCHEMA>/<run-id>/
    fund_config.txt
    filing_data.txt
    holdings.csv
    source_manifest.csv
    field_provenance.csv
    reconciliation.csv
    input_receipt.json

output/<fund>/<period>/nport-v<SCHEMA>/<run-id>/<FUND>_<PERIOD>_nport-v<SCHEMA>_<RUN-ID>.xml
output/<fund>/<period>/nport-v<SCHEMA>/<run-id>/<FUND>_<PERIOD>_nport-v<SCHEMA>_<RUN-ID>.manifest.json
```

TEST is the safe default. The application does not transmit filings to EDGAR.
Part F / NPORT-EX is not implemented and is intentionally absent from the
input workbook.

Only reviewed, authoritative fund configurations belong in `data/funds/`.
Synthetic configs and historical filing data are archived and cannot be selected
by the default CLI path. See [data/funds/README.md](data/funds/README.md) for the
production-registry contract.

See [docs/pipeline.md](docs/pipeline.md) for the handoffs and failure behavior,
and [docs/inputs.md](docs/inputs.md) for the fund-partitioned input contract. See
[docs/field-lineage.md](docs/field-lineage.md) for source-to-model-to-XML
mapping. Everything displaced by this cleanup is preserved under the single
`archive/cleanup-20260904/` root and is not part of the installed package.
