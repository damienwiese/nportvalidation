"""Fund-level human-review workflow and fail-closed provenance controls."""

from pathlib import Path
import shutil

from openpyxl import load_workbook

from nport.config import _CONFIG_KEY_MAP, _FILING_KEY_MAP, parse_filing
from nport.fund_review import evaluate_review, finalize_review, prepare_review
from nport.preflight import sha256_file


def _sheet_rows(workbook: Path, sheet: str):
    wb = load_workbook(workbook, data_only=True)
    ws = wb[sheet]
    headers = [cell.value for cell in ws[1]]
    return [dict(zip(headers, ("" if value is None else str(value) for value in row)))
            for row in ws.iter_rows(min_row=2, values_only=True)]


def test_prepare_review_creates_all_13_gap_locations_without_accounting_defaults(tmp_path, fdrs_dir):
    fund_dir = tmp_path / "fdrs"
    fund_dir.mkdir()
    shutil.copyfile(fdrs_dir / "fund_config.txt", fund_dir / "fund_config.txt")

    workbook = prepare_review(fund_dir, "2025-12")
    wb = load_workbook(workbook, data_only=True)

    assert wb.sheetnames == [
        "Summary", "GapGuide", "FundFields", "HoldingFields",
        "Sources", "Approvals", "Reconciliation",
    ]
    assert len(list(wb["GapGuide"].iter_rows(min_row=2, values_only=True))) == 13
    totals = [row for row in _sheet_rows(workbook, "FundFields")
              if row["fieldName"] == "totAssets"]
    assert totals[0]["currentValue"] == ""
    assert totals[0]["proposedValue"] == ""
    assert totals[0]["status"] == "MISSING"


def test_prohibited_us_bank_source_is_reported_as_blocker(tmp_path, fdrs_dir):
    fund_dir = tmp_path / "fdrs"
    fund_dir.mkdir()
    shutil.copyfile(fdrs_dir / "fund_config.txt", fund_dir / "fund_config.txt")
    positions = tmp_path / "US Bank Positions.csv"
    shutil.copyfile(fdrs_dir / "filings" / "2025-12" / "holdings.csv", positions)
    workbook = prepare_review(fund_dir, "2025-12", positions=positions)

    wb = load_workbook(workbook)
    ws = wb["Sources"]
    headers = {cell.value: cell.column for cell in ws[1]}
    for field, value in {
        "sourceSystem": "U.S. Bank custody", "sourceAsOf": "2025-12-31",
        "acquiredAt": "2026-01-02T12:00:00Z", "preparedBy": "Ops A",
        "reviewedBy": "Ops B", "reviewedAt": "2026-01-03T12:00:00Z",
        "status": "APPROVED",
    }.items():
        ws.cell(2, headers[field], value)
    wb.save(workbook)

    result = evaluate_review(fund_dir, "2025-12")
    assert "REVIEW_SOURCE_PROHIBITED" in {item.code for item in result["blockers"]}


def test_approved_review_finalizes_clean_traceable_bundle(tmp_path, fdrs_dir):
    fund_dir = tmp_path / "fdrs"
    fund_dir.mkdir()
    shutil.copyfile(fdrs_dir / "fund_config.txt", fund_dir / "fund_config.txt")
    positions = tmp_path / "internal_positions.csv"
    shutil.copyfile(fdrs_dir / "filings" / "2025-12" / "holdings.csv", positions)
    support = tmp_path / "internal_accounting_and_policy.csv"
    support.write_text("control,value\nperiod,2025-12-31\n", encoding="utf-8")
    workbook = prepare_review(fund_dir, "2025-12", positions=positions)
    filing = parse_filing(fdrs_dir / "filings" / "2025-12" / "filing_data.txt")

    source_as_of = "2025-12-31"
    reviewed_at = "2026-01-05T12:00:00Z"
    wb = load_workbook(workbook)

    sources = wb["Sources"]
    source_headers = {cell.value: cell.column for cell in sources[1]}
    for field, value in {
        "sourceSystem": "Internal OMS", "sourceAsOf": source_as_of,
        "acquiredAt": "2026-01-02T12:00:00Z", "preparedBy": "Ops A",
        "reviewedBy": "Ops B", "reviewedAt": reviewed_at, "status": "APPROVED",
    }.items():
        sources.cell(2, source_headers[field], value)
    evidence = {
        "sourceId": "EVIDENCE", "dataset": "internal_fund_accounting_and_policy",
        "sourceType": "INTERNAL_CONTROL_PACKAGE", "sourceSystem": "Internal books and records",
        "sourcePath": str(support), "sourceAsOf": source_as_of,
        "acquiredAt": "2026-01-02T12:00:00Z", "sha256": sha256_file(support),
        "recordCount": "1", "preparedBy": "Accounting A", "reviewedBy": "Accounting B",
        "reviewedAt": reviewed_at, "status": "APPROVED", "comment": "Synthetic test evidence",
    }
    sources.append([evidence.get(sources.cell(1, column).value, "")
                    for column in range(1, sources.max_column + 1)])

    policy_values = {
        "fiscalYearEndMMDD": "12-31", "derivativesRegimePolicy": "NONE",
        "liquidityRequired": "N", "cashB2fRequired": "N",
        "policyEffectiveFrom": "2020-01-01", "policyApprovedBy": "Compliance B",
        "policyApprovedAt": "2025-01-01T12:00:00Z",
        "policySourceRef": "Internal policy memorandum 2025-01",
    }
    fields = wb["FundFields"]
    field_headers = {cell.value: cell.column for cell in fields[1]}
    for rownum in range(2, fields.max_row + 1):
        target = fields.cell(rownum, field_headers["targetFile"]).value
        name = fields.cell(rownum, field_headers["fieldName"]).value
        status = fields.cell(rownum, field_headers["status"]).value
        if status in {"SYSTEM_DERIVED", "SYSTEM_CONTROL"}:
            continue
        value = ""
        if target == "fund_config.txt":
            value = policy_values.get(name, fields.cell(rownum, field_headers["currentValue"]).value or "")
        elif name in _FILING_KEY_MAP:
            value = getattr(filing, _FILING_KEY_MAP[name])
        if not value:
            fields.cell(rownum, field_headers["status"], "NOT_APPLICABLE")
            fields.cell(rownum, field_headers["comment"], "Not applicable for this synthetic test fund")
        else:
            fields.cell(rownum, field_headers["proposedValue"], str(value))
            fields.cell(rownum, field_headers["status"], "APPROVED")
        fields.cell(rownum, field_headers["sourceId"], "EVIDENCE")
        fields.cell(rownum, field_headers["sourceAsOf"], source_as_of)
        fields.cell(rownum, field_headers["reviewer"], "Reviewer B")
        fields.cell(rownum, field_headers["reviewedAt"], reviewed_at)

    holdings = wb["HoldingFields"]
    holding_headers = {cell.value: cell.column for cell in holdings[1]}
    for rownum in range(2, holdings.max_row + 1):
        current = holdings.cell(rownum, holding_headers["currentValue"]).value or ""
        holdings.cell(rownum, holding_headers["status"], "APPROVED" if current else "NOT_APPLICABLE")
        holdings.cell(rownum, holding_headers["sourceId"], "POSITIONS")
        holdings.cell(rownum, holding_headers["sourceAsOf"], source_as_of)
        holdings.cell(rownum, holding_headers["reviewer"], "Reviewer B")
        holdings.cell(rownum, holding_headers["reviewedAt"], reviewed_at)
        if not current:
            holdings.cell(rownum, holding_headers["comment"], "Not applicable in source record")

    approvals = wb["Approvals"]
    approval_headers = {cell.value: cell.column for cell in approvals[1]}
    for rownum, name in ((2, "Preparer A"), (3, "Reviewer B")):
        approvals.cell(rownum, approval_headers["name"], name)
        approvals.cell(rownum, approval_headers["approvedAt"], reviewed_at)
        approvals.cell(rownum, approval_headers["status"], "APPROVED")
    wb.save(workbook)

    result = evaluate_review(fund_dir, "2025-12")
    assert result["blockers"] == []
    bundle = finalize_review(fund_dir, "2025-12", output_root=tmp_path / "builds", run_id="test-run")
    assert {path.name for path in bundle.iterdir()} == {
        "fund_config.txt", "filing_data.txt", "holdings.csv", "source_manifest.csv",
        "field_provenance.csv", "reconciliation.csv", "review_receipt.json",
    }
    provenance = (bundle / "field_provenance.csv").read_text(encoding="utf-8")
    assert "fund_config.txt,FUND,cik" in provenance
    assert "filing_data.txt,FUND,totAssets" in provenance
