# nport

Build SEC Form N-PORT XML from the operating inputs already received: custodian
positions, EagleSTAR fund accounting, create/redeem orders, Bloomberg enrichment,
and one centralized human-review workbook.

## One-time setup

```powershell
Set-Location "C:\Users\damie\nportvalidation"
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]"
```

## Complete monthly workflow

The example period is `2026-06`. There is no manually created `positions.csv`.

### 1. Put the received files in these three folders

```text
data/custodian/          # custodian positions CSV
data/fund_accounting/    # EagleSTAR .zip or .mbox
data/orders/             # create/redeem orders CSV
```

### 2. Load all three inputs

```powershell
& ".\.venv\Scripts\nport.exe" masters 2026-06
```

The command auto-detects the files by their contents and prints the exact paths
it selected. It creates:

```text
data/master/security_master.xlsx
data/master/filing_master.xlsx
```

If more than one candidate exists, specify the exact files explicitly:

```powershell
& ".\.venv\Scripts\nport.exe" masters 2026-06 `
  --custodian ".\data\custodian\custodian.csv" `
  --fund-accounting ".\data\fund_accounting\eaglestar.zip" `
  --ap-orders ".\data\orders\create_redeem.csv"
```

### 3. Let Bloomberg populate

Open both master workbooks on a Bloomberg terminal, wait for formulas to finish,
then save and close both files.

### 4. Complete the one human-review workbook

```powershell
& ".\.venv\Scripts\nport.exe" mergehumanreview 2026-06
```

Open `data/humanreview/2026-06_review.xlsx`. Fill every required blank reported
by the command. Save and close it, then apply the entries:

```powershell
& ".\.venv\Scripts\nport.exe" mergehumanreview 2026-06
```

If the command still reports required blanks, fix those exact rows and rerun it.

### 5. Write the reviewed data to each fund

```powershell
& ".\.venv\Scripts\nport.exe" split 2026-06
```

### 6. Build XML

```powershell
& ".\.venv\Scripts\nport.exe" build
```

To build only one fund:

```powershell
& ".\.venv\Scripts\nport.exe" build fdrs 2026-06
```

The final operating sequence is therefore:

```text
masters -> open/save both workbooks in Bloomberg -> mergehumanreview
-> human fills one review workbook -> mergehumanreview -> split -> build
```

Custodian, EagleSTAR, and create/redeem data enter only through `masters`.
Human corrections enter only through `data/humanreview/<period>_review.xlsx`.
Do not manually create a `positions.csv` for this workflow.

### Optional read-only comparison

Run this only after the independent XML exists and only when the reference uses
the same fund and report date:

```powershell
& ".\.venv\Scripts\nport.exe" compare-reference `
  --internal ".\output\FDRS_2026-06.xml" `
  --reference "<aligned-reference.xml>"
```

Reference filings are comparison outputs; they are not operating inputs.

Run `nport guide` at any time to print the same sequence in the terminal.
