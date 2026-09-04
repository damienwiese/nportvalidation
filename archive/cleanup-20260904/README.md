# Pipeline cleanup archive (2026-09-04)

This is the single archive root for everything removed from the supported
N-PORT run path during the 2026-09-04 production cleanup.

- `retired-repo/` contains source-controlled historical inputs, generated
  outputs, scripts, tests, documentation, superseded implementation, and 89
  synthetic fund configurations removed from the production registry.
- `local-artifacts/` contains ignored local work products, prior output runs,
  old intake batches, workbooks, caches, lock files, and temporary files. It is
  intentionally excluded from Git because it can contain client data.

Nothing below this directory is imported by `src/nport`, collected by the test
suite, read by the CLI, or used for a release. The live path is documented in
the repository `README.md` and `docs/pipeline.md`.

`inventory.csv` is the post-cleanup inventory of accessible archived files,
with actual archive-relative paths, sizes, and SHA-256 hashes. A small number of
old pytest temporary directories have Windows ACLs that prevent enumeration;
they remain contained under `local-artifacts/tmp/` and outside the run path.
