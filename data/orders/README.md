# Create/redeem order input

Place the create/redeem order CSV used for the filing month in this directory.
`nport masters <period>` detects a CSV containing the columns `Ticker`, `Side`,
`Trade Date`, and `Notional`. Use `--ap-orders <path>` when more than one file is
present and you need to select one explicitly.
