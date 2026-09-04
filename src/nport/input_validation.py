"""Input validation for N-PORT filing data.

Validates field formats, value ranges, and cross-field consistency
before XML generation. All format rules derived from SEC N-PORT XSD v1.13.
"""

import json
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from nport.models import FilingData, FundConfig, Holding
from nport.schema import (
    DEBT_ASSET_CATEGORIES,
    DEBT_FIELD_NAMES,
    DERIVATIVE_FIELD_NAMES,
    get_allowed_derivative_fields,
)

NAV_EQUATION_TOLERANCE = Decimal("0.02")
PCT_TIE_MINIMUM_TOLERANCE = Decimal("0.5")
PCT_TIE_PER_HOLDING_TOLERANCE = Decimal("0.005")
LIQUIDITY_PCT_TOLERANCE = Decimal("0.01")

# ── Patterns from the XSD ─────────────────────────────────

_CIK_RE = re.compile(r"^\d{1,10}$")
_LEI_RE = re.compile(r"^([0-9A-Z]{20}|N/A)$")
_CUSIP_RE = re.compile(r"^([0-9A-HJ-NP-Z]{5}[0-9A-HJ-NP-Z#*@]{3}[0-9]|N/A|000000000)$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{10}$")
_SERIES_ID_RE = re.compile(r"^[Ss]\d{9}$")
_CLASS_ID_RE = re.compile(r"^[Cc]\d{9}$")
_FILE_NUMBER_RE = re.compile(r"^\d{3}-\d{5}$")
_YN_RE = re.compile(r"^[YN]$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_NONNEGATIVE_INTEGER_5_RE = re.compile(r"^\d{1,5}$")

_VALID_SUBMISSION_TYPES = {"NPORT-P", "NPORT-NP", "NPORT-P/A", "NPORT-NP/A"}
_VALID_UNITS = {"NS", "PA", "NC", "OU"}
_VALID_ASSET_CATS = {
    "STIV", "RA", "EC", "EP", "DBT", "DCO", "DCR", "DE", "DFE",
    "DIR", "DO", "SN", "LON", "ABS-MBS", "ABS-APCP", "ABS-CBDO",
    "ABS-O", "COMM", "RE", "OTHER",
}
_VALID_ISSUER_CATS = {"CORP", "UST", "USGA", "USGSE", "MUN", "NUSS", "PF", "RF", "OTHER"}
_VALID_PAYOFF_PROFILES = {"Long", "Short", "N/A"}
_VALID_FAIR_VAL_LEVELS = {"1", "2", "3", "N/A"}

# Derivative / debt enums
_VALID_DERIV_CATS = {"FWD", "FUT", "SWP", "OPT", "SWO", "WAR", "OTH"}
_VALID_COUPON_KINDS = {"Fixed", "Floating", "Variable", "None"}
_VALID_PUT_CALL = {"Put", "Call"}
_VALID_WRITTEN_PUR = {"Written", "Purchased"}
_VALID_FIXED_FLOATING = {"Fixed", "Floating", "Other"}
_VALID_REF_INST_TYPES = {"indexBasket", "otherRefInst"}
_VALID_FLOATING_DATE_UNITS = {"Day", "Month", "Year"}

_REFERENCE_DETAIL_FIELDS = {
    "ref_index_name", "ref_index_identifier", "ref_issuer_name", "ref_issue_title",
    "ref_cusip", "ref_isin", "ref_ticker",
}
_REFERENCE_BRANCH_FIELDS = {
    "indexBasket": {"ref_index_name", "ref_index_identifier"},
    "otherRefInst": {
        "ref_issuer_name", "ref_issue_title", "ref_cusip", "ref_isin", "ref_ticker",
    },
}
_RECEIVE_LEG_FIELDS = {
    "rec_fixed_rt", "rec_floating_rt_index", "rec_floating_rt_spread",
    "rec_pmnt_amt", "rec_cur_cd", "rec_rate_tenor", "rec_rate_unit",
    "rec_reset_dt", "rec_reset_unit", "rec_desc",
}
_RECEIVE_BRANCH_FIELDS = {
    "Fixed": {"rec_fixed_rt", "rec_pmnt_amt", "rec_cur_cd"},
    "Floating": {
        "rec_floating_rt_index", "rec_floating_rt_spread", "rec_pmnt_amt",
        "rec_cur_cd", "rec_rate_tenor", "rec_rate_unit", "rec_reset_dt",
        "rec_reset_unit",
    },
    "Other": {"rec_desc"},
}
_PAYMENT_LEG_FIELDS = {
    "pmnt_fixed_rt", "pmnt_floating_rt_index", "pmnt_floating_rt_spread",
    "pmnt_pmnt_amt", "pmnt_cur_cd_leg", "pmnt_rate_tenor", "pmnt_rate_unit",
    "pmnt_reset_dt", "pmnt_reset_unit", "pmnt_desc",
}
_PAYMENT_BRANCH_FIELDS = {
    "Fixed": {"pmnt_fixed_rt", "pmnt_pmnt_amt", "pmnt_cur_cd_leg"},
    "Floating": {
        "pmnt_floating_rt_index", "pmnt_floating_rt_spread", "pmnt_pmnt_amt",
        "pmnt_cur_cd_leg", "pmnt_rate_tenor", "pmnt_rate_unit",
        "pmnt_reset_dt", "pmnt_reset_unit",
    },
    "Other": {"pmnt_desc"},
}

# Fields that must be valid decimals
_BALANCE_SHEET_FIELDS = [
    "assets_attr_misc_sec", "assets_invested",
    "amt_pay_one_yr_banks_borr", "amt_pay_one_yr_ctrld_comp",
    "amt_pay_one_yr_oth_affil", "amt_pay_one_yr_other",
    "amt_pay_aft_one_yr_banks_borr", "amt_pay_aft_one_yr_ctrld_comp",
    "amt_pay_aft_one_yr_oth_affil", "amt_pay_aft_one_yr_other",
    "delay_deliv", "stand_by_commit", "liquid_pref",
]
_MONTHLY_NUMERIC_FIELDS = [
    "net_realized_gain_mon1", "net_unrealized_appr_mon1",
    "net_realized_gain_mon2", "net_unrealized_appr_mon2",
    "net_realized_gain_mon3", "net_unrealized_appr_mon3",
    "mon1_sales", "mon1_redemption", "mon1_reinvestment",
    "mon2_sales", "mon2_redemption", "mon2_reinvestment",
    "mon3_sales", "mon3_redemption", "mon3_reinvestment",
]

# ── Check helpers ──────────────────────────────────────────


def _check_re(errors, pattern, value, field):
    if not pattern.match(value):
        errors.append(f"{field}: invalid format '{value}'.")


def _check_set(errors, valid, value, field):
    if value not in valid:
        errors.append(f"{field}: invalid value '{value}' (expected: {', '.join(sorted(valid))}).")


def _as_date(value: str) -> date | None:
    try:
        parsed = date.fromisoformat(value)
        return parsed if parsed.isoformat() == value else None
    except (TypeError, ValueError):
        return None


def _check_date(errors, value, field):
    if _as_date(value) is None:
        errors.append(f"{field}: invalid date '{value}' (expected YYYY-MM-DD).")


def _as_decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value)
        if not parsed.is_finite():
            raise InvalidOperation
        return parsed
    except (InvalidOperation, TypeError, ValueError):
        return None


def _check_numeric(errors, value, field, allow_na=False):
    if allow_na and value == "N/A":
        return
    if _as_decimal(value) is None:
        errors.append(f"{field}: not a valid number '{value}'.")


def _check_nonempty(errors, value, field):
    if not value.strip():
        errors.append(f"{field}: must not be empty.")


def _reject_populated_fields(
    errors: list[str], holding: Holding, prefix: str,
    candidates: set[str] | frozenset[str], allowed: set[str] | frozenset[str],
    context: str,
) -> None:
    unexpected = sorted(
        field for field in candidates - allowed if getattr(holding, field)
    )
    if unexpected:
        errors.append(
            f"{prefix}/{context}: fields are not applicable and would not be serialized: "
            + ", ".join(unexpected)
        )


def _load_json(errors: list[str], raw: str, field: str, expected_type: type):
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        errors.append(f"{field}: invalid JSON ({exc}).")
        return None
    if not isinstance(value, expected_type):
        errors.append(f"{field}: JSON must be a {expected_type.__name__}.")
        return None
    return value


def _validate_risk_json(filing: FilingData, errors: list[str]) -> None:
    period_keys = ("3month", "1year", "5year", "10year", "30year")
    metric_keys = {"curCd"} | {
        f"{prefix}_{period}" for prefix in ("dv01", "dv100") for period in period_keys
    }
    if not filing.cur_metrics_json:
        if filing.credit_sprd_risk_ig_json or filing.credit_sprd_risk_nonig_json:
            errors.append("B.3 credit-spread JSON cannot be supplied without curMetricsJson.")
        return
    metrics = _load_json(errors, filing.cur_metrics_json, "curMetricsJson", list)
    if metrics is not None:
        if not metrics:
            errors.append("curMetricsJson: list must contain at least one currency metric.")
        currencies: list[str] = []
        for index, metric in enumerate(metrics):
            label = f"curMetricsJson[{index}]"
            if not isinstance(metric, dict):
                errors.append(f"{label}: must be an object.")
                continue
            if not _CURRENCY_RE.match(str(metric.get("curCd", ""))):
                errors.append(f"{label}.curCd: must be a three-letter currency code.")
            else:
                currencies.append(str(metric["curCd"]))
            unknown = sorted(set(metric) - metric_keys)
            if unknown:
                errors.append(f"{label}: unknown keys {unknown}.")
            for prefix in ("dv01", "dv100"):
                for period_key in period_keys:
                    key = f"{prefix}_{period_key}"
                    if key not in metric:
                        errors.append(f"{label}.{key}: required.")
                    else:
                        _check_numeric(errors, str(metric[key]), f"{label}.{key}", allow_na=True)
        if len(currencies) != len(set(currencies)):
            errors.append("curMetricsJson: currency metrics must be unique by curCd.")
    for raw, field in (
        (filing.credit_sprd_risk_ig_json, "creditSprdRiskIgJson"),
        (filing.credit_sprd_risk_nonig_json, "creditSprdRiskNonigJson"),
    ):
        if not raw:
            errors.append(f"{field}: required when curMetricsJson is supplied.")
            continue
        values = _load_json(errors, raw, field, dict)
        if values is None:
            continue
        unknown = sorted(set(values) - set(period_keys))
        if unknown:
            errors.append(f"{field}: unknown keys {unknown}.")
        for key in period_keys:
            if key not in values:
                errors.append(f"{field}.{key}: required.")
            else:
                _check_numeric(errors, str(values[key]), f"{field}.{key}", allow_na=True)


def _validate_monthly_return_json(raw: str, errors: list[str]) -> None:
    if not raw:
        return
    data = _load_json(errors, raw, "monthlyReturnCategoriesJson", dict)
    if data is None:
        return
    contracts = {
        "commodityContracts", "creditContracts", "equityContracts",
        "foreignExchgContracts", "interestRtContracts", "otherContracts",
    }
    instruments = {
        "forwardCategory", "futureCategory", "optionCategory", "swapCategory",
        "swaptionCategory", "warrantCategory", "otherCategory",
    }
    unknown = set(data) - contracts
    if unknown:
        errors.append(f"monthlyReturnCategoriesJson: unknown contracts {sorted(unknown)}.")
    for contract, values in data.items():
        if contract not in contracts or not isinstance(values, dict):
            continue
        unknown_contract_keys = sorted(set(values) - instruments - {"mon1", "mon2", "mon3"})
        if unknown_contract_keys:
            errors.append(
                f"monthlyReturnCategoriesJson.{contract}: unknown keys {unknown_contract_keys}."
            )
        selected = [name for name in instruments if values.get(name)]
        if len(selected) != 1:
            errors.append(f"monthlyReturnCategoriesJson.{contract}: exactly one instrument category is required.")
            continue
        instrument = values[selected[0]]
        if isinstance(instrument, dict):
            unknown_months = sorted(set(instrument) - {"mon1", "mon2", "mon3"})
            if unknown_months:
                errors.append(
                    f"monthlyReturnCategoriesJson.{contract}.{selected[0]}: "
                    f"unknown keys {unknown_months}."
                )
        for month in ("mon1", "mon2", "mon3"):
            for parent, label in ((values, contract), (instrument, selected[0])):
                item = parent.get(month) if isinstance(parent, dict) else None
                if not isinstance(item, dict) or not {
                    "netRealizedGain", "netUnrealizedAppr",
                } <= set(item):
                    errors.append(
                        f"monthlyReturnCategoriesJson.{contract}.{label}.{month}: "
                        "realized and unrealized values are required."
                    )
                    continue
                unknown_values = sorted(
                    set(item) - {"netRealizedGain", "netUnrealizedAppr"}
                )
                if unknown_values:
                    errors.append(
                        f"monthlyReturnCategoriesJson.{contract}.{label}.{month}: "
                        f"unknown keys {unknown_values}."
                    )
                _check_numeric(errors, str(item["netRealizedGain"]), f"{contract}.{label}.{month}.netRealizedGain", allow_na=True)
                _check_numeric(errors, str(item["netUnrealizedAppr"]), f"{contract}.{label}.{month}.netUnrealizedAppr", allow_na=True)


def _validate_liquidity_json(holding: Holding, prefix: str, errors: list[str]) -> None:
    valid_categories = {"HLI", "MLI", "LLI", "ILI"}
    valid_circumstances = {
        "DIFF_LIQUIDITY_FEATURES", "MULTI_SUBADVISORS", "POSITION_THRU_EVAL",
    }
    raw = holding.liquidity_classification_json.strip()
    if raw and raw != "N/A":
        categories = _load_json(errors, raw, f"{prefix}/liquidityClassificationJson", list)
        if categories is not None:
            if not 1 <= len(categories) <= 4:
                errors.append(f"{prefix}/liquidityClassificationJson: requires one to four categories.")
            names = []
            percentages: list[Decimal] = []
            for index, category in enumerate(categories):
                if not isinstance(category, dict) or not category.get("category") or "pct" not in category:
                    errors.append(f"{prefix}/liquidityClassificationJson[{index}]: category and pct are required.")
                    continue
                names.append(str(category["category"]))
                unknown = sorted(set(category) - {"category", "pct"})
                if unknown:
                    errors.append(
                        f"{prefix}/liquidityClassificationJson[{index}]: unknown keys {unknown}."
                    )
                if category["category"] not in valid_categories:
                    errors.append(
                        f"{prefix}/liquidityClassificationJson[{index}].category: "
                        f"invalid value {category['category']!r}."
                    )
                pct = _as_decimal(str(category["pct"]))
                if pct is None or pct < 0:
                    errors.append(
                        f"{prefix}/liquidityClassificationJson[{index}].pct: "
                        "must be a finite non-negative number."
                    )
                else:
                    percentages.append(pct)
            if len(names) != len(set(names)):
                errors.append(f"{prefix}/liquidityClassificationJson: categories must be unique.")
            if len(percentages) == len(categories) and abs(
                sum(percentages, Decimal("0")) - Decimal("100")
            ) > LIQUIDITY_PCT_TOLERANCE:
                errors.append(
                    f"{prefix}/liquidityClassificationJson: percentages must total 100 "
                    f"within {LIQUIDITY_PCT_TOLERANCE}."
                )
    if holding.liquidity_circumstances_json:
        if not raw or raw == "N/A":
            errors.append(
                f"{prefix}/liquidityCircumstancesJson: requires populated liquidity classifications."
            )
        values = _load_json(
            errors, holding.liquidity_circumstances_json,
            f"{prefix}/liquidityCircumstancesJson", list,
        )
        if values is not None:
            if len(values) > 3:
                errors.append(f"{prefix}/liquidityCircumstancesJson: at most three circumstances are allowed.")
            invalid = sorted({str(value) for value in values} - valid_circumstances)
            if invalid:
                errors.append(
                    f"{prefix}/liquidityCircumstancesJson: invalid values {invalid}."
                )
            if len(values) != len(set(map(str, values))):
                errors.append(f"{prefix}/liquidityCircumstancesJson: values must be unique.")


# ── Public validation ──────────────────────────────────────


def validate_config(config: FundConfig) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    _check_re(errors, _CIK_RE, config.cik, "cik")
    if len(config.ccc) != 8:
        errors.append(f"ccc: must be exactly 8 characters, got {len(config.ccc)}.")
    _check_nonempty(errors, config.reg_name, "regName")
    _check_re(errors, _FILE_NUMBER_RE, config.reg_file_number, "regFileNumber")
    _check_re(errors, _CIK_RE, config.reg_cik, "regCik")
    _check_re(errors, _LEI_RE, config.reg_lei, "regLei")
    _check_nonempty(errors, config.reg_street1, "regStreet1")
    _check_nonempty(errors, config.reg_city, "regCity")
    _check_re(errors, _COUNTRY_RE, config.reg_country, "regCountry")
    _check_nonempty(errors, config.series_name, "seriesName")
    _check_re(errors, _SERIES_ID_RE, config.series_id, "seriesId")
    _check_re(errors, _LEI_RE, config.series_lei, "seriesLei")
    _check_re(errors, _CLASS_ID_RE, config.class_id, "classId")
    _check_nonempty(errors, config.signer_org, "signerOrg")
    _check_nonempty(errors, config.signer_name, "signerName")
    _check_nonempty(errors, config.signer_title, "signerTitle")

    if config.cik != config.reg_cik:
        warnings.append(f"cik ({config.cik}) differs from regCik ({config.reg_cik}).")
    if config.reg_country == "US" and not config.reg_state.startswith("US-"):
        warnings.append(f"regState '{config.reg_state}' should start with 'US-'.")

    return errors, warnings


def validate_filing(
    filing: FilingData, today: "date | None" = None,
) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    today = today or date.today()

    _check_set(errors, _VALID_SUBMISSION_TYPES, filing.submission_type, "submissionType")
    _check_set(errors, {"TEST", "LIVE"}, filing.live_test_flag, "liveTestFlag")
    _check_date(errors, filing.rep_pd_end, "repPdEnd")
    _check_date(errors, filing.rep_pd_date, "repPdDate")
    _check_re(errors, _YN_RE, filing.is_final_filing, "isFinalFiling")
    _check_date(errors, filing.date_signed, "dateSigned")
    _check_numeric(errors, filing.tot_assets, "totAssets")
    _check_numeric(errors, filing.tot_liabs, "totLiabs")
    _check_numeric(errors, filing.net_assets, "netAssets")
    _check_re(errors, _YN_RE, filing.is_non_cash_collateral, "isNonCashCollateral")

    for field in _BALANCE_SHEET_FIELDS:
        _check_numeric(errors, getattr(filing, field), field)
    for rtn in ["rtn1", "rtn2", "rtn3"]:
        _check_numeric(errors, getattr(filing, rtn), rtn, allow_na=True)
    for field in _MONTHLY_NUMERIC_FIELDS:
        # All monthly gain/flow fields are decimal-or-N/A in the XSD; N/A = no feed.
        _check_numeric(errors, getattr(filing, field), field, allow_na=True)

    if filing.cash_not_reported_in_c_or_d:
        _check_numeric(errors, filing.cash_not_reported_in_c_or_d, "cashNotReportedInCOrD")

    b9 = (
        filing.deriv_exposure_pct, filing.deriv_currency_exposure_pct,
        filing.deriv_interest_rate_exposure_pct, filing.deriv_days_in_excess,
    )
    if any(b9) and not all(b9):
        errors.append("B.9 derivatives exposure is partial; all four fields are required.")
    for name, value in zip(
        ("derivExposurePct", "derivCurrencyExposurePct", "derivInterestRateExposurePct"),
        b9[:3],
    ):
        if value:
            _check_numeric(errors, value, name, allow_na=True)
    if filing.deriv_days_in_excess:
        _check_numeric(errors, filing.deriv_days_in_excess, "derivDaysInExcess", allow_na=True)

    if filing.derivatives_regime == "LIMITED" and not all(b9):
        errors.append("B.9 is required when derivativesRegime=LIMITED.")
    if filing.derivatives_regime in {"VAR_RELATIVE", "VAR_ABSOLUTE"}:
        if not filing.median_daily_var_pct or not filing.backtesting_exceptions:
            errors.append("B.10 requires medianDailyVarPct and backtestingExceptions for a VaR fund.")
    if filing.derivatives_regime == "VAR_RELATIVE":
        for name, value in (
            ("nameDesignatedIndex", filing.name_designated_index),
            ("indexIdentifier", filing.index_identifier),
            ("medianVarRatioPct", filing.median_var_ratio_pct),
        ):
            if not value:
                errors.append(f"B.10 relative VaR requires {name}.")
    if filing.median_daily_var_pct:
        _check_numeric(errors, filing.median_daily_var_pct, "medianDailyVarPct", allow_na=True)
    if filing.median_var_ratio_pct:
        _check_numeric(errors, filing.median_var_ratio_pct, "medianVarRatioPct", allow_na=True)
    if filing.backtesting_exceptions:
        _check_numeric(errors, filing.backtesting_exceptions, "backtestingExceptions", allow_na=True)

    _validate_risk_json(filing, errors)
    _validate_monthly_return_json(filing.monthly_return_categories_json, errors)

    # Cross-field checks (only if individual fields parsed OK)
    assets = _as_decimal(filing.tot_assets)
    liabs = _as_decimal(filing.tot_liabs)
    net = _as_decimal(filing.net_assets)
    if assets is not None and liabs is not None and net is not None:
        if abs(net - (assets - liabs)) > NAV_EQUATION_TOLERANCE:
            errors.append(f"NAV mismatch: netAssets ({net}) != totAssets - totLiabs ({assets - liabs}).")
        if assets < 0:
            errors.append(f"totAssets must be non-negative, got {filing.tot_assets}.")
        if liabs < 0:
            errors.append(f"totLiabs must be non-negative, got {filing.tot_liabs}.")

    pd_end = _as_date(filing.rep_pd_date)
    signed = _as_date(filing.date_signed)
    if pd_end is not None and signed is not None:
        if signed < pd_end:
            warnings.append(f"dateSigned ({filing.date_signed}) is before repPdDate ({filing.rep_pd_date}).")
        if (signed - pd_end).days > 60:
            warnings.append(f"dateSigned is {(signed - pd_end).days} days after repPdDate — filings due within 60 days.")
        if pd_end > today:
            warnings.append(f"repPdDate ({filing.rep_pd_date}) is in the future.")

    return errors, warnings


def validate_holding(holding: Holding, index: int, rep_pd_end: str = "") -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    p = f"holding[{index}] ({holding.name})"

    _check_nonempty(errors, holding.name, f"{p}/name")
    _check_re(errors, _LEI_RE, holding.lei, f"{p}/lei")
    _check_nonempty(errors, holding.title, f"{p}/title")
    _check_re(errors, _CUSIP_RE, holding.cusip, f"{p}/cusip")
    _check_numeric(errors, holding.balance, f"{p}/balance")
    _check_set(errors, _VALID_UNITS, holding.units, f"{p}/units")
    _check_re(errors, _CURRENCY_RE, holding.cur_cd, f"{p}/curCd")
    _check_numeric(errors, holding.val_usd, f"{p}/valUSD")
    _check_numeric(errors, holding.pct_val, f"{p}/pctVal")
    _check_set(errors, _VALID_PAYOFF_PROFILES, holding.payoff_profile, f"{p}/payoffProfile")
    _check_set(errors, _VALID_ASSET_CATS, holding.asset_cat, f"{p}/assetCat")
    _check_set(errors, _VALID_ISSUER_CATS, holding.issuer_cat, f"{p}/issuerCat")
    _check_re(errors, _COUNTRY_RE, holding.inv_country, f"{p}/invCountry")
    _check_re(errors, _YN_RE, holding.is_restricted_sec, f"{p}/isRestrictedSec")
    _check_set(errors, _VALID_FAIR_VAL_LEVELS, holding.fair_val_level, f"{p}/fairValLevel")
    _check_re(errors, _YN_RE, holding.is_cash_collateral, f"{p}/isCashCollateral")
    _check_re(errors, _YN_RE, holding.is_non_cash_collateral, f"{p}/isNonCashCollateral")
    _check_re(errors, _YN_RE, holding.is_loan_by_fund, f"{p}/isLoanByFund")

    if holding.isin and holding.isin != "N/A" and not _ISIN_RE.match(holding.isin):
        errors.append(f"{p}/isin: invalid format '{holding.isin}'.")
    if not any((
        holding.isin and holding.isin != "N/A",
        holding.ticker,
        holding.other_desc and holding.other_value,
        holding.cusip not in {"", "N/A", "000000000"},
    )):
        errors.append(f"{p}/identifiers: at least one usable identifier is required.")
    if bool(holding.other_desc) != bool(holding.other_value):
        errors.append(f"{p}/otherIdentifier: otherDesc and otherValue must be supplied together.")
    if holding.cur_cd != "USD" and not holding.exchange_rt:
        errors.append(f"{p}/exchangeRt: required for a non-USD holding.")
    if holding.exchange_rt:
        exchange_rate = _as_decimal(holding.exchange_rt)
        if exchange_rate is None or exchange_rate <= 0:
            errors.append(f"{p}/exchangeRt: must be a finite positive number.")

    # Conditional element validation
    if holding.issuer_cat == "OTHER" and not holding.issuer_conditional_desc:
        errors.append(f"{p}/issuerCat: 'OTHER' requires issuerConditionalDesc.")
    if holding.asset_cat == "OTHER" and not holding.asset_conditional_desc:
        errors.append(f"{p}/assetCat: 'OTHER' requires assetConditionalDesc.")

    _validate_liquidity_json(holding, p, errors)

    # Debt validation (when maturity_dt is set)
    has_debt = (
        holding.asset_cat in DEBT_ASSET_CATEGORIES
        or any(getattr(holding, field) for field in DEBT_FIELD_NAMES)
    )
    if has_debt:
        _check_date(errors, holding.maturity_dt, f"{p}/maturityDt")
        _check_set(errors, _VALID_COUPON_KINDS, holding.coupon_kind, f"{p}/couponKind")
        _check_numeric(errors, holding.annualized_rt, f"{p}/annualizedRt")
        _check_re(errors, _YN_RE, holding.is_default, f"{p}/isDefault")
        _check_re(errors, _YN_RE, holding.are_intrst_pmnts_in_arrs, f"{p}/areIntrstPmntsInArrs")
        _check_re(errors, _YN_RE, holding.is_paid_kind, f"{p}/isPaidKind")

    derivative_details = DERIVATIVE_FIELD_NAMES - {"deriv_cat"}
    if not holding.deriv_cat and any(getattr(holding, field) for field in derivative_details):
        errors.append(f"{p}/derivCat: required when derivative fields are populated.")

    # Derivative validation (when deriv_cat is set)
    if holding.deriv_cat:
        _check_set(errors, _VALID_DERIV_CATS, holding.deriv_cat, f"{p}/derivCat")
        if holding.deriv_cat in _VALID_DERIV_CATS:
            _reject_populated_fields(
                errors, holding, p, DERIVATIVE_FIELD_NAMES,
                get_allowed_derivative_fields(holding.deriv_cat),
                f"derivCat={holding.deriv_cat}",
            )
        _check_nonempty(errors, holding.counterparty_name, f"{p}/counterpartyName")
        _check_re(errors, _LEI_RE, holding.counterparty_lei, f"{p}/counterpartyLei")
        if holding.counterparty_lei == "N/A":
            warnings.append(f"{p}/counterpartyLei: real counterparties should have LEIs.")
        _check_numeric(errors, holding.unrealized_appr, f"{p}/unrealizedAppr")
        if holding.payoff_profile != "N/A":
            warnings.append(f"{p}/payoffProfile: C.3 is normalized to N/A for derivatives.")

        # Option-specific validation
        if holding.deriv_cat in ("OPT", "SWO", "WAR"):
            if not holding.ref_inst_type:
                errors.append(f"{p}/refInstType: options, swaptions, and warrants require a reference instrument.")
            _check_set(errors, _VALID_PUT_CALL, holding.put_or_call, f"{p}/putOrCall")
            _check_set(errors, _VALID_WRITTEN_PUR, holding.written_or_pur, f"{p}/writtenOrPur")
            _check_numeric(errors, holding.exercise_price, f"{p}/exercisePrice")
            _check_numeric(errors, holding.share_no, f"{p}/shareNo", allow_na=True)
            _check_re(errors, _CURRENCY_RE, holding.exercise_price_cur_cd, f"{p}/exercisePriceCurCd")
            _check_date(errors, holding.exp_dt, f"{p}/expDt")
            _check_numeric(errors, holding.delta, f"{p}/delta", allow_na=True)
            # Written options should have negative balance
            if holding.written_or_pur == "Written":
                balance = _as_decimal(holding.balance)
                if balance is not None and balance > 0:
                    warnings.append(f"{p}: written option has positive balance.")
            # Cross-field: exercise price should be positive
            exercise_price = _as_decimal(holding.exercise_price)
            if exercise_price is not None and exercise_price <= 0:
                warnings.append(f"{p}/exercisePrice: should be positive, got {holding.exercise_price}.")
            # Cross-field: delta should be in [-1, 1]
            if holding.delta and holding.delta != "N/A":
                delta = _as_decimal(holding.delta)
                if delta is not None and not (Decimal("-1") <= delta <= Decimal("1")):
                    warnings.append(f"{p}/delta: should be in [-1, 1], got {holding.delta}.")

        # Swap-specific validation
        if holding.deriv_cat == "SWP":
            _check_re(errors, _YN_RE, holding.swap_flag, f"{p}/swapFlag")
            _check_date(errors, holding.termination_dt, f"{p}/terminationDt")
            _check_numeric(errors, holding.upfront_pmnt, f"{p}/upfrontPmnt")
            _check_re(errors, _CURRENCY_RE, holding.pmnt_cur_cd, f"{p}/pmntCurCd")
            _check_numeric(errors, holding.upfront_rcpt, f"{p}/upfrontRcpt")
            _check_re(errors, _CURRENCY_RE, holding.rcpt_cur_cd, f"{p}/rcptCurCd")
            _check_numeric(errors, holding.notional_amt, f"{p}/notionalAmt")
            _check_re(errors, _CURRENCY_RE, holding.swap_cur_cd, f"{p}/swapCurCd")
            if not holding.rec_fixed_or_floating:
                errors.append(f"{p}/recFixedOrFloating: must not be empty for swaps.")
            else:
                _check_set(errors, _VALID_FIXED_FLOATING, holding.rec_fixed_or_floating, f"{p}/recFixedOrFloating")
                if holding.rec_fixed_or_floating == "Fixed":
                    _check_numeric(errors, holding.rec_fixed_rt, f"{p}/recFixedRt")
                    _check_numeric(errors, holding.rec_pmnt_amt, f"{p}/recPmntAmt", allow_na=True)
                    _check_re(errors, _CURRENCY_RE, holding.rec_cur_cd, f"{p}/recCurCd")
                elif holding.rec_fixed_or_floating == "Floating":
                    _check_nonempty(errors, holding.rec_floating_rt_index, f"{p}/recFloatingRtIndex")
                    _check_numeric(errors, holding.rec_floating_rt_spread, f"{p}/recFloatingRtSpread")
                    _check_numeric(errors, holding.rec_pmnt_amt, f"{p}/recPmntAmt")
                    _check_re(errors, _CURRENCY_RE, holding.rec_cur_cd, f"{p}/recCurCd")
                    _check_set(
                        errors, _VALID_FLOATING_DATE_UNITS,
                        holding.rec_rate_tenor, f"{p}/recRateTenor",
                    )
                    _check_re(
                        errors, _NONNEGATIVE_INTEGER_5_RE,
                        holding.rec_rate_unit, f"{p}/recRateUnit",
                    )
                    _check_set(
                        errors, _VALID_FLOATING_DATE_UNITS,
                        holding.rec_reset_dt, f"{p}/recResetDt",
                    )
                    _check_re(
                        errors, _NONNEGATIVE_INTEGER_5_RE,
                        holding.rec_reset_unit, f"{p}/recResetUnit",
                    )
                elif holding.rec_fixed_or_floating == "Other":
                    _check_nonempty(errors, holding.rec_desc, f"{p}/recDesc")
                if holding.rec_fixed_or_floating in _RECEIVE_BRANCH_FIELDS:
                    _reject_populated_fields(
                        errors, holding, p, _RECEIVE_LEG_FIELDS,
                        _RECEIVE_BRANCH_FIELDS[holding.rec_fixed_or_floating],
                        f"recFixedOrFloating={holding.rec_fixed_or_floating}",
                    )
            if not holding.pmnt_fixed_or_floating:
                errors.append(f"{p}/pmntFixedOrFloating: must not be empty for swaps.")
            else:
                _check_set(errors, _VALID_FIXED_FLOATING, holding.pmnt_fixed_or_floating, f"{p}/pmntFixedOrFloating")
                if holding.pmnt_fixed_or_floating == "Fixed":
                    _check_numeric(errors, holding.pmnt_fixed_rt, f"{p}/pmntFixedRt")
                    _check_numeric(errors, holding.pmnt_pmnt_amt, f"{p}/pmntPmntAmt", allow_na=True)
                    _check_re(errors, _CURRENCY_RE, holding.pmnt_cur_cd_leg, f"{p}/pmntCurCdLeg")
                elif holding.pmnt_fixed_or_floating == "Floating":
                    _check_nonempty(errors, holding.pmnt_floating_rt_index, f"{p}/pmntFloatingRtIndex")
                    _check_numeric(errors, holding.pmnt_floating_rt_spread, f"{p}/pmntFloatingRtSpread")
                    _check_numeric(errors, holding.pmnt_pmnt_amt, f"{p}/pmntPmntAmt")
                    _check_re(errors, _CURRENCY_RE, holding.pmnt_cur_cd_leg, f"{p}/pmntCurCdLeg")
                    _check_set(
                        errors, _VALID_FLOATING_DATE_UNITS,
                        holding.pmnt_rate_tenor, f"{p}/pmntRateTenor",
                    )
                    _check_re(
                        errors, _NONNEGATIVE_INTEGER_5_RE,
                        holding.pmnt_rate_unit, f"{p}/pmntRateUnit",
                    )
                    _check_set(
                        errors, _VALID_FLOATING_DATE_UNITS,
                        holding.pmnt_reset_dt, f"{p}/pmntResetDt",
                    )
                    _check_re(
                        errors, _NONNEGATIVE_INTEGER_5_RE,
                        holding.pmnt_reset_unit, f"{p}/pmntResetUnit",
                    )
                elif holding.pmnt_fixed_or_floating == "Other":
                    _check_nonempty(errors, holding.pmnt_desc, f"{p}/pmntDesc")
                if holding.pmnt_fixed_or_floating in _PAYMENT_BRANCH_FIELDS:
                    _reject_populated_fields(
                        errors, holding, p, _PAYMENT_LEG_FIELDS,
                        _PAYMENT_BRANCH_FIELDS[holding.pmnt_fixed_or_floating],
                        f"pmntFixedOrFloating={holding.pmnt_fixed_or_floating}",
                    )
            # Cross-field: swap may have expired
            if rep_pd_end and holding.termination_dt:
                term = _as_date(holding.termination_dt)
                pd_end = _as_date(rep_pd_end)
                if term is not None and pd_end is not None:
                    if term <= pd_end:
                        warnings.append(f"{p}: terminationDt ({holding.termination_dt}) <= repPdEnd ({rep_pd_end}) — swap may have expired.")

        # Forward/Future-specific validation
        if holding.deriv_cat in ("FWD", "FUT"):
            _check_set(errors, _VALID_PAYOFF_PROFILES, holding.payoff_prof_deriv, f"{p}/payoffProfDeriv")
            _check_date(errors, holding.exp_dt, f"{p}/expDt")
            _check_numeric(errors, holding.notional_amt, f"{p}/notionalAmt")
            _check_re(errors, _CURRENCY_RE, holding.swap_cur_cd, f"{p}/swapCurCd")
            if holding.deriv_cat == "FUT" and not holding.ref_inst_type:
                errors.append(f"{p}/refInstType: futures require a reference instrument.")

        if holding.deriv_cat == "OTH":
            _check_nonempty(errors, holding.other_deriv_desc, f"{p}/otherDerivDesc")
            _check_date(errors, holding.termination_dt, f"{p}/terminationDt")
            _check_numeric(errors, holding.notional_amt, f"{p}/notionalAmt", allow_na=True)
            _check_re(errors, _CURRENCY_RE, holding.swap_cur_cd, f"{p}/swapCurCd")
            _check_numeric(errors, holding.delta, f"{p}/delta", allow_na=True)

    # Reference instrument validation (applies to all derivatives with ref_inst_type)
    if not holding.ref_inst_type and any(
        getattr(holding, field) for field in _REFERENCE_DETAIL_FIELDS
    ):
        errors.append(f"{p}/refInstType: required when reference fields are populated.")
    if holding.ref_inst_type:
        _check_set(errors, _VALID_REF_INST_TYPES, holding.ref_inst_type, f"{p}/refInstType")
        if holding.ref_inst_type in _REFERENCE_BRANCH_FIELDS:
            _reject_populated_fields(
                errors, holding, p, _REFERENCE_DETAIL_FIELDS,
                _REFERENCE_BRANCH_FIELDS[holding.ref_inst_type],
                f"refInstType={holding.ref_inst_type}",
            )
        if holding.ref_inst_type == "indexBasket":
            _check_nonempty(errors, holding.ref_index_name, f"{p}/refIndexName")
            _check_nonempty(errors, holding.ref_index_identifier, f"{p}/refIndexIdentifier")
        elif holding.ref_inst_type == "otherRefInst":
            _check_nonempty(errors, holding.ref_issuer_name, f"{p}/refIssuerName")
            _check_nonempty(errors, holding.ref_issue_title, f"{p}/refIssueTitle")
            if not any((holding.ref_cusip, holding.ref_isin, holding.ref_ticker)):
                errors.append(f"{p}/referenceIdentifiers: at least one identifier is required.")
            if holding.ref_cusip:
                _check_re(errors, _CUSIP_RE, holding.ref_cusip, f"{p}/refCusip")
            if holding.ref_isin and not _ISIN_RE.match(holding.ref_isin):
                errors.append(f"{p}/refIsin: invalid format '{holding.ref_isin}'.")

    return errors, warnings


def validate_holdings(holdings: list[Holding], rep_pd_end: str = "",
                      net_assets: str = "") -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    if not holdings:
        errors.append("No holdings provided.")
        return errors, warnings

    for i, h in enumerate(holdings):
        h_err, h_warn = validate_holding(h, i, rep_pd_end=rep_pd_end)
        errors.extend(h_err)
        warnings.extend(h_warn)

    pct_values = [_as_decimal(holding.pct_val) for holding in holdings]
    value_usd = [_as_decimal(holding.val_usd) for holding in holdings]
    net = _as_decimal(net_assets) if net_assets else None
    if all(value is not None for value in pct_values + value_usd):
        pct_sum = sum((value for value in pct_values if value is not None), Decimal("0"))
        # The percentages must tie to the reported total: sum(pctVal) == sum(valUSD)/netAssets.
        # This is exact regardless of how much cash the fund holds, unlike comparing to 100%
        # (a fund that is 70% cash legitimately sums to 30%). A break here means pctVal and
        # netAssets were computed off different denominators.
        if net is not None and net != 0:
            implied = sum(
                (value for value in value_usd if value is not None), Decimal("0")
            ) / net * Decimal("100")
            # Tolerance absorbs 2dp rounding across the holdings, nothing more.
            tolerance = max(
                PCT_TIE_MINIMUM_TOLERANCE,
                PCT_TIE_PER_HOLDING_TOLERANCE * len(holdings),
            )
            if abs(pct_sum - implied) > tolerance:
                errors.append(
                    f"pctVal does not tie to netAssets: holdings sum to {pct_sum:.2f}% but "
                    f"valUSD/netAssets implies {implied:.2f}% - the percentages and the "
                    f"reported netAssets came from different denominators.")
    else:
        warnings.append("Could not sum pctVal — some values are not numeric.")

    cusips = [h.cusip for h in holdings if h.cusip not in ("N/A", "000000000")]
    dupes = {cusip for cusip, count in Counter(cusips).items() if count > 1}
    if dupes:
        warnings.append(f"Duplicate CUSIPs: {', '.join(sorted(dupes))}.")

    return errors, warnings


def validate_all(
    config: FundConfig, filing: FilingData, holdings: list[Holding],
    today: "date | None" = None,
) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for fn, args in [
        (validate_config, (config,)),
        (validate_filing, (filing, today)),
        (validate_holdings, (holdings, filing.rep_pd_end, filing.net_assets)),
    ]:
        e, w = fn(*args)
        errors.extend(e)
        warnings.extend(w)
    return errors, warnings


def validate_for_serialization(
    config: FundConfig, filing: FilingData, holdings: list[Holding],
) -> list[str]:
    """Validate every value that the XML builder can serialize.

    Portfolio reconciliation remains a pipeline gate; this function protects
    the builder itself from incomplete fields and invalid conditional branches.
    """
    config_errors, _ = validate_config(config)
    filing_errors, _ = validate_filing(filing)
    holding_errors = ["No holdings provided."] if not holdings else []
    for index, holding in enumerate(holdings):
        errors, _ = validate_holding(holding, index, rep_pd_end=filing.rep_pd_end)
        holding_errors.extend(errors)
    return config_errors + filing_errors + holding_errors
