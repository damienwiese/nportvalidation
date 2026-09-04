"""In-house fund policy and fiscal-calendar controls.

Reference/administrator filings are intentionally not accepted as a policy
source.  They may be compared after generation, but cannot supply a production
field through this module.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from nport.models import FilingData, FundConfig
from nport.source_policy import is_prohibited_source

DERIVATIVES_REGIMES = {"NONE", "LIMITED", "VAR_RELATIVE", "VAR_ABSOLUTE"}


@dataclass(frozen=True)
class FundPolicy:
    ticker: str
    fiscal_year_end_mmdd: str
    derivatives_regime: str
    liquidity_required: bool
    cash_b2f_required: bool
    active_from: date
    active_to: date | None
    approved_by: str = ""
    approved_at: datetime | None = None
    source_system: str = ""
    source_ref: str = ""
    required_sources: tuple[str, ...] = ()

    def is_active(self, report_date: date) -> bool:
        return self.active_from <= report_date and (
            self.active_to is None or report_date <= self.active_to
        )


@dataclass(frozen=True)
class FilingContext:
    report_date: date
    fiscal_year_end: date
    submission_type: str
    is_confidential: bool
    policy: FundPolicy


def _parse_bool(value: str, field: str) -> bool:
    normalized = value.strip().upper()
    if normalized not in {"Y", "N", "TRUE", "FALSE"}:
        raise ValueError(f"{field} must be Y/N or true/false, got {value!r}")
    return normalized in {"Y", "TRUE"}


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD, got {value!r}") from exc


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"approved_at must be ISO-8601, got {value!r}") from exc


def _validate_mmdd(value: str) -> tuple[int, int]:
    try:
        month, day = (int(part) for part in value.split("-"))
        date(2000, month, day)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"fiscal_year_end_mmdd must be MM-DD, got {value!r}") from exc
    return month, day


def policy_from_config(config: FundConfig, ticker: str, source_ref: str | Path) -> FundPolicy:
    """Load approved policy from the existing per-fund configuration.

    No business value is inferred. Every policy field required for release must
    be explicitly present in ``fund_config.txt`` and supported by an internal
    source reference.
    """
    missing = [
        name for name, value in (
            ("fiscalYearEndMMDD", config.fiscal_year_end_mmdd),
            ("derivativesRegimePolicy", config.derivatives_regime_policy),
            ("liquidityRequired", config.liquidity_required),
            ("cashB2fRequired", config.cash_b2f_required),
            ("policyEffectiveFrom", config.policy_effective_from),
        ) if not value.strip()
    ]
    if missing:
        raise ValueError(
            "fund_config.txt is missing approved policy fields: " + ", ".join(missing)
        )
    if is_prohibited_source(str(source_ref)):
        raise ValueError("prohibited custody/prepared-filing data cannot approve fund policy")
    regime = config.derivatives_regime_policy.strip().upper()
    if regime not in DERIVATIVES_REGIMES:
        raise ValueError(f"invalid derivativesRegimePolicy {regime!r}")
    _validate_mmdd(config.fiscal_year_end_mmdd)
    return FundPolicy(
        ticker=ticker.upper(),
        fiscal_year_end_mmdd=config.fiscal_year_end_mmdd.strip(),
        derivatives_regime=regime,
        liquidity_required=_parse_bool(config.liquidity_required, "liquidityRequired"),
        cash_b2f_required=_parse_bool(config.cash_b2f_required, "cashB2fRequired"),
        active_from=_parse_date(config.policy_effective_from, "policyEffectiveFrom"),
        active_to=(
            _parse_date(config.policy_effective_to, "policyEffectiveTo")
            if config.policy_effective_to.strip() else None
        ),
        approved_by=config.policy_approved_by.strip(),
        approved_at=(
            _parse_datetime(config.policy_approved_at.strip())
            if config.policy_approved_at.strip() else None
        ),
        source_system="Internal fund configuration",
        source_ref=str(source_ref),
        required_sources=tuple(
            value.strip() for value in config.required_sources.split(";") if value.strip()
        ),
    )


def derive_context_from_config(
    config: FundConfig, ticker: str, period: str, source_ref: str | Path
) -> FilingContext:
    report_date = report_date_for_period(period)
    policy = policy_from_config(config, ticker, source_ref)
    if not policy.is_active(report_date):
        raise ValueError(
            f"fund policy is not effective for {ticker.upper()} on {report_date.isoformat()}"
        )
    submission_type = submission_type_for(report_date, policy.fiscal_year_end_mmdd)
    return FilingContext(
        report_date=report_date,
        fiscal_year_end=fiscal_year_end_on_or_after(report_date, policy.fiscal_year_end_mmdd),
        submission_type=submission_type,
        is_confidential=submission_type == "NPORT-NP",
        policy=policy,
    )


def report_date_for_period(period: str) -> date:
    if (
        not isinstance(period, str)
        or len(period) != 7
        or period[4] != "-"
        or not period.isascii()
        or not (period[:4] + period[5:]).isdigit()
    ):
        raise ValueError(f"period must be YYYY-MM, got {period!r}")
    try:
        year, month = (int(part) for part in period.split("-"))
        return date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"period must be YYYY-MM, got {period!r}") from exc


def fiscal_year_end_on_or_after(report_date: date, mmdd: str) -> date:
    month, day = _validate_mmdd(mmdd)
    # Feb-29 policies use the last valid day in non-leap years.
    day_this_year = min(day, monthrange(report_date.year, month)[1])
    candidate = date(report_date.year, month, day_this_year)
    if candidate < report_date:
        next_day = min(day, monthrange(report_date.year + 1, month)[1])
        candidate = date(report_date.year + 1, month, next_day)
    return candidate


def submission_type_for(report_date: date, fiscal_year_end_mmdd: str) -> str:
    fiscal_month, _ = _validate_mmdd(fiscal_year_end_mmdd)
    fiscal_quarter_end_months = {
        ((fiscal_month - offset - 1) % 12) + 1 for offset in (0, 3, 6, 9)
    }
    return "NPORT-P" if report_date.month in fiscal_quarter_end_months else "NPORT-NP"


def apply_context(filing: FilingData, context: FilingContext) -> FilingData:
    """Replace operator-entered calendar/applicability values with policy output."""
    return replace(
        filing,
        submission_type=context.submission_type,
        rep_pd_end=context.fiscal_year_end.isoformat(),
        rep_pd_date=context.report_date.isoformat(),
        derivatives_regime=context.policy.derivatives_regime,
    )
