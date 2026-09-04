# Production fund registry

Each child directory under this path is an active, reviewed fund configuration:

```text
data/funds/<fund>/fund_config.txt
```

The directory name is the CLI fund key. `fund_config.txt` contains authoritative
static filing identity and reviewed policy values; it must not contain synthetic,
placeholder, or copied identifiers. The test suite parses every config and rejects
invalid identities, duplicate series/class IDs, and synthetic markers.

Period-specific workbooks are generated beneath the same directory by `nport
prepare`; they are operational artifacts and are not committed as reference data.
Synthetic examples belong under `tests/fixtures/`. Retired fund data belongs only
under the dated archive and is never a default CLI input.

`fund_universe.csv` is the complete ordered list of 197 fund tickers used to
generate the fund-partitioned input workbook. It preserves the Thematic, 2x
Leveraged, Structured Buffer, and Fixed Income group order. A ticker can exist
in that universe before it has an active reviewed `fund_config.txt`; its Config
sheet is left blank and it cannot enter the filing run path until authoritative
static configuration is activated.
