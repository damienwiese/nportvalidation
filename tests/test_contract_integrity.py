"""Cross-layer contracts for canonical models, validation, XML, and XSD."""

import json
from dataclasses import replace
from datetime import date

import pytest

from nport.builder import NportBuilder
from nport.input_validation import (
    validate_filing,
    validate_for_serialization,
    validate_holdings,
)
from nport.schema import FIELD_BY_NAME, get_required_fields
from nport.xsd_validator import NportValidator

BRANCHES = (
    "equity", "debt", "option", "swap_floating", "swap_fixed",
    "swap_other", "forward", "future", "other_derivative",
)


def _derivative(factories, **values):
    base = dict(
        payoff_profile="N/A", asset_cat="DE",
        counterparty_name="Test Counterparty",
        counterparty_lei="549300DKPDN9M5S8GB14",
        unrealized_appr="0", other_desc="INTERNAL", other_value="DERIV-1",
    )
    base.update(values)
    return factories.equity(**base)


def _branch(factories, name):
    if name == "equity":
        return factories.equity(), {}
    if name == "debt":
        return factories.bond(), {"has_debt": True}
    if name == "option":
        return factories.option(), {
            "deriv_cat": "OPT", "ref_inst_type": "indexBasket",
        }
    if name == "swap_floating":
        return factories.swap(), {
            "deriv_cat": "SWP", "ref_inst_type": "indexBasket",
            "rec_fixed_or_floating": "Floating",
            "pmnt_fixed_or_floating": "Floating",
        }
    if name == "swap_fixed":
        holding = factories.swap(
            rec_fixed_or_floating="Fixed", rec_fixed_rt="0.01",
            rec_floating_rt_index="", rec_floating_rt_spread="",
            rec_rate_tenor="", rec_rate_unit="", rec_reset_dt="", rec_reset_unit="",
            pmnt_fixed_or_floating="Fixed", pmnt_fixed_rt="0.02",
            pmnt_floating_rt_index="", pmnt_floating_rt_spread="",
            pmnt_rate_tenor="", pmnt_rate_unit="", pmnt_reset_dt="", pmnt_reset_unit="",
        )
        return holding, {
            "deriv_cat": "SWP", "ref_inst_type": "indexBasket",
            "rec_fixed_or_floating": "Fixed", "pmnt_fixed_or_floating": "Fixed",
        }
    if name == "swap_other":
        holding = factories.swap(
            rec_fixed_or_floating="Other", rec_desc="Receive custom leg",
            rec_floating_rt_index="", rec_floating_rt_spread="", rec_pmnt_amt="",
            rec_cur_cd="", rec_rate_tenor="", rec_rate_unit="",
            rec_reset_dt="", rec_reset_unit="",
            pmnt_fixed_or_floating="Other", pmnt_desc="Pay custom leg",
            pmnt_floating_rt_index="", pmnt_floating_rt_spread="", pmnt_pmnt_amt="",
            pmnt_cur_cd_leg="", pmnt_rate_tenor="", pmnt_rate_unit="",
            pmnt_reset_dt="", pmnt_reset_unit="",
        )
        return holding, {
            "deriv_cat": "SWP", "ref_inst_type": "indexBasket",
            "rec_fixed_or_floating": "Other", "pmnt_fixed_or_floating": "Other",
        }
    if name == "forward":
        return _derivative(
            factories, deriv_cat="FWD", payoff_prof_deriv="Long",
            exp_dt="2027-01-31", notional_amt="1000000", swap_cur_cd="USD",
        ), {"deriv_cat": "FWD"}
    if name == "future":
        return _derivative(
            factories, deriv_cat="FUT", payoff_prof_deriv="Long",
            exp_dt="2027-01-31", notional_amt="1000000", swap_cur_cd="USD",
            ref_inst_type="indexBasket", ref_index_name="Test Index",
            ref_index_identifier="TEST",
        ), {"deriv_cat": "FUT", "ref_inst_type": "indexBasket"}
    if name == "other_derivative":
        return _derivative(
            factories, deriv_cat="OTH", other_deriv_desc="Custom derivative",
            termination_dt="2027-01-31", notional_amt="1000000",
            swap_cur_cd="USD", delta="N/A",
        ), {"deriv_cat": "OTH"}
    raise AssertionError(f"unknown test branch: {name}")


@pytest.mark.parametrize("branch", BRANCHES)
def test_each_canonical_branch_validates_and_passes_xsd(branch, factories, schema_dir):
    holding, _ = _branch(factories, branch)
    config = factories.config()
    filing = factories.filing()
    assert validate_for_serialization(config, filing, [holding]) == []
    xml = NportBuilder(config, filing, [holding]).to_xml_bytes()
    assert NportValidator(schema_dir).validate_xsd(xml) == []


@pytest.mark.parametrize("branch", BRANCHES)
def test_every_declared_required_field_is_enforced(branch, factories):
    holding, selector_args = _branch(factories, branch)
    required = get_required_fields(**selector_args)
    assert required
    for field in required:
        incomplete = replace(holding, **{field: ""})
        errors = validate_for_serialization(
            factories.config(), factories.filing(), [incomplete],
        )
        assert errors, f"{branch}.{field} was declared required but validation accepted blank"


@pytest.mark.parametrize("branch", BRANCHES)
def test_every_typed_required_field_rejects_invalid_lexical_data(branch, factories):
    holding, selector_args = _branch(factories, branch)
    invalid_by_type = {
        "decimal": "NaN",
        "date": "2026-02-30",
        "enum": "INVALID",
        "Y/N": "MAYBE",
        "nonnegative integer": "-1",
        "json": "not-json",
    }
    for field in get_required_fields(**selector_args):
        value_type = FIELD_BY_NAME[field].value_type
        if value_type not in invalid_by_type:
            continue
        invalid = replace(holding, **{field: invalid_by_type[value_type]})
        errors = validate_for_serialization(
            factories.config(), factories.filing(), [invalid],
        )
        assert errors, (
            f"{branch}.{field} ({value_type}) accepted invalid lexical data"
        )


def test_decimal_accounting_is_exact(factories):
    filing = factories.filing(tot_assets="0.3", tot_liabs="0.1", net_assets="0.2")
    errors, _ = validate_filing(filing, today=date(2026, 3, 1))
    assert not any("NAV mismatch" in error for error in errors)

    holdings = [
        factories.equity(val_usd="0.1", pct_val="33.33333333333333333333333333"),
        factories.equity(
            name="Second", cusip="12345A789", ticker="TST2",
            val_usd="0.2", pct_val="66.66666666666666666666666667",
        ),
    ]
    errors, _ = validate_holdings(holdings, net_assets="0.3")
    assert not any("does not tie" in error for error in errors)


def test_holding_percentage_tie_tolerance_boundary_is_deterministic(factories):
    within = factories.equity(val_usd="100", pct_val="100.5")
    outside = replace(within, pct_val="100.5001")

    within_errors, _ = validate_holdings([within], net_assets="100")
    outside_errors, _ = validate_holdings([outside], net_assets="100")

    assert not any("does not tie" in error for error in within_errors)
    assert any("does not tie" in error for error in outside_errors)


def test_nav_tolerance_boundary_is_deterministic(factories):
    within = factories.filing(tot_assets="100.00", tot_liabs="0", net_assets="99.98")
    outside = replace(within, net_assets="99.979")
    within_errors, _ = validate_filing(within, today=date(2026, 3, 1))
    outside_errors, _ = validate_filing(outside, today=date(2026, 3, 1))
    assert not any("NAV mismatch" in error for error in within_errors)
    assert any("NAV mismatch" in error for error in outside_errors)


def test_non_usd_positions_require_a_positive_exchange_rate(factories):
    holding = factories.equity(cur_cd="EUR", exchange_rt="")
    errors = validate_for_serialization(
        factories.config(), factories.filing(), [holding],
    )
    assert any("exchangeRt: required" in error for error in errors)
    assert "exchange_rt" in get_required_fields(currency="EUR")

    valid = replace(holding, exchange_rt="1.125")
    assert validate_for_serialization(
        factories.config(), factories.filing(), [valid],
    ) == []


def test_internal_json_contract_rejects_unknown_fields(factories):
    periods = ("3month", "1year", "5year", "10year", "30year")
    metric = {"curCd": "USD", "unexpected": "discard me"}
    metric.update({f"dv01_{period}": "0" for period in periods})
    metric.update({f"dv100_{period}": "0" for period in periods})
    spreads = {period: "0" for period in periods}
    filing = factories.filing(
        cur_metrics_json=json.dumps([metric]),
        credit_sprd_risk_ig_json=json.dumps(spreads),
        credit_sprd_risk_nonig_json=json.dumps(spreads),
    )
    errors, _ = validate_filing(filing, today=date(2026, 3, 1))
    assert any("unknown keys ['unexpected']" in error for error in errors)


@pytest.mark.parametrize(
    "holding,error_fragment",
    [
        ("option_with_swap_field", "derivCat=OPT"),
        ("index_with_other_reference_field", "refInstType=indexBasket"),
        ("fixed_swap_with_floating_field", "recFixedOrFloating=Fixed"),
        ("circumstance_without_classification", "requires populated liquidity classifications"),
    ],
)
def test_fields_that_would_be_dropped_are_rejected(holding, error_fragment, factories):
    cases = {
        "option_with_swap_field": factories.option(swap_flag="N"),
        "index_with_other_reference_field": factories.option(ref_ticker="SHOULD-NOT-DROP"),
        "fixed_swap_with_floating_field": factories.swap(
            rec_fixed_or_floating="Fixed", rec_fixed_rt="0.01",
        ),
        "circumstance_without_classification": factories.equity(
            liquidity_circumstances_json=json.dumps(["DIFF_LIQUIDITY_FEATURES"]),
        ),
    }
    errors = validate_for_serialization(
        factories.config(), factories.filing(), [cases[holding]],
    )
    assert any(error_fragment in error for error in errors)


def test_liquidity_percentages_have_a_documented_tolerance(factories):
    within = factories.equity(
        liquidity_classification_json=json.dumps([
            {"category": "HLI", "pct": "99.99"},
        ])
    )
    outside = replace(
        within,
        liquidity_classification_json=json.dumps([
            {"category": "HLI", "pct": "99.989"},
        ]),
    )
    within_errors = validate_for_serialization(
        factories.config(), factories.filing(), [within],
    )
    outside_errors = validate_for_serialization(
        factories.config(), factories.filing(), [outside],
    )
    assert not any("percentages must total" in error for error in within_errors)
    assert any("percentages must total" in error for error in outside_errors)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "not-a-number"])
def test_nonfinite_and_invalid_numbers_fail_loudly(value, factories):
    filing = factories.filing(tot_assets=value)
    errors, _ = validate_filing(filing, today=date(2026, 3, 1))
    assert any("totAssets: not a valid number" in error for error in errors)
