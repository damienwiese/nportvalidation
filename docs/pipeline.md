# Technical pipeline

## Supported boundary

There is one production path:

```text
input workbook OR independent files + per-fund reference config
  -> content-addressed normalized files (input-workbook path only)
  -> prepare
  -> reviewed filing_inputs.xlsx
  -> evaluate + reconcile + preflight
  -> canonical model objects
  -> immutable canonical bundle
  -> reparse + validate
  -> XML builder
  -> SEC XSD validator
  -> versioned XML + integrity manifest
```

The program does not fetch email, SFTP, accounting, Bloomberg, or EDGAR data.
File acquisition and EDGAR transmission are operational handoffs outside this
repository. Bloomberg is an Excel calculation handoff, not an API integration.

`data/funds/` is the production registry, not a fixture directory. Each child
directory must represent a reviewed filing series with authoritative SEC
identifiers. Synthetic configurations live only under `tests/fixtures/` or the
dated archive. The registry contract test parses every active config, validates
its static identity, and rejects duplicate series/class identifiers or synthetic
markers.

## Artifact and ownership contract

| Artifact | Producer | Consumer | Authority |
|---|---|---|---|
| input workbook | `input-template`, source owners, reviewer | input-workbook importer | fund-partitioned July entry surface; not a release artifact |
| `_normalized/nport-v1.13/<workbook-sha256>/<fund>/<period>/*.csv` | input-workbook importer | `prepare` | immutable fund-period projection of the workbook |
| `data/funds/<fund>/fund_config.txt` | fund setup | `prepare` | reference only until each XML-impacting value is reviewed |
| positions CSV | internal position process | `prepare`, then `evaluate` | base holding population and unoverridden base values |
| orders CSV | internal create/redeem process | `prepare` | accepted CREATE/REDEEM notional for the three reporting months |
| `filing_inputs.xlsx` | `prepare`, Bloomberg Excel, reviewer | `status`, `preflight`, `validate`, `build` | sole release input |
| canonical run bundle | `finalize_inputs` | bundle reparser and release manifest | immutable serialized model snapshot |
| XML | `NportBuilder` | SEC XSD validator, downstream filing operation | validated release artifact |
| release manifest | build | audit/reproduction | hashes, policy context, environment, and release eligibility |

## 1. Prepare and ingest

The workbook entry point is:

```powershell
nport input-template 2026-07
nport prepare <fund> <YYYY-MM> --input-workbook <completed-workbook.xlsx>
```

The workbook schema is versioned with the N-PORT schema and covers the complete
fund universe. Every fund has `<FUND>_Config`, `<FUND>_FundData`, and
`<FUND>_Positions` sheets. Create/redeem activity remains in one consolidated
`Orders` sheet. It includes exact Bloomberg formulas for the three fund returns
and the narrow position-reference allowlist. Formula cells use the sheet fund,
period, asset branch, ticker/CUSIP, issuer category, and swap-reference CUSIP;
copying a starter row copies those formulas. Import
validates the workbook and selects exactly one fund-period. It rejects
unauthorized or modified formulas and other
structural drift, hashes the entire workbook, writes immutable normalized
position/order CSVs under that hash, and calls the same `prepare_inputs`
function used below. The input workbook contains values only; it does not expose
review statuses, source controls, comments, or reconciliation fields. Blank
values do not overwrite values derived from accepted orders. The importer turns
populated values into reviewed-workbook `PROVIDED` rows and assigns source
attribution deterministically. Downstream evaluation, models, reconciliation,
XML mapping, and XSD validation are identical for both entry points.

The formula rule is fail-closed: only the exact generated Bloomberg formulas
are accepted in their designated cells. The importer reads values cached by
Excel. A resolved result is attributed to the `BLOOMBERG` source; an unresolved
or error result stays blank and the standard `filing_inputs.xlsx` Bloomberg
formula remains available for the normal calculation handoff. A hard-coded
value replacing a generated formula is treated as input-workbook data.

The direct-file entry point is:

```powershell
nport prepare <fund> <YYYY-MM> --positions <positions.csv> [--orders <orders.csv>]
```

`prepare` performs deterministic local ingestion:

1. Parses `fund_config.txt` as UTF-8 `key=value` data into `FundConfig`.
2. Resolves supplied file paths and records SHA-256 plus CSV row counts.
3. Reads positions with `csv.DictReader`. Duplicate headers, over-wide rows,
   empty files, and duplicate record keys fail immediately.
4. Chooses each stable holding key in this order: explicit `holdingId`, ticker,
   `otherValue`, CUSIP, then row number. A collision must be resolved by adding
   unique `holdingId` values; it is never silently numbered.
5. Parses the optional order file using required headers `Ticker`, `Side`,
   `Trade Date`, `Notional`, and `Status`. Only `ACCEPTED` rows contribute.
   Dates and notionals are strict; invalid accepted rows block preparation.
6. Aggregates CREATE to `monXSales` and REDEEM to `monXRedemption` with exact
   decimal arithmetic. The order file does not supply reinvestment.
7. Generates Bloomberg formulas for the three monthly returns and supported
   position/reference fields.
8. Expands conditional holding requirements based on debt/derivative branch,
   reference-instrument branch, and swap-leg branch.
9. Writes the workbook through a same-directory temporary file and atomic rename.

Refreshing a workbook preserves editable cells only for keys that still exist.
Deleted positions and retired reconciliation checks are dropped. Extra `Sources`
rows are preserved because they are optional provenance registrations.

## 2. Workbook handoff

The output is:

`data/funds/<fund>/filings/<period>/filing_inputs.xlsx`

The input sheets have fixed schemas:

| Sheet | Key | What supplies model values |
|---|---|---|
| `FundFields` | `(targetFile, recordKey, fieldName)` | `proposedValue` when `status=PROVIDED`; otherwise eligible `currentValue` |
| `HoldingFields` | `(targetFile, recordKey, fieldName)` | reviewed override, explicit omission, or original position value |
| `ReconciliationInputs` | `checkId` | independent `controlValue`, `tolerance`, disposition, and comment |
| `Sources` | `sourceId` | provenance only; it never supplies a field value by itself |

Controlled statuses are `MISSING`, `PROVIDED`, and `NOT_APPLICABLE`.
`SYSTEM_DERIVED` is reserved for `submissionType`, `repPdEnd`, `repPdDate`, and
`derivativesRegime`; `SYSTEM_CONTROL` is reserved for `liveTestFlag`. A reviewer
cannot assign a system status to bypass review. Any other status is rejected.

For a Bloomberg handoff, open the workbook on a Bloomberg-enabled Excel machine,
wait for the `Bloomberg` sheet to calculate, and save. Evaluation opens the file
with cached values (`data_only=True`); an uncalculated formula therefore remains
missing and blocks release.

## 3. Evaluation and model assembly

`evaluate_inputs` validates workbook structure before interpreting cells:

- required sheets and headers must exist;
- keys, source IDs, and datasets must not conflict;
- field names and target files must belong to the canonical maps;
- holding rows must refer to the current position population;
- used source files must still exist and match the hash recorded at prepare time;
- prohibited comparison/prepared-filing sources are rejected.

It then builds the models:

- `FundConfig`: baseline config plus reviewed fund-config rows. The baseline is
  never enough by itself: release requires reviewed `proposedValue` cells.
- `FilingData`: reviewed filing rows, followed by policy-derived period end,
  fiscal year end, submission type, and derivative regime.
- `list[Holding]`: every source position, with reviewed overrides keyed by
  `(holdingId, fieldName)`. `NOT_APPLICABLE` explicitly clears an optional source
  value. Dates and coupon kinds are normalized before object construction.

All canonical model fields are strings deliberately. This preserves the exact
lexical values that will be serialized into SEC XML; `input_validation.py` owns
numeric, date, enum, JSON, and cross-field interpretation.

That pre-serialization type gate is independent of the XSD. It rejects invalid
ISO dates, non-finite decimals, invalid enumerations and Y/N values, malformed
country/currency/identifier codes, invalid JSON structures, and invalid swap
reset/tenor units before XML exists. It also enforces internal contracts the XSD
cannot see: workbook status vocabulary, unique row identities, source hashes,
field applicability, policy consistency, and accounting reconciliations. The
bundled XSD remains the final check on XML structure and SEC lexical types.

See [field-lineage.md](field-lineage.md) for the exhaustive mapping contract.

## 4. Reconciliation and validation gates

The gate order is fixed:

1. Workbook structure, row identity, controlled status, source boundary, and
   source-file hash integrity.
2. Completeness of every applicable workbook field.
3. `validate_config`, `validate_filing`, and `validate_holdings`: formats,
   enums, finite decimals, dates, JSON shape, derivative/debt branch completeness,
   identifiers, NAV equation, and holding percentages.
4. Reconciliation: NAV equation; position `valUSD` total to independent GL;
   nine flow fields to supplied controls; and, when applicable, derivative
   market value and unrealized appreciation to independent controls.
5. Policy preflight: fiscal calendar, NPORT-P/NPORT-NP derivation, B.2.f, B.9,
   B.10, relative-VaR benchmark, and C.7 applicability.
6. Canonical serialization, reparse, and the same model/preflight validation.
7. XML construction and SEC N-PORT XSD v1.13 validation.

Numeric calculations use decimal arithmetic. The NAV identity allows a fixed
`0.02` currency-unit rounding difference. The holding percentage tie allows
`max(0.50 percentage points, 0.005 × holding count)`. Each independent
reconciliation row supplies its own nonnegative tolerance; the build records
the actual difference and blocks when its absolute value exceeds that limit.

Warnings are informational. Any blocker/error stops retained release output.

```powershell
nport status <fund> <period>
nport preflight <fund> <period>
nport validate <fund> <period>
```

`validate` uses temporary storage and retains nothing. `status`, `preflight`, and
`validate` do not mutate active filing data.

The only runtime cache is the seven-day throttle for the optional SEC schema
update check. It defaults to the operating-system temporary directory under
`nportvalidation/schema-check-v<SCHEMA>.json`, can be relocated with
`NPORT_CACHE_DIR`, and is never used as filing input. Tests pin the clock and
cache path and never depend on the network.

The deterministic test suite covers parser rejection paths, every canonical
holding branch, every branch-required field, invalid lexical types, exact
decimal arithmetic, tolerance boundaries, canonical-bundle immutability,
atomic failure behavior, XML mappings, and final XSD validation.

## 5. Canonical bundle and release

```powershell
nport build <fund> <period> [--dry-run]
```

A successful retained build writes a new run ID; it does not overwrite a prior
release:

```text
data/builds/<fund>/<period>/nport-v<SCHEMA>/<run-id>/
  fund_config.txt
  filing_data.txt
  holdings.csv
  source_manifest.csv
  field_provenance.csv
  reconciliation.csv
  input_receipt.json

output/<fund>/<period>/nport-v<SCHEMA>/<run-id>/
  <FUND>_<PERIOD>_nport-v<SCHEMA>_<RUN-ID>.xml
  <FUND>_<PERIOD>_nport-v<SCHEMA>_<RUN-ID>.manifest.json
```

`field_provenance.csv` records every canonical holding field and every supplied
fund field with its record key, value, source ID, and method (`SOURCE_FILE`,
`MANUAL_INPUT`, or `BLOOMBERG_FORMULA`). `input_receipt.json` hashes the workbook
and every bundle file. The release manifest hashes the XML and bundle files.

XML and manifests use temporary-file replacement. If manifest creation fails,
the just-created XML is rolled back so a partial release is not left behind.
The CLI exposes configurable bundle and release roots, but no arbitrary filename
override; every retained artifact follows the same versioned naming contract.

`--dry-run` executes finalization, reparse, model checks, XML construction, and
XSD validation entirely in temporary storage.

## Explicitly outside this pipeline

- mailbox/SFTP/ICE/accounting/Bloomberg API ingestion;
- custodian, administrator, prepared-filing, or historical XML values as inputs;
- portfolio-wide batch orchestration;
- Part F/NPORT-EX construction;
- EDGAR transmission.
