"""Parsers for key=value txt files and CSV holdings files."""

import csv
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from nport.models import FilingData, FundConfig, Holding

# Key name in txt file -> dataclass field name
CONFIG_KEY_MAP = {
    "cik": "cik", "ccc": "ccc",
    "regName": "reg_name", "regFileNumber": "reg_file_number",
    "regCik": "reg_cik", "regLei": "reg_lei",
    "regStreet1": "reg_street1", "regStreet2": "reg_street2",
    "regCity": "reg_city", "regState": "reg_state",
    "regCountry": "reg_country", "regZipOrPostalCode": "reg_zip",
    "regPhone": "reg_phone",
    "seriesName": "series_name", "seriesId": "series_id",
    "seriesLei": "series_lei", "classId": "class_id",
    "signerOrg": "signer_org", "signerName": "signer_name",
    "signerTitle": "signer_title",
    "fiscalYearEndMMDD": "fiscal_year_end_mmdd",
    "derivativesRegimePolicy": "derivatives_regime_policy",
    "liquidityRequired": "liquidity_required",
    "cashB2fRequired": "cash_b2f_required",
    "policyEffectiveFrom": "policy_effective_from",
    "policyEffectiveTo": "policy_effective_to",
    "policyApprovedBy": "policy_approved_by",
    "policyApprovedAt": "policy_approved_at",
    "policySourceRef": "policy_source_ref",
    "requiredSources": "required_sources",
}

FILING_KEY_MAP = {
    "submissionType": "submission_type",
    "liveTestFlag": "live_test_flag",
    "repPdEnd": "rep_pd_end", "repPdDate": "rep_pd_date",
    "isFinalFiling": "is_final_filing", "dateSigned": "date_signed",
    "totAssets": "tot_assets", "totLiabs": "tot_liabs",
    "netAssets": "net_assets",
    "assetsAttrMiscSec": "assets_attr_misc_sec",
    "assetsInvested": "assets_invested",
    "amtPayOneYrBanksBorr": "amt_pay_one_yr_banks_borr",
    "amtPayOneYrCtrldComp": "amt_pay_one_yr_ctrld_comp",
    "amtPayOneYrOthAffil": "amt_pay_one_yr_oth_affil",
    "amtPayOneYrOther": "amt_pay_one_yr_other",
    "amtPayAftOneYrBanksBorr": "amt_pay_aft_one_yr_banks_borr",
    "amtPayAftOneYrCtrldComp": "amt_pay_aft_one_yr_ctrld_comp",
    "amtPayAftOneYrOthAffil": "amt_pay_aft_one_yr_oth_affil",
    "amtPayAftOneYrOther": "amt_pay_aft_one_yr_other",
    "delayDeliv": "delay_deliv", "standByCommit": "stand_by_commit",
    "liquidPref": "liquid_pref",
    "isNonCashCollateral": "is_non_cash_collateral",
    "rtn1": "rtn1", "rtn2": "rtn2", "rtn3": "rtn3",
    "netRealizedGainMon1": "net_realized_gain_mon1",
    "netUnrealizedApprMon1": "net_unrealized_appr_mon1",
    "netRealizedGainMon2": "net_realized_gain_mon2",
    "netUnrealizedApprMon2": "net_unrealized_appr_mon2",
    "netRealizedGainMon3": "net_realized_gain_mon3",
    "netUnrealizedApprMon3": "net_unrealized_appr_mon3",
    "mon1Sales": "mon1_sales", "mon1Redemption": "mon1_redemption",
    "mon1Reinvestment": "mon1_reinvestment",
    "mon2Sales": "mon2_sales", "mon2Redemption": "mon2_redemption",
    "mon2Reinvestment": "mon2_reinvestment",
    "mon3Sales": "mon3_sales", "mon3Redemption": "mon3_redemption",
    "mon3Reinvestment": "mon3_reinvestment",
    "nameDesignatedIndex": "name_designated_index",
    "indexIdentifier": "index_identifier",
    # B.3 Risk metrics (optional)
    "curMetricsJson": "cur_metrics_json",
    "creditSprdRiskIgJson": "credit_sprd_risk_ig_json",
    "creditSprdRiskNonigJson": "credit_sprd_risk_nonig_json",
    "cashNotReportedInCOrD": "cash_not_reported_in_c_or_d",
    "monthlyReturnCategoriesJson": "monthly_return_categories_json",
    "derivativesRegime": "derivatives_regime",
    "derivExposurePct": "deriv_exposure_pct",
    "derivCurrencyExposurePct": "deriv_currency_exposure_pct",
    "derivInterestRateExposurePct": "deriv_interest_rate_exposure_pct",
    "derivDaysInExcess": "deriv_days_in_excess",
    "medianDailyVarPct": "median_daily_var_pct",
    "medianVarRatioPct": "median_var_ratio_pct",
    "backtestingExceptions": "backtesting_exceptions",
}

HOLDINGS_KEY_MAP = {
    "name": "name", "lei": "lei", "title": "title",
    "cusip": "cusip", "isin": "isin", "ticker": "ticker",
    "balance": "balance", "units": "units", "curCd": "cur_cd",
    "valUSD": "val_usd", "pctVal": "pct_val",
    "payoffProfile": "payoff_profile",
    "assetCat": "asset_cat", "issuerCat": "issuer_cat",
    "invCountry": "inv_country",
    "isRestrictedSec": "is_restricted_sec",
    "fairValLevel": "fair_val_level",
    "isCashCollateral": "is_cash_collateral",
    "isNonCashCollateral": "is_non_cash_collateral",
    "isLoanByFund": "is_loan_by_fund",
    # Conditional elements
    "issuerConditionalDesc": "issuer_conditional_desc",
    "assetConditionalDesc": "asset_conditional_desc",
    "otherDesc": "other_desc",
    "otherValue": "other_value",
    "exchangeRt": "exchange_rt",
    # Debt fields (C.9)
    "maturityDt": "maturity_dt",
    "couponKind": "coupon_kind",
    "annualizedRt": "annualized_rt",
    "isDefault": "is_default",
    "areIntrstPmntsInArrs": "are_intrst_pmnts_in_arrs",
    "isPaidKind": "is_paid_kind",
    # Derivative common
    "derivCat": "deriv_cat",
    "counterpartyName": "counterparty_name",
    "counterpartyLei": "counterparty_lei",
    "unrealizedAppr": "unrealized_appr",
    # Options (C.11.c)
    "putOrCall": "put_or_call",
    "writtenOrPur": "written_or_pur",
    "shareNo": "share_no",
    "exercisePrice": "exercise_price",
    "exercisePriceCurCd": "exercise_price_cur_cd",
    "expDt": "exp_dt",
    "delta": "delta",
    # Reference instrument
    "refInstType": "ref_inst_type",
    "refIndexName": "ref_index_name",
    "refIndexIdentifier": "ref_index_identifier",
    "refIssuerName": "ref_issuer_name",
    "refIssueTitle": "ref_issue_title",
    "refCusip": "ref_cusip",
    "refIsin": "ref_isin",
    "refTicker": "ref_ticker",
    # Swaps (C.11.f)
    "swapFlag": "swap_flag",
    "terminationDt": "termination_dt",
    "upfrontPmnt": "upfront_pmnt",
    "pmntCurCd": "pmnt_cur_cd",
    "upfrontRcpt": "upfront_rcpt",
    "rcptCurCd": "rcpt_cur_cd",
    "notionalAmt": "notional_amt",
    "swapCurCd": "swap_cur_cd",
    # Receive leg
    "recFixedOrFloating": "rec_fixed_or_floating",
    "recFixedRt": "rec_fixed_rt",
    "recFloatingRtIndex": "rec_floating_rt_index",
    "recFloatingRtSpread": "rec_floating_rt_spread",
    "recPmntAmt": "rec_pmnt_amt",
    "recCurCd": "rec_cur_cd",
    "recRateTenor": "rec_rate_tenor",
    "recRateUnit": "rec_rate_unit",
    "recResetDt": "rec_reset_dt",
    "recResetUnit": "rec_reset_unit",
    "recDesc": "rec_desc",
    "pmntDesc": "pmnt_desc",
    # Pay leg
    "pmntFixedOrFloating": "pmnt_fixed_or_floating",
    "pmntFixedRt": "pmnt_fixed_rt",
    "pmntFloatingRtIndex": "pmnt_floating_rt_index",
    "pmntFloatingRtSpread": "pmnt_floating_rt_spread",
    "pmntPmntAmt": "pmnt_pmnt_amt",
    "pmntCurCdLeg": "pmnt_cur_cd_leg",
    "pmntRateTenor": "pmnt_rate_tenor",
    "pmntRateUnit": "pmnt_rate_unit",
    "pmntResetDt": "pmnt_reset_dt",
    "pmntResetUnit": "pmnt_reset_unit",
    # Futures/forwards
    "payoffProfDeriv": "payoff_prof_deriv",
    # Other derivatives
    "otherDerivDesc": "other_deriv_desc",
    "liquidityClassificationJson": "liquidity_classification_json",
    "liquidityCircumstancesJson": "liquidity_circumstances_json",
}

def optional_model_fields(model_type: type[Any]) -> frozenset[str]:
    """Return fields that the dataclass itself declares optional.

    Parser optionality is derived from the canonical model so it cannot drift
    into a second, independently maintained schema.
    """
    return frozenset(
        field.name
        for field in fields(model_type)
        if field.default is not MISSING or field.default_factory is not MISSING
    )


OPTIONAL_HOLDING_FIELDS = optional_model_fields(Holding)
OPTIONAL_FILING_FIELDS = optional_model_fields(FilingData)
OPTIONAL_CONFIG_FIELDS = optional_model_fields(FundConfig)


def _parse_kv_file(path: Path) -> dict[str, str]:
    """Parse a key=value text file, skipping comments and blank lines."""
    data = {}
    with open(path, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"{path}:{lineno}: expected key=value, got: {line!r}")
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                raise ValueError(f"{path}:{lineno}: key must not be empty.")
            if key in data:
                raise ValueError(f"{path}:{lineno}: duplicate key {key!r}.")
            data[key] = value.strip()
    return data


def _map_keys(
    raw: dict[str, str], key_map: dict[str, str], source: str | Path,
    optional: frozenset[str] = frozenset(), *,
    reject_unknown: bool = False,
) -> dict[str, str]:
    """Map txt/csv keys to dataclass field names, raising on missing required keys."""
    if reject_unknown:
        unknown = sorted(set(raw) - set(key_map))
        if unknown:
            raise ValueError(f"{source}: unknown key(s): {', '.join(unknown)}.")
    kwargs: dict[str, str] = {}
    for txt_key, field_name in key_map.items():
        if txt_key not in raw:
            if field_name in optional:
                kwargs[field_name] = ""
                continue
            raise ValueError(f"{source}: missing required key '{txt_key}'.")
        kwargs[field_name] = (raw[txt_key] or "").strip()
    return kwargs


def parse_config(path: str | Path) -> FundConfig:
    path = Path(path)
    return FundConfig(**_map_keys(
        _parse_kv_file(path), CONFIG_KEY_MAP, path, OPTIONAL_CONFIG_FIELDS,
        reject_unknown=True,
    ))


def parse_filing(path: str | Path) -> FilingData:
    path = Path(path)
    return FilingData(**_map_keys(
        _parse_kv_file(path), FILING_KEY_MAP, path, OPTIONAL_FILING_FIELDS,
        reject_unknown=True,
    ))


def _validate_csv_headers(
    reader: csv.DictReader, path: Path, *, allowed: set[str] | None = None,
    required: set[str] | None = None,
) -> list[str]:
    headers = reader.fieldnames or []
    duplicates = sorted({value for value in headers if value and headers.count(value) > 1})
    unknown = sorted(set(headers) - allowed) if allowed is not None else []
    missing = sorted(required - set(headers)) if required is not None else []
    problems = []
    if not headers or any(not value for value in headers):
        problems.append("blank or missing column name")
    if duplicates:
        problems.append("duplicate columns: " + ", ".join(duplicates))
    if unknown:
        problems.append("unknown columns: " + ", ".join(unknown))
    if missing:
        problems.append("missing required columns: " + ", ".join(missing))
    if problems:
        raise ValueError(f"{path}: invalid CSV header row ({'; '.join(problems)}).")
    return headers


def _clean_csv_row(row: dict[str | None, str | None], source: str) -> dict[str, str]:
    if None in row:
        raise ValueError(f"{source}: row has more values than the header.")
    return {key: (value or "").strip() for key, value in row.items() if key is not None}


def _parse_split_holdings(base_path: Path) -> list[Holding]:
    """Parse holdings from split CSV files (base + optional satellites)."""
    parent = base_path.parent

    # Read base holdings.csv, indexed by holdingId
    base_rows: dict[str, dict[str, str]] = {}
    row_order: list[str] = []
    required_headers = {
        external for external, internal in HOLDINGS_KEY_MAP.items()
        if internal not in OPTIONAL_HOLDING_FIELDS
    }
    with open(base_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _validate_csv_headers(
            reader, base_path, allowed=set(HOLDINGS_KEY_MAP) | {"holdingId"},
            required=required_headers | {"holdingId"},
        )
        for rownum, row in enumerate(reader, 2):
            row = _clean_csv_row(row, f"{base_path}:{rownum}")
            hid = row.pop("holdingId", "").strip()
            if not hid:
                raise ValueError(f"{base_path}:{rownum}: missing holdingId value.")
            if hid in base_rows:
                raise ValueError(
                    f"{base_path}:{rownum}: duplicate holdingId '{hid}'."
                )
            base_rows[hid] = dict(row)
            row_order.append(hid)

    # Merge satellite files
    for sat_name in ("debt_securities.csv", "derivatives.csv"):
        sat_path = parent / sat_name
        if not sat_path.is_file():
            continue
        with open(sat_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            _validate_csv_headers(
                reader, sat_path, allowed=set(HOLDINGS_KEY_MAP) | {"holdingId"},
                required={"holdingId"},
            )
            satellite_ids: set[str] = set()
            for rownum, row in enumerate(reader, 2):
                row = _clean_csv_row(row, f"{sat_path}:{rownum}")
                hid = row.pop("holdingId", "").strip()
                if not hid:
                    raise ValueError(
                        f"{sat_path}:{rownum}: missing holdingId value."
                    )
                if hid not in base_rows:
                    raise ValueError(
                        f"{sat_path}:{rownum}: holdingId '{hid}' not in {base_path.name}."
                    )
                if hid in satellite_ids:
                    raise ValueError(f"{sat_path}:{rownum}: duplicate holdingId '{hid}'.")
                satellite_ids.add(hid)
                conflicts = sorted(
                    key for key, value in row.items()
                    if value and base_rows[hid].get(key) and base_rows[hid][key] != value
                )
                if conflicts:
                    raise ValueError(
                        f"{sat_path}:{rownum}: conflicting value(s) already present in "
                        f"{base_path.name}: {', '.join(conflicts)}."
                    )
                base_rows[hid].update({key: value for key, value in row.items() if value})

    # Construct Holding objects
    holdings = []
    for hid in row_order:
        row = base_rows[hid]
        kwargs = _map_keys(
            row, HOLDINGS_KEY_MAP, f"{base_path}: holdingId {hid!r}",
            OPTIONAL_HOLDING_FIELDS, reject_unknown=True,
        )
        holdings.append(Holding(**kwargs))

    return holdings


def parse_holdings(path: str | Path) -> list[Holding]:
    path = Path(path)
    # Auto-detect split format by checking for holdingId column
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = _validate_csv_headers(
            reader, path, allowed=set(HOLDINGS_KEY_MAP) | {"holdingId"},
        )
    if "holdingId" in headers:
        return _parse_split_holdings(path)
    # Existing flat-CSV code path
    holdings = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_headers = {
            external for external, internal in HOLDINGS_KEY_MAP.items()
            if internal not in OPTIONAL_HOLDING_FIELDS
        }
        _validate_csv_headers(
            reader, path, allowed=set(HOLDINGS_KEY_MAP), required=required_headers,
        )
        for rownum, row in enumerate(reader, 2):
            row = _clean_csv_row(row, f"{path}:{rownum}")
            kwargs = _map_keys(
                row, HOLDINGS_KEY_MAP, f"{path}:{rownum}",
                OPTIONAL_HOLDING_FIELDS, reject_unknown=True,
            )
            holdings.append(Holding(**kwargs))
    return holdings
