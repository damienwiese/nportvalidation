# Retired repository artifacts

This directory preserves the retired master-workbook, custodian/EagleSTAR,
reference-comparison, EDGAR-download, generated-documentation, and one-off
maintenance implementation that existed before the pipeline was reduced to:

`prepare -> workbook review -> status/preflight -> validate -> build`

Nothing under this directory is imported by the `nport` package or exposed by
the supported CLI. The inventory in this directory preserves the original
pre-consolidation move record. The authoritative post-cleanup paths and hashes
are in `../inventory.csv`; ignored local exports are in `../local-artifacts/`.
