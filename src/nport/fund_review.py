"""Fund-period human review, provenance, and clean canonical finalization.

This module creates places for missing values; it never supplies business data.
Every accepted human value must cite an approved, non-U.S.-Bank source file.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

from nport.ap_orders import aggregate_flows, parse_ap_orders
from nport.config import (
    _CONFIG_KEY_MAP, _FILING_KEY_MAP, _HOLDINGS_KEY_MAP,
    _OPTIONAL_FILING_KEYS, parse_config,
)
from nport.input_validation import validate_all
from nport.models import FilingData, FundConfig, Holding
from nport.policy import apply_context, derive_context_from_config, report_date_for_period
from nport.preflight import Finding, _is_prohibited_source, sha256_file
from nport.schema import FIELD_SPECS, get_required_fields


REVIEW_FILENAME = "human_review.xlsx"

FIELD_HEADERS = [
    "gapId", "targetFile", "recordKey", "fieldName", "currentValue",
    "proposedValue", "sourceId", "sourceAsOf", "status", "reviewer",
    "reviewedAt", "comment",
]
SOURCE_HEADERS = [
    "sourceId", "dataset", "sourceType", "sourceSystem", "sourcePath",
    "sourceAsOf", "acquiredAt", "sha256", "recordCount", "preparedBy",
    "reviewedBy", "reviewedAt", "status", "comment",
]
APPROVAL_HEADERS = ["role", "name", "approvedAt", "status", "comment"]

POLICY_FIELDS = {
    "fiscalYearEndMMDD": "fiscal_year_end_mmdd",
    "derivativesRegimePolicy": "derivatives_regime_policy",
    "liquidityRequired": "liquidity_required",
    "cashB2fRequired": "cash_b2f_required",
    "policyEffectiveFrom": "policy_effective_from",
    "policyEffectiveTo": "policy_effective_to",
    "policyApprovedBy": "policy_approved_by",
    "policyApprovedAt": "policy_approved_at",
    "policySourceRef": "policy_source_ref",
}

SYSTEM_DERIVED_FILING = {
    "submissionType", "repPdEnd", "repPdDate", "derivativesRegime",
}

SENSITIVE_HOLDING_GROUPS = {"debt", "deriv_common", "option", "ref_instrument", "swap", "liquidity"}

GAP_GUIDE = [
    ("G-001", "Independent position population", "data/intake/<period>/<fund>/positions.csv", "Sources + HoldingFields",
     "Attach an independently produced period-end positions CSV. Review every surfaced holding exception."),
    ("G-002", "Independent fund-accounting close", "accounting_close.csv or accounting_close.pdf", "Sources + FundFields",
     "Add the approved internal GL/NAV close as a source, then enter each supported filing-level value."),
    ("G-003", "Create/redeem flows", "create_redeem_orders.csv; reinvestment_support.csv if applicable", "Sources + FundFields",
     "Attach the internal order export. Calculated sales/redemptions still require review; reinvestment needs separate evidence."),
    ("G-004", "Fund policy and static data", "fund_policy_approval.pdf; fund_static_data.csv", "FundFields",
     "Confirm every fund configuration and effective-dated policy value from internal governance evidence."),
    ("G-005", "Source manifest", "human_review.xlsx -> source_manifest.csv", "Sources",
     "Complete cutoff, capture time, hash, count, preparer, reviewer, and approval for every source used."),
    ("G-006", "Prohibited legacy inputs", "data/custodian/*; data/fund_accounting/*; data/master/*.xlsx; legacy data/funds/* files", "Sources",
     "Do not cite U.S. Bank, EagleSTAR, prepared filings, current masters, or files derived from them."),
    ("G-007", "Human-review evidence", "human_review.xlsx -> field_provenance.csv and review_receipt.json", "FundFields + HoldingFields + Approvals",
     "Every accepted value or not-applicable disposition needs a source, reviewer, timestamp, and explanation."),
    ("G-008", "Swap economics", "swap_trade_export.csv; executed_swap_confirmations.pdf", "HoldingFields",
     "Resolve surfaced swap terms from internal trade capture or an independently retained executed confirmation."),
    ("G-009", "Conditional filing sections", "cash_ledger.csv; risk_metrics.csv; rule_18f4_results.csv; var_backtesting.csv; monthly_return_categories.csv", "FundFields",
     "Enter B.2.f/B.3/B.5.c/B.9/B.10 data from internal accounting or risk evidence, or document not-applicable."),
    ("G-010", "Liquidity classification", "liquidity_classifications.csv; liquidity_circumstances.csv if applicable", "HoldingFields",
     "Enter C.7 classifications from the internal liquidity-risk process for each applicable holding."),
    ("G-011", "Option terms and delta", "option_trade_terms.csv; option_delta.csv", "HoldingFields",
     "Confirm option terms and delta from internal trade/risk evidence at the reporting cutoff."),
    ("G-012", "Reconciliation", "reconciliation.csv; positions_to_gl_reconciliation.csv; flow_reconciliation.csv; derivatives_reconciliation.csv", "Reconciliation",
     "Clear automated count and NAV-equation exceptions; retain the supporting internal control report."),
    ("G-013", "Origin assurance", "source_origin_attestation.pdf; review_receipt.json", "Sources + review receipt",
     "Local hashes catch changed or exact known files; reviewers must attest to origin because this local workflow has no authenticated connector."),
]


class ReviewBlocked(ValueError):
    """Raised when a review package has unresolved release blockers."""

    def __init__(self, blockers: list[Finding]):
        self.blockers = blockers
        super().__init__(f"review package has {len(blockers)} blocker(s)")


def review_path(fund_dir: str | Path, period: str) -> Path:
    return Path(fund_dir) / "filings" / period / REVIEW_FILENAME


def _hash(path: Path) -> str:
    return sha256_file(path)


def _read_sheet(path: Path, sheet: str) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    wb = load_workbook(path, data_only=True, read_only=True)
    if sheet not in wb.sheetnames:
        return []
    rows = list(wb[sheet].iter_rows(values_only=True))
    if not rows:
        return []
    headers = ["" if value is None else str(value).strip() for value in rows[0]]
    out: list[dict[str, str]] = []
    for raw in rows[1:]:
        if not raw or all(value is None for value in raw):
            continue
        out.append({
            headers[i]: "" if raw[i] is None else str(raw[i]).strip()
            for i in range(min(len(headers), len(raw))) if headers[i]
        })
    return out


def _field_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row.get("targetFile", ""), row.get("recordKey", ""), row.get("fieldName", "")


def _merge_preserved(
    generated: list[dict[str, str]], existing: list[dict[str, str]],
    key_fn,
) -> list[dict[str, str]]:
    prior = {key_fn(row): row for row in existing}
    editable = {
        "proposedValue", "sourceId", "sourceAsOf", "status", "reviewer",
        "reviewedAt", "comment", "preparedBy", "reviewedBy", "dataset",
        "sourceType", "sourceSystem", "sourcePath", "acquiredAt", "recordCount",
        "name", "approvedAt",
    }
    out = []
    for row in generated:
        merged = dict(row)
        old = prior.get(key_fn(row))
        if old:
            for key in editable:
                if old.get(key, ""):
                    merged[key] = old[key]
        out.append(merged)
    for key, old in prior.items():
        if key not in {key_fn(row) for row in generated}:
            out.append(old)
    return out


def _write_table(
    ws, headers: list[str], rows: list[dict[str, str]], *,
    editable_headers: set[str] | None = None,
) -> None:
    """Write a clean review table and visibly distinguish operator input columns."""
    editable_headers = editable_headers or set()
    thin = Side(style="thin", color="D4DDE6")
    ws.append(headers)
    for header, cell in zip(headers, ws[1]):
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            "solid", fgColor="356F78" if header in editable_headers else "28465C"
        )
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in rows:
        ws.append([row.get(header, "") for header in headers])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.zoomScale = 85
    ws.row_dimensions[1].height = 30
    for column in ws.columns:
        letter = column[0].column_letter
        width = min(42, max(12, max(len(str(cell.value or "")) for cell in column) + 2))
        ws.column_dimensions[letter].width = width
    for row_cells in ws.iter_rows(min_row=2):
        for cell in row_cells:
            cell.number_format = "@"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)


def _add_list_validation(ws, header: str, values: list[str]) -> None:
    """Add an Excel dropdown to a named column without supplying a decision."""
    headers = {cell.value: cell.column for cell in ws[1]}
    column = headers[header]
    letter = ws.cell(1, column).column_letter
    validation = DataValidation(
        type="list", formula1='"' + ",".join(values) + '"', allow_blank=False,
    )
    validation.error = "Choose one of the controlled workflow statuses."
    validation.errorTitle = "Invalid status"
    validation.prompt = "Select the status that matches the evidence and review state."
    validation.promptTitle = "Controlled status"
    validation.showErrorMessage = True
    validation.showInputMessage = True
    ws.add_data_validation(validation)
    validation.add(f"{letter}2:{letter}{max(2, ws.max_row)}")


def _gap_row(
    gap_id: str, target: str, key: str, field: str, current: str = "",
    status: str = "MISSING", comment: str = "",
) -> dict[str, str]:
    return {
        "gapId": gap_id, "targetFile": target, "recordKey": key,
        "fieldName": field, "currentValue": current, "proposedValue": "",
        "sourceId": "", "sourceAsOf": "", "status": status,
        "reviewer": "", "reviewedAt": "", "comment": comment,
    }


def _config_rows(config: FundConfig) -> list[dict[str, str]]:
    rows = []
    for external, attr in _CONFIG_KEY_MAP.items():
        if external == "requiredSources":
            # Derived from the approved rows on Sources; operators do not type it.
            continue
        value = getattr(config, attr, "")
        is_policy = external in POLICY_FIELDS
        rows.append(_gap_row(
            f"G-004:{external}", "fund_config.txt", "FUND", external, value,
            "NEEDS_REVIEW" if value else "MISSING",
            ("Confirm from an approved internal policy/governance record."
             if is_policy else "Confirm from approved internal legal/entity/static-data evidence."),
        ))
    return rows


def _filing_rows() -> list[dict[str, str]]:
    rows = []
    for external, attr in _FILING_KEY_MAP.items():
        if external in SYSTEM_DERIVED_FILING:
            rows.append(_gap_row(
                f"SYSTEM:{external}", "filing_data.txt", "FUND", external,
                "", "SYSTEM_DERIVED", "Derived from period and approved fund policy.",
            ))
            continue
        current = "TEST" if external == "liveTestFlag" else ""
        status = "SYSTEM_CONTROL" if external == "liveTestFlag" else "MISSING"
        gap = "G-002"
        if external.startswith("mon"):
            gap = "G-003"
        elif external in {"cashNotReportedInCOrD", "curMetricsJson", "creditSprdRiskIgJson",
                          "creditSprdRiskNonigJson", "monthlyReturnCategoriesJson"} or \
                external.startswith(("deriv", "median", "backtesting")):
            gap = "G-009"
        rows.append(_gap_row(
            f"{gap}:{external}", "filing_data.txt", "FUND", external,
            current, status, "No default business value is supplied.",
        ))
    return rows


def _holding_ids(rows: list[dict[str, str]]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for index, row in enumerate(rows, 1):
        base = (row.get("holdingId") or row.get("ticker") or row.get("otherValue")
                or row.get("cusip") or f"row-{index}").strip()
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append(base if count == 0 else f"{base}-{count}")
    return out


def _raw_positions(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    return _holding_ids(rows), rows


def _holding_review_rows(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    ids, positions = _raw_positions(path)
    spec_by_external = {spec.csv_header: spec for spec in FIELD_SPECS}
    rows: list[dict[str, str]] = []
    for hid, position in zip(ids, positions):
        deriv = position.get("derivCat", "")
        has_debt = bool(position.get("maturityDt")) or position.get("assetCat") in {
            "DBT", "ABS-MBS", "ABS-CBDO", "ABS-O",
        }
        required_internal = set(get_required_fields(deriv, has_debt))
        required_external = {
            next(spec.csv_header for spec in FIELD_SPECS if spec.name == name)
            for name in required_internal
        }
        for external, spec in spec_by_external.items():
            value = position.get(external, "")
            sensitive = spec.group in SENSITIVE_HOLDING_GROUPS and (
                value or external in required_external
            )
            if not value and external not in required_external:
                continue
            if value and not sensitive:
                continue
            gap = "G-001"
            if spec.group == "swap":
                gap = "G-008"
            elif spec.group == "option" or (spec.group == "ref_instrument" and deriv in {"OPT", "SWO", "WAR"}):
                gap = "G-011"
            elif spec.group == "liquidity":
                gap = "G-010"
            rows.append(_gap_row(
                f"{gap}:{hid}:{external}", "holdings.csv", hid, external, value,
                "NEEDS_REVIEW" if value else "MISSING",
                f"Holding field; requirement: {spec.required} {spec.condition}".strip(),
            ))
    return rows


def prepare_review(
    fund_dir: str | Path, period: str, *, positions: str | Path | None = None,
    orders: str | Path | None = None,
) -> Path:
    """Create or refresh a fund-period review workbook without inventing data."""
    base = Path(fund_dir)
    config_path = base / "fund_config.txt"
    config = parse_config(config_path)
    destination = review_path(base, period)
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing_fields = _read_sheet(destination, "FundFields")
    existing_holding = _read_sheet(destination, "HoldingFields")
    existing_sources = _read_sheet(destination, "Sources")
    existing_approvals = _read_sheet(destination, "Approvals")

    position_path = Path(positions).resolve() if positions else None
    order_path = Path(orders).resolve() if orders else None
    sources: list[dict[str, str]] = []
    for sid, dataset, stype, path in (
        ("POSITIONS", "internal_positions", "INDEPENDENT_POSITIONS", position_path),
        ("ORDERS", "internal_create_redeem", "CREATE_REDEEM", order_path),
    ):
        if path is None:
            continue
        record_count = ""
        if path.is_file() and path.suffix.lower() in {".csv", ".tsv"}:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            with open(path, newline="", encoding="utf-8-sig") as handle:
                record_count = str(sum(1 for _ in csv.reader(handle, delimiter=delimiter)) - 1)
        sources.append({
            "sourceId": sid, "dataset": dataset, "sourceType": stype,
            "sourceSystem": "", "sourcePath": str(path), "sourceAsOf": "",
            "acquiredAt": "", "sha256": _hash(path) if path.is_file() else "",
            "recordCount": record_count, "preparedBy": "", "reviewedBy": "",
            "reviewedAt": "", "status": "PENDING", "comment": "",
        })
    sources = _merge_preserved(sources, existing_sources, lambda row: row.get("sourceId", ""))
    for source in sources:
        source_path = Path(source.get("sourcePath", ""))
        if not source_path.is_file():
            continue
        actual_hash = _hash(source_path)
        recorded_hash = source.get("sha256", "").strip().lower()
        if not recorded_hash:
            source["sha256"] = actual_hash
        elif recorded_hash != actual_hash:
            source["status"] = "PENDING"
            source["comment"] = "File changed after it was recorded; update evidence and re-review."
        if not source.get("recordCount", "") and source_path.suffix.lower() in {".csv", ".tsv"}:
            delimiter = "\t" if source_path.suffix.lower() == ".tsv" else ","
            with open(source_path, newline="", encoding="utf-8-sig") as handle:
                source["recordCount"] = str(max(0, sum(1 for _ in csv.reader(handle, delimiter=delimiter)) - 1))

    generated_fund_rows = _config_rows(config) + _filing_rows()
    if order_path and order_path.is_file():
        flows = aggregate_flows(parse_ap_orders(order_path), period).get(base.name.upper(), {})
        for row in generated_fund_rows:
            field = row.get("fieldName", "")
            if field in flows and not field.endswith("Reinvestment"):
                row["currentValue"] = flows[field]
                row["sourceId"] = "ORDERS"
                row["status"] = "NEEDS_REVIEW"
                row["comment"] = "Calculated from accepted independent create/redeem orders; review required."
    fund_rows = _merge_preserved(generated_fund_rows, existing_fields, _field_key)
    holding_rows = _merge_preserved(
        _holding_review_rows(position_path), existing_holding, _field_key,
    )
    approvals = _merge_preserved([
        {"role": "PREPARER", "name": "", "approvedAt": "", "status": "PENDING", "comment": ""},
        {"role": "REVIEWER", "name": "", "approvedAt": "", "status": "PENDING", "comment": ""},
    ], existing_approvals, lambda row: row.get("role", ""))

    wb = Workbook()
    wb.remove(wb.active)
    summary = wb.create_sheet("Summary")
    summary_rows = [
        ["FUND-PERIOD REVIEW WORKFLOW", ""],
        ["Fund", base.name.upper()],
        ["Period", period],
        ["Current status", "BLOCKED until review-status reports zero blockers"],
        ["Non-negotiable rule", "Do not use U.S. Bank, EagleSTAR, prepared filings, or values derived from them."],
        ["1 - Register evidence", "Complete Sources first. Use the real source system, path, cutoff, preparer, and reviewer."],
        ["2 - Resolve fund fields", "Filter FundFields to MISSING and NEEDS_REVIEW; resolve only from approved independent evidence."],
        ["3 - Resolve holding fields", "Complete the generated HoldingFields exceptions; do not manually recreate the base position population."],
        ["4 - Approve", "Two different people complete PREPARER and REVIEWER on Approvals."],
        ["5 - Check", f"Run: nport review-status {base.name.lower()} {period}"],
        ["6 - Build", f"After zero blockers: nport build {base.name.lower()} {period} --from-review"],
        ["Allowed field decisions", "APPROVED, or NOT_APPLICABLE only when supported with source, reviewer, time, and reason."],
        ["Source helper", "For a manually added source, enter its real path, save, and rerun prepare-review to populate a blank hash/count."],
        ["Truth limitation", "The workbook records evidence and decisions; it does not prove origin if a person copied and relabelled a prohibited value."],
    ]
    for values in summary_rows:
        summary.append(values)
    summary.column_dimensions["A"].width = 25
    summary.column_dimensions["B"].width = 95
    summary.freeze_panes = "A2"
    summary.sheet_view.showGridLines = False
    summary.sheet_view.zoomScale = 90
    for cell in summary[1]:
        cell.fill = PatternFill("solid", fgColor="28465C")
        cell.font = Font(bold=True, color="FFFFFF", size=12)
    for row_cells in summary.iter_rows(min_row=2):
        row_cells[0].font = Font(bold=True, color="28465C")
        for cell in row_cells:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    summary.auto_filter.ref = summary.dimensions
    _write_table(
        wb.create_sheet("GapGuide"),
        ["gapId", "gap", "requiredFiles", "whereToFix", "requiredAction"],
        [dict(zip(["gapId", "gap", "requiredFiles", "whereToFix", "requiredAction"], row)) for row in GAP_GUIDE],
    )
    field_inputs = {
        "proposedValue", "sourceId", "sourceAsOf", "status", "reviewer",
        "reviewedAt", "comment",
    }
    fund_ws = wb.create_sheet("FundFields")
    _write_table(fund_ws, FIELD_HEADERS, fund_rows, editable_headers=field_inputs)
    _add_list_validation(
        fund_ws, "status",
        ["MISSING", "NEEDS_REVIEW", "APPROVED", "NOT_APPLICABLE", "SYSTEM_DERIVED", "SYSTEM_CONTROL"],
    )
    holding_ws = wb.create_sheet("HoldingFields")
    _write_table(holding_ws, FIELD_HEADERS, holding_rows, editable_headers=field_inputs)
    _add_list_validation(
        holding_ws, "status", ["MISSING", "NEEDS_REVIEW", "APPROVED", "NOT_APPLICABLE"],
    )
    source_ws = wb.create_sheet("Sources")
    _write_table(
        source_ws, SOURCE_HEADERS, sources,
        editable_headers=set(SOURCE_HEADERS) - {"sha256"},
    )
    _add_list_validation(source_ws, "status", ["PENDING", "APPROVED", "REJECTED"])
    approval_ws = wb.create_sheet("Approvals")
    _write_table(
        approval_ws, APPROVAL_HEADERS, approvals,
        editable_headers={"name", "approvedAt", "status", "comment"},
    )
    _add_list_validation(approval_ws, "status", ["PENDING", "APPROVED", "REJECTED"])
    _write_table(wb.create_sheet("Reconciliation"),
                 ["check", "status", "actual", "expected", "detail"], [])

    fd, tmp = tempfile.mkstemp(dir=destination.parent, suffix=".xlsx")
    os.close(fd)
    try:
        wb.save(tmp)
        Path(tmp).replace(destination)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return destination


def _resolved(row: dict[str, str]) -> str:
    return row.get("proposedValue", "").strip() or row.get("currentValue", "").strip()


def _approved(row: dict[str, str]) -> bool:
    return row.get("status", "").strip().upper() in {"APPROVED", "SYSTEM_DERIVED", "SYSTEM_CONTROL"}


def _source_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("sourceId", ""): row for row in rows if row.get("sourceId")}


def _block(code: str, technical: str, plain: str) -> Finding:
    return Finding(code, "BLOCKER", technical, plain)


def _validate_sources(
    sources: list[dict[str, str]], used: set[str], period: str,
) -> list[Finding]:
    blockers: list[Finding] = []
    by_id = _source_map(sources)
    ids = [row.get("sourceId", "") for row in sources if row.get("sourceId", "")]
    for sid in sorted({sid for sid in ids if ids.count(sid) > 1}):
        blockers.append(_block("REVIEW_SOURCE_DUPLICATE", f"sourceId {sid!r} occurs more than once",
                               f"Source ID {sid!r} is duplicated."))
    expected_as_of = report_date_for_period(period).isoformat()
    for sid in sorted(used):
        source = by_id.get(sid)
        if source is None:
            blockers.append(_block("REVIEW_SOURCE_MISSING", f"sourceId {sid!r} is absent",
                                   "A reviewed value has no source row."))
            continue
        if source.get("status", "").upper() != "APPROVED":
            blockers.append(_block("REVIEW_SOURCE_UNAPPROVED", f"{sid}: status is not APPROVED",
                                   f"Source {sid!r} has not been approved."))
        values = [source.get(key, "") for key in ("dataset", "sourceType", "sourceSystem", "sourcePath")]
        if _is_prohibited_source(*values):
            blockers.append(_block("REVIEW_SOURCE_PROHIBITED", f"{sid}: prohibited U.S. Bank/admin source",
                                   f"Source {sid!r} is comparison-only."))
            continue
        path = Path(source.get("sourcePath", ""))
        if not path.is_file():
            blockers.append(_block("REVIEW_SOURCE_FILE", f"{sid}: {path} does not exist",
                                   f"Source file for {sid!r} cannot be found."))
            continue
        actual = _hash(path)
        if actual != source.get("sha256", "").lower():
            blockers.append(_block("REVIEW_SOURCE_HASH", f"{sid}: SHA-256 changed",
                                   f"Source {sid!r} changed after review."))
        for key in ("dataset", "sourceType", "sourceSystem", "sourceAsOf", "acquiredAt", "recordCount",
                    "preparedBy", "reviewedBy", "reviewedAt"):
            if not source.get(key, "").strip():
                blockers.append(_block("REVIEW_SOURCE_EVIDENCE", f"{sid}: {key} is blank",
                                       f"Source {sid!r} lacks complete review evidence."))
        if source.get("sourceAsOf", "").strip() and source["sourceAsOf"].strip() != expected_as_of:
            blockers.append(_block(
                "REVIEW_SOURCE_ASOF",
                f"{sid}: sourceAsOf={source['sourceAsOf']!r}; expected {expected_as_of!r}",
                f"Source {sid!r} is not aligned to the filing cutoff.",
            ))
        for key in ("acquiredAt", "reviewedAt"):
            raw_timestamp = source.get(key, "").strip()
            if raw_timestamp:
                try:
                    datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                except ValueError:
                    blockers.append(_block("REVIEW_SOURCE_TIME", f"{sid}: {key} is not ISO-8601",
                                           f"Source {sid!r} has an invalid {key} timestamp."))
        try:
            if int(source.get("recordCount", "")) < 0:
                raise ValueError
        except ValueError:
            blockers.append(_block("REVIEW_SOURCE_COUNT", f"{sid}: invalid recordCount",
                                   f"Source {sid!r} needs a non-negative record count."))
        if source.get("preparedBy", "").strip() and source.get("preparedBy", "").strip() == source.get("reviewedBy", "").strip():
            blockers.append(_block("REVIEW_SOURCE_SEPARATION", f"{sid}: preparer and reviewer are the same",
                                   f"Source {sid!r} needs a second-person review."))
    return blockers


def _apply_config_rows(config: FundConfig, rows: list[dict[str, str]]) -> FundConfig:
    values = {}
    for row in rows:
        external = row.get("fieldName", "")
        attr = _CONFIG_KEY_MAP.get(external)
        if attr and _approved(row):
            values[attr] = _resolved(row)
    return replace(config, **values)


def _filing_from_rows(rows: list[dict[str, str]], config: FundConfig, ticker: str, period: str) -> FilingData:
    values: dict[str, str] = {field.name: "" for field in fields(FilingData)}
    for row in rows:
        external = row.get("fieldName", "")
        attr = _FILING_KEY_MAP.get(external)
        if attr and _approved(row) and external not in SYSTEM_DERIVED_FILING:
            values[attr] = _resolved(row)
    context = derive_context_from_config(config, ticker, period, "fund_config.txt")
    return apply_context(FilingData(**values), context)


def _holding_objects(
    positions_path: Path, rows: list[dict[str, str]], default_source: str,
) -> tuple[list[Holding], list[dict[str, str]]]:
    ids, raw = _raw_positions(positions_path)
    overrides = {
        (row.get("recordKey", ""), row.get("fieldName", "")): _resolved(row)
        for row in rows if _approved(row)
    }
    external_fields = list(_HOLDINGS_KEY_MAP)
    provenance: list[dict[str, str]] = []
    holdings = []
    row_by_key = {(row.get("recordKey", ""), row.get("fieldName", "")): row for row in rows}
    for hid, source_row in zip(ids, raw):
        mapped: dict[str, str] = {}
        for external, attr in _HOLDINGS_KEY_MAP.items():
            value = overrides.get((hid, external), source_row.get(external, ""))
            mapped[attr] = value
            review_row = row_by_key.get((hid, external))
            provenance.append({
                "targetFile": "holdings.csv", "recordKey": hid, "fieldName": external,
                "value": value, "sourceId": (
                    review_row.get("sourceId", "") if review_row and _approved(review_row)
                    else default_source
                ),
                "method": "HUMAN_REVIEW" if review_row and _approved(review_row) else "SOURCE_FILE",
                "reviewer": review_row.get("reviewer", "") if review_row else "",
                "reviewedAt": review_row.get("reviewedAt", "") if review_row else "",
            })
        holdings.append(Holding(**mapped))
    return holdings, provenance


def _approval_blockers(rows: list[dict[str, str]]) -> list[Finding]:
    blockers = []
    by_role = {row.get("role", "").upper(): row for row in rows}
    for role in ("PREPARER", "REVIEWER"):
        row = by_role.get(role)
        if not row or row.get("status", "").upper() != "APPROVED" or not row.get("name") or not row.get("approvedAt"):
            blockers.append(_block("REVIEW_APPROVAL", f"{role} approval is incomplete",
                                   f"The {role.lower()} approval is missing."))
        elif row.get("approvedAt"):
            try:
                datetime.fromisoformat(row["approvedAt"].replace("Z", "+00:00"))
            except ValueError:
                blockers.append(_block("REVIEW_APPROVAL_TIME", f"{role} approvedAt is not ISO-8601",
                                       f"The {role.lower()} approval time is invalid."))
    if by_role.get("PREPARER", {}).get("name") and \
            by_role.get("PREPARER", {}).get("name") == by_role.get("REVIEWER", {}).get("name"):
        blockers.append(_block("REVIEW_SEPARATION", "preparer and reviewer are the same person",
                               "A second person must approve the review."))
    return blockers


def _field_blockers(rows: list[dict[str, str]], *, optional: set[str] | None = None) -> list[Finding]:
    optional = optional or set()
    blockers = []
    for row in rows:
        field = row.get("fieldName", "")
        status = row.get("status", "").upper()
        if status in {"SYSTEM_DERIVED", "SYSTEM_CONTROL"}:
            continue
        if field in optional and not _resolved(row):
            continue
        if status == "NOT_APPLICABLE":
            if not row.get("sourceId", "") or not row.get("reviewer", "") or \
                    not row.get("reviewedAt", "") or not row.get("comment", ""):
                blockers.append(_block(
                    "REVIEW_NA_EVIDENCE",
                    f"{row.get('targetFile')}:{row.get('recordKey')}:{field} has incomplete NOT_APPLICABLE evidence",
                    f"{field} is marked not applicable but lacks source, reviewer, time, or reason.",
                ))
            continue
        if not _approved(row) or not _resolved(row):
            blockers.append(_block(row.get("gapId", "REVIEW_FIELD"),
                                   f"{row.get('targetFile')}:{row.get('recordKey')}:{field} is unresolved",
                                   f"{field} still needs a supported value or approved disposition."))
        elif not row.get("sourceId", ""):
            blockers.append(_block("REVIEW_FIELD_SOURCE", f"{field} has no sourceId",
                                   f"{field} has a value but no traceable source."))
        elif not row.get("reviewer", "") or not row.get("reviewedAt", ""):
            blockers.append(_block("REVIEW_FIELD_REVIEW", f"{field} lacks reviewer/time",
                                   f"{field} has not been fully reviewed."))
        elif not row.get("sourceAsOf", ""):
            blockers.append(_block("REVIEW_FIELD_ASOF", f"{field} lacks sourceAsOf",
                                   f"{field} has no recorded source cutoff."))
        else:
            try:
                datetime.fromisoformat(row["reviewedAt"].replace("Z", "+00:00"))
            except ValueError:
                blockers.append(_block("REVIEW_FIELD_TIME", f"{field} reviewedAt is not ISO-8601",
                                       f"{field} has an invalid review timestamp."))
    return blockers


def _field_source_consistency(rows: list[dict[str, str]], sources: list[dict[str, str]]) -> list[Finding]:
    blockers: list[Finding] = []
    by_id = _source_map(sources)
    for row in rows:
        if not (_approved(row) or row.get("status", "").upper() == "NOT_APPLICABLE"):
            continue
        sid = row.get("sourceId", "")
        if not sid:
            continue
        source = by_id.get(sid)
        if source and row.get("sourceAsOf", "").strip() != source.get("sourceAsOf", "").strip():
            blockers.append(_block(
                "REVIEW_FIELD_SOURCE_ASOF",
                f"{row.get('targetFile')}:{row.get('recordKey')}:{row.get('fieldName')} sourceAsOf does not match {sid}",
                f"{row.get('fieldName')} does not use the same cutoff as source {sid!r}.",
            ))
    return blockers


def _positions_source(sources: list[dict[str, str]]) -> dict[str, str] | None:
    return next((row for row in sources if row.get("dataset") == "internal_positions"), None)


def evaluate_review(fund_dir: str | Path, period: str) -> dict:
    """Return resolved models, blockers, provenance, and reconciliation without writing."""
    base = Path(fund_dir)
    ticker = base.name.upper()
    workbook = review_path(base, period)
    config = parse_config(base / "fund_config.txt")
    fund_rows = _read_sheet(workbook, "FundFields")
    holding_rows = _read_sheet(workbook, "HoldingFields")
    sources = _read_sheet(workbook, "Sources")
    approvals = _read_sheet(workbook, "Approvals")
    blockers: list[Finding] = []
    if not workbook.is_file():
        blockers.append(_block("REVIEW_WORKBOOK", f"{workbook} does not exist",
                               "The fund-level human-review workbook has not been created."))
        return {"blockers": blockers}

    blockers.extend(_approval_blockers(approvals))
    # Optional/conditional filing sections still need an explicit reviewed
    # disposition. Only an open-ended policy date and relative-VaR identifiers
    # that are inapplicable under the approved regime may remain blank.
    blockers.extend(_field_blockers(
        fund_rows, optional={"policyEffectiveTo", "nameDesignatedIndex", "indexIdentifier"}
    ))
    blockers.extend(_field_blockers(holding_rows, optional={"isin", "ticker"}))
    blockers.extend(_field_source_consistency(fund_rows + holding_rows, sources))

    used_sources = {
        row.get("sourceId", "") for row in fund_rows + holding_rows
        if (_approved(row) or row.get("status", "").upper() == "NOT_APPLICABLE")
        and row.get("sourceId", "")
    }
    position_source = _positions_source(sources)
    if position_source:
        used_sources.add(position_source.get("sourceId", ""))
    else:
        blockers.append(_block("G-001", "no internal_positions source is present",
                               "An independent position population has not been supplied."))
    blockers.extend(_validate_sources(sources, used_sources, period))

    try:
        config = _apply_config_rows(config, fund_rows)
        approved_datasets = sorted({
            source.get("dataset", "") for source in sources
            if source.get("status", "").upper() == "APPROVED" and source.get("dataset", "")
        })
        config = replace(config, required_sources=";".join(approved_datasets))
        filing = _filing_from_rows(fund_rows, config, ticker, period)
    except ValueError as exc:
        blockers.append(_block("G-004", str(exc), "The approved fund policy is incomplete or invalid."))
        filing = None

    holdings: list[Holding] = []
    provenance: list[dict[str, str]] = []
    if position_source and Path(position_source.get("sourcePath", "")).is_file():
        try:
            holdings, provenance = _holding_objects(
                Path(position_source["sourcePath"]), holding_rows,
                position_source.get("sourceId", "POSITIONS"),
            )
        except (OSError, TypeError, ValueError) as exc:
            blockers.append(_block("G-001", f"position import failed: {exc}",
                                   "The independent position file is invalid."))

    reconciliation: list[dict[str, str]] = []
    if filing and holdings:
        errors, warnings = validate_all(config, filing, holdings)
        for message in errors:
            blockers.append(_block("INPUT_VALIDATION", message, "A canonical filing value is invalid."))
        try:
            equation = float(filing.tot_assets) - float(filing.tot_liabs) - float(filing.net_assets)
            status = "PASS" if abs(equation) <= 1.0 else "BLOCKER"
            reconciliation.append({
                "check": "NAV equation", "status": status, "actual": f"{equation:.2f}",
                "expected": "0.00", "detail": "totAssets - totLiabs - netAssets",
            })
            if status == "BLOCKER":
                blockers.append(_block("G-012_NAV", f"NAV equation difference {equation:.2f}",
                                       "Assets, liabilities, and net assets do not reconcile."))
        except ValueError:
            pass
        expected_count = position_source.get("recordCount", "") if position_source else ""
        count_status = "PASS" if expected_count == str(len(holdings)) else "BLOCKER"
        reconciliation.append({
            "check": "Position count", "status": count_status, "actual": str(len(holdings)),
            "expected": expected_count, "detail": "Independent positions imported",
        })
        if count_status == "BLOCKER":
            blockers.append(_block("G-012_COUNT",
                                   f"position count {len(holdings)} does not match source count {expected_count!r}",
                                   "The imported position population does not match its source control count."))
        for row in fund_rows:
            if _approved(row) and row.get("fieldName") in _CONFIG_KEY_MAP:
                provenance.append({
                    "targetFile": "fund_config.txt", "recordKey": "FUND",
                    "fieldName": row.get("fieldName", ""), "value": _resolved(row),
                    "sourceId": row.get("sourceId", ""), "method": "HUMAN_REVIEW",
                    "reviewer": row.get("reviewer", ""), "reviewedAt": row.get("reviewedAt", ""),
                })
            elif _approved(row) and row.get("fieldName") in _FILING_KEY_MAP:
                provenance.append({
                    "targetFile": "filing_data.txt", "recordKey": "FUND",
                    "fieldName": row.get("fieldName", ""), "value": _resolved(row),
                    "sourceId": row.get("sourceId", ""), "method": "HUMAN_REVIEW",
                    "reviewer": row.get("reviewer", ""), "reviewedAt": row.get("reviewedAt", ""),
                })

    return {
        "workbook": workbook, "config": config, "filing": filing, "holdings": holdings,
        "sources": sources, "approvals": approvals, "blockers": blockers,
        "provenance": provenance, "reconciliation": reconciliation,
    }


def _write_kv(path: Path, mapping: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in mapping.items()), encoding="utf-8")


def _write_holdings(path: Path, holdings: list[Holding]) -> None:
    field_to_external = {value: key for key, value in _HOLDINGS_KEY_MAP.items()}
    headers = [field_to_external[field.name] for field in fields(Holding)]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for holding in holdings:
            raw = asdict(holding)
            writer.writerow({field_to_external[key]: value for key, value in raw.items()})


def finalize_review(
    fund_dir: str | Path, period: str, *, output_root: str | Path = "data/builds",
    run_id: str | None = None,
) -> Path:
    """Write a clean, versioned canonical bundle only when review has no blockers."""
    result = evaluate_review(fund_dir, period)
    if result["blockers"]:
        raise ReviewBlocked(result["blockers"])
    ticker = Path(fund_dir).name.upper()
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = Path(output_root) / ticker.lower() / period / run_id
    destination.mkdir(parents=True, exist_ok=False)

    config: FundConfig = result["config"]
    filing: FilingData = result["filing"]
    config_inverse = {value: key for key, value in _CONFIG_KEY_MAP.items()}
    filing_inverse = {value: key for key, value in _FILING_KEY_MAP.items()}
    _write_kv(destination / "fund_config.txt", {
        config_inverse[field.name]: str(getattr(config, field.name))
        for field in fields(FundConfig) if field.name in config_inverse
    })
    _write_kv(destination / "filing_data.txt", {
        filing_inverse[field.name]: str(getattr(filing, field.name))
        for field in fields(FilingData) if field.name in filing_inverse
    })
    _write_holdings(destination / "holdings.csv", result["holdings"])

    with open(destination / "source_manifest.csv", "w", newline="", encoding="utf-8") as handle:
        headers = ["dataset", "source_system", "source_path", "as_of", "acquired_at",
                   "sha256", "record_count", "approved_by"]
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for source in result["sources"]:
            if source.get("status", "").upper() == "APPROVED":
                writer.writerow({
                    "dataset": source.get("dataset", ""),
                    "source_system": source.get("sourceSystem", ""),
                    "source_path": source.get("sourcePath", ""),
                    "as_of": source.get("sourceAsOf", ""),
                    "acquired_at": source.get("acquiredAt", ""),
                    "sha256": source.get("sha256", ""),
                    "record_count": source.get("recordCount", ""),
                    "approved_by": source.get("reviewedBy", ""),
                })

    for filename, rows, headers in (
        ("field_provenance.csv", result["provenance"],
         ["targetFile", "recordKey", "fieldName", "value", "sourceId", "method", "reviewer", "reviewedAt"]),
        ("reconciliation.csv", result["reconciliation"],
         ["check", "status", "actual", "expected", "detail"]),
    ):
        with open(destination / filename, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    receipt = {
        "fund": ticker, "period": period, "runId": run_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "reviewWorkbook": str(result["workbook"]),
        "reviewWorkbookSha256": _hash(result["workbook"]),
        "approvals": result["approvals"], "blockers": [],
        "outputs": {},
        "originControlLimitation": (
            "Local hashes and dual review prevent accidental/exact-file reuse; local code "
            "cannot prove that a person did not manually copy a prohibited value."
        ),
    }
    for name in ("fund_config.txt", "filing_data.txt", "holdings.csv",
                 "source_manifest.csv", "field_provenance.csv", "reconciliation.csv"):
        receipt["outputs"][name] = _hash(destination / name)
    (destination / "review_receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return destination
