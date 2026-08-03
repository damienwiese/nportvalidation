"""Fail-closed, in-house preflight and release evidence controls."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from nport.models import FilingData, Holding
from nport.policy import FilingContext


_PROHIBITED_SOURCE_TOKENS = (
    "us bank", "u.s. bank", "usbank", "eaglestar",
    "data/custodian", "data\\custodian", "data/fund_accounting",
    "data\\fund_accounting", "takeout", "nportimplementation",
    "n-port comparison", "nport comparison", "administrator reference",
    "reference filing", "filing comparison", "prepared n-port",
    "telegram desktop", "support_final", "consolidated reports_final",
    "fwdcorgitrust", "founder-led 2x daily etf", "corgi 4.30.2026",
    "data/master", "data\\master", "data/funds", "data\\funds",
    "data/humanreview", "data\\humanreview", "output/", "output\\",
)


def _is_prohibited_source(*values: str) -> bool:
    """Identify U.S. Bank-delivered and administrator/reference inputs."""
    source = " | ".join(values).strip().lower()
    return any(token in source for token in _PROHIBITED_SOURCE_TOKENS)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    technical: str
    plain: str


@dataclass(frozen=True)
class SourceEvidence:
    dataset: str
    source_system: str
    source_path: str
    as_of: date
    acquired_at: datetime
    sha256: str
    record_count: int
    approved_by: str


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_source_manifest(path: str | Path) -> dict[str, SourceEvidence]:
    manifest = Path(path)
    required = {
        "dataset", "source_system", "source_path", "as_of", "acquired_at",
        "sha256", "record_count", "approved_by",
    }
    evidence: dict[str, SourceEvidence] = {}
    with open(manifest, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{manifest}: missing source-manifest columns {sorted(missing)}")
        for rownum, row in enumerate(reader, 2):
            source = row["source_system"]
            if _is_prohibited_source(row["dataset"], source, row["source_path"]):
                raise ValueError(
                    f"{manifest}:{rownum}: U.S. Bank/admin comparison data cannot feed the "
                    "in-house pipeline (dataset, source_system, and source_path are all checked)"
                )
            dataset = row["dataset"].strip()
            if not dataset or dataset in evidence:
                raise ValueError(f"{manifest}:{rownum}: dataset must be unique and non-empty")
            evidence[dataset] = SourceEvidence(
                dataset=dataset,
                source_system=row["source_system"].strip(),
                source_path=row["source_path"].strip(),
                as_of=date.fromisoformat(row["as_of"].strip()),
                acquired_at=datetime.fromisoformat(row["acquired_at"].strip().replace("Z", "+00:00")),
                sha256=row["sha256"].strip().lower(),
                record_count=int(row["record_count"]),
                approved_by=row["approved_by"].strip(),
            )
    return evidence


def run_preflight(
    context: FilingContext,
    filing: FilingData,
    holdings: list[Holding],
    source_manifest: str | Path | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    expected = {
        "repPdEnd": context.fiscal_year_end.isoformat(),
        "repPdDate": context.report_date.isoformat(),
        "submissionType": context.submission_type,
        "derivativesRegime": context.policy.derivatives_regime,
    }
    actual = {
        "repPdEnd": filing.rep_pd_end,
        "repPdDate": filing.rep_pd_date,
        "submissionType": filing.submission_type,
        "derivativesRegime": filing.derivatives_regime,
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            findings.append(Finding(
                f"POLICY_{field.upper()}", "BLOCKER",
                f"{field}={actual[field]!r}; approved policy derives {expected_value!r}.",
                f"The filing's {field} does not match the approved internal calendar/policy.",
            ))

    regime = context.policy.derivatives_regime
    if regime == "LIMITED" and not all((
        filing.deriv_exposure_pct, filing.deriv_currency_exposure_pct,
        filing.deriv_interest_rate_exposure_pct, filing.deriv_days_in_excess,
    )):
        findings.append(Finding(
            "COVERAGE_B9", "BLOCKER", "Rule 18f-4 LIMITED policy requires complete Item B.9.",
            "The fund is classified as a limited derivatives user, but its exposure section is incomplete.",
        ))
    if regime.startswith("VAR_") and not all((
        filing.median_daily_var_pct, filing.backtesting_exceptions,
    )):
        findings.append(Finding(
            "COVERAGE_B10", "BLOCKER", "VaR policy requires complete Item B.10.",
            "The internal VaR calculation and backtesting result are missing.",
        ))
    if regime == "VAR_RELATIVE" and not all((
        filing.name_designated_index, filing.index_identifier, filing.median_var_ratio_pct,
    )):
        findings.append(Finding(
            "COVERAGE_B10_RELATIVE", "BLOCKER",
            "Relative VaR requires designated portfolio identity and median VaR ratio.",
            "The relative-VaR benchmark evidence is incomplete.",
        ))
    if context.policy.cash_b2f_required and not filing.cash_not_reported_in_c_or_d:
        findings.append(Finding(
            "COVERAGE_B2F", "BLOCKER", "Policy requires Item B.2.f from internal cash records.",
            "Cash not represented in the holdings schedule has not been supplied.",
        ))
    missing_liquidity = sum(not h.liquidity_classification_json.strip() for h in holdings)
    if context.policy.liquidity_required and missing_liquidity:
        findings.append(Finding(
            "COVERAGE_C7", "BLOCKER",
            f"{missing_liquidity}/{len(holdings)} positions lack internal C.7 classifications.",
            f"Liquidity classification is missing for {missing_liquidity} positions.",
        ))

    if source_manifest is None:
        findings.append(Finding(
            "EVIDENCE_MANIFEST", "BLOCKER", "No source-evidence manifest was supplied.",
            "The run cannot prove where its inputs came from or when they were captured.",
        ))
        return findings

    try:
        evidence = load_source_manifest(source_manifest)
    except (OSError, ValueError) as exc:
        findings.append(Finding(
            "EVIDENCE_MANIFEST", "BLOCKER", str(exc),
            "The source-evidence manifest is missing or invalid.",
        ))
        return findings

    for dataset in context.policy.required_sources:
        item = evidence.get(dataset)
        if item is None:
            findings.append(Finding(
                "EVIDENCE_SOURCE_MISSING", "BLOCKER", f"Required dataset {dataset!r} is absent.",
                f"Required internal source {dataset!r} was not delivered.",
            ))
            continue
        source_path = Path(item.source_path)
        if not source_path.is_file():
            findings.append(Finding(
                "EVIDENCE_FILE_MISSING", "BLOCKER", f"{dataset}: {source_path} does not exist.",
                f"The recorded file for {dataset!r} cannot be found.",
            ))
        elif sha256_file(source_path) != item.sha256:
            findings.append(Finding(
                "EVIDENCE_HASH", "BLOCKER", f"{dataset}: SHA-256 does not match the manifest.",
                f"The {dataset!r} file changed after it was recorded.",
            ))
        if item.as_of != context.report_date:
            findings.append(Finding(
                "EVIDENCE_ASOF", "BLOCKER",
                f"{dataset}: as_of={item.as_of}, expected {context.report_date}.",
                f"The {dataset!r} input is not aligned to the filing date.",
            ))
        if not item.approved_by:
            findings.append(Finding(
                "EVIDENCE_APPROVAL", "BLOCKER", f"{dataset}: approved_by is empty.",
                f"The {dataset!r} input has no recorded internal approval.",
            ))
    return findings


def write_release_manifest(
    path: str | Path,
    *,
    ticker: str,
    period: str,
    context: FilingContext,
    xml_path: str | Path,
    input_paths: list[str | Path],
    xsd_version: str,
    findings: list[Finding],
    live_test_flag: str,
) -> None:
    """Write the immutable facts needed to reproduce a generated artifact."""
    destination = Path(path)
    payload = {
        "ticker": ticker.upper(),
        "period": period,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "registry": str(context.policy.source_ref),
            "approved_by": context.policy.approved_by,
            "approved_at": context.policy.approved_at.isoformat(),
            "fiscal_year_end": context.fiscal_year_end.isoformat(),
            "submission_type": context.submission_type,
            "derivatives_regime": context.policy.derivatives_regime,
        },
        "schema_version": xsd_version,
        "environment": live_test_flag,
        "xml": {"path": str(xml_path), "sha256": sha256_file(xml_path)},
        "inputs": [
            {"path": str(item), "sha256": sha256_file(item)} for item in input_paths
            if Path(item).is_file()
        ],
        "preflight": [asdict(finding) for finding in findings],
        "release_eligible": (
            live_test_flag == "LIVE"
            and not any(finding.severity == "BLOCKER" for finding in findings)
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
