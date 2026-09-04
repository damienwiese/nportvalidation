"""Unit tests for extended builder — debt, derivatives, conditionals, risk metrics."""

import json

import pytest
from lxml import etree

from nport.builder import NportBuilder
from nport.constants import NS_NPORT
from nport.models import FilingData, FundConfig, Holding

NS = {"n": NS_NPORT}


def _config():
    return FundConfig(
        cik="0002078265", ccc="XXXXXXXX", reg_name="Corgi ETF Trust I",
        reg_file_number="811-24117", reg_cik="0002078265",
        reg_lei="529900HSQC73ZP7RGT16", reg_street1="425 Bush St.",
        reg_street2="Suite 500", reg_city="San Francisco",
        reg_state="US-CA", reg_country="US", reg_zip="94104",
        reg_phone="855-552-6744", series_name="Test Fund",
        series_id="S000096625", series_lei="529900Y4TPD7LE3K2C21",
        class_id="C000265520", signer_org="Corgi ETF Trust I",
        signer_name="Emily Yuan", signer_title="President & PEO",
    )


def _filing(**overrides):
    defaults = dict(
        submission_type="NPORT-P", live_test_flag="TEST",
        rep_pd_end="2025-12-31", rep_pd_date="2025-12-31",
        is_final_filing="N", date_signed="2026-02-24",
        tot_assets="19914806.89", tot_liabs="9903037.79",
        net_assets="10011769.10", assets_attr_misc_sec="0",
        assets_invested="0", amt_pay_one_yr_banks_borr="0",
        amt_pay_one_yr_ctrld_comp="0", amt_pay_one_yr_oth_affil="0",
        amt_pay_one_yr_other="0", amt_pay_aft_one_yr_banks_borr="0",
        amt_pay_aft_one_yr_ctrld_comp="0", amt_pay_aft_one_yr_oth_affil="0",
        amt_pay_aft_one_yr_other="0", delay_deliv="0", stand_by_commit="0",
        liquid_pref="0", is_non_cash_collateral="N",
        rtn1="N/A", rtn2="N/A", rtn3="-1.34",
        net_realized_gain_mon1="0", net_unrealized_appr_mon1="0",
        net_realized_gain_mon2="0", net_unrealized_appr_mon2="0",
        net_realized_gain_mon3="0", net_unrealized_appr_mon3="0",
        mon1_sales="0", mon1_redemption="0", mon1_reinvestment="0",
        mon2_sales="0", mon2_redemption="0", mon2_reinvestment="0",
        mon3_sales="0", mon3_redemption="0", mon3_reinvestment="0",
        name_designated_index="N/A", index_identifier="N/A",
    )
    defaults.update(overrides)
    return FilingData(**defaults)


def _holding(**overrides):
    defaults = dict(
        name="Test Stock", lei="549300DKPDN9M5S8GB14",
        title="Test Stock", cusip="58733R102", isin="US58733R1023",
        ticker="TST", balance="100", units="NS", cur_cd="USD",
        val_usd="10000.00", pct_val="1.00", payoff_profile="Long",
        asset_cat="EC", issuer_cat="CORP", inv_country="US",
        is_restricted_sec="N", fair_val_level="1",
        is_cash_collateral="N", is_non_cash_collateral="N",
        is_loan_by_fund="N",
    )
    defaults.update(overrides)
    return Holding(**defaults)


def _build_single(holding, filing_overrides=None):
    """Build XML with a single holding and return the invstOrSec element."""
    f = _filing(**(filing_overrides or {}))
    xml = NportBuilder(_config(), f, [holding]).to_xml_bytes()
    root = etree.fromstring(xml)
    return root.find(".//n:invstOrSec", NS)


# ── Equity unchanged ──────────────────────────────────────


class TestEquityUnchanged:
    def test_no_debt_sec(self):
        sec = _build_single(_holding())
        assert sec.find("n:debtSec", NS) is None

    def test_no_derivative_info(self):
        sec = _build_single(_holding())
        assert sec.find("n:derivativeInfo", NS) is None

    def test_has_cur_cd(self):
        sec = _build_single(_holding())
        assert sec.find("n:curCd", NS) is not None
        assert sec.find("n:currencyConditional", NS) is None

    def test_has_asset_cat(self):
        sec = _build_single(_holding())
        assert sec.find("n:assetCat", NS).text == "EC"
        assert sec.find("n:assetConditional", NS) is None

    def test_has_issuer_cat(self):
        sec = _build_single(_holding())
        assert sec.find("n:issuerCat", NS).text == "CORP"
        assert sec.find("n:issuerConditional", NS) is None


# ── Debt Securities ───────────────────────────────────────


class TestDebtSec:
    def test_emitted(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="Fixed",
            annualized_rt="5.25",
            is_default="N",
            are_intrst_pmnts_in_arrs="N",
            is_paid_kind="N",
            asset_cat="DBT",
        )
        sec = _build_single(h)
        ds = sec.find("n:debtSec", NS)
        assert ds is not None
        assert ds.find("n:maturityDt", NS).text == "2030-12-31"
        assert ds.find("n:couponKind", NS).text == "Fixed"
        assert ds.find("n:annualizedRt", NS).text == "5.25"

    def test_explicit_debt_flags(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="Fixed",
            annualized_rt="5.25",
            is_default="N",
            are_intrst_pmnts_in_arrs="N",
            is_paid_kind="N",
        )
        sec = _build_single(h)
        ds = sec.find("n:debtSec", NS)
        assert ds.find("n:isDefault", NS).text == "N"
        assert ds.find("n:areIntrstPmntsInArrs", NS).text == "N"
        assert ds.find("n:isPaidKind", NS).text == "N"

    def test_empty_flags_are_not_invented(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="Floating",
            annualized_rt="3.50",
        )
        with pytest.raises(ValueError, match="canonical model is not serializable"):
            _build_single(h)


# ── Option Derivative ─────────────────────────────────────


class TestOptionDerivative:
    def _option_holding(self, **extra):
        defaults = dict(
            deriv_cat="OPT",
            payoff_profile="N/A",
            counterparty_name="Goldman Sachs",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call",
            written_or_pur="Purchased",
            share_no="100",
            exercise_price="150.00",
            exercise_price_cur_cd="USD",
            exp_dt="2026-06-30",
            delta="0.65",
            unrealized_appr="500.00",
            ref_inst_type="otherRefInst",
            ref_issuer_name="Apple Inc",
            ref_issue_title="Apple Inc Common Stock",
            ref_cusip="037833100",
            ref_isin="US0378331005",
            ref_ticker="AAPL",
            asset_cat="DE",
            cusip="N/A",
        )
        defaults.update(extra)
        return _holding(**defaults)

    def test_emitted(self):
        sec = _build_single(self._option_holding())
        di = sec.find("n:derivativeInfo", NS)
        assert di is not None
        opt = di.find("n:optionSwaptionWarrantDeriv", NS)
        assert opt is not None

    def test_put_or_call(self):
        sec = _build_single(self._option_holding())
        opt = sec.find(".//n:optionSwaptionWarrantDeriv", NS)
        assert opt.find("n:putOrCall", NS).text == "Call"
        assert opt.find("n:writtenOrPur", NS).text == "Purchased"

    def test_exercise_price(self):
        sec = _build_single(self._option_holding())
        opt = sec.find(".//n:optionSwaptionWarrantDeriv", NS)
        assert opt.find("n:exercisePrice", NS).text == "150.00"
        assert opt.find("n:exercisePriceCurCd", NS).text == "USD"

    def test_exp_dt_and_delta(self):
        sec = _build_single(self._option_holding())
        opt = sec.find(".//n:optionSwaptionWarrantDeriv", NS)
        assert opt.find("n:expDt", NS).text == "2026-06-30"
        assert opt.find("n:delta", NS).text == "0.65"

    def test_counterparty(self):
        sec = _build_single(self._option_holding())
        # counterparties is the repeating element with direct children.
        cp = sec.find(".//n:counterparties", NS)
        assert cp is not None
        assert cp.find("n:counterpartyName", NS).text == "Goldman Sachs"
        assert cp.find("n:counterpartyLei", NS).text == "W22LROWP2IHZNBB6K528"

    def test_deriv_cat_attribute(self):
        """derivCat is an XML attribute on the derivative element."""
        sec = _build_single(self._option_holding())
        opt = sec.find(".//n:optionSwaptionWarrantDeriv", NS)
        assert opt.get("derivCat") == "OPT"

    def test_ref_instrument_other(self):
        sec = _build_single(self._option_holding())
        ori = sec.find(".//n:otherRefInst", NS)
        assert ori is not None
        assert ori.find("n:issuerName", NS).text == "Apple Inc"
        ids = ori.find("n:identifiers", NS)
        assert ids.find("n:cusip", NS).get("value") == "037833100"
        assert ids.find("n:isin", NS).get("value") == "US0378331005"
        assert ids.find("n:ticker", NS).get("value") == "AAPL"

    def test_unrealized_appr(self):
        sec = _build_single(self._option_holding())
        opt = sec.find(".//n:optionSwaptionWarrantDeriv", NS)
        assert opt.find("n:unrealizedAppr", NS).text == "500.00"


# ── Swap Derivative ───────────────────────────────────────


class TestSwapDerivative:
    def _swap_holding(self, **extra):
        defaults = dict(
            deriv_cat="SWP",
            payoff_profile="N/A",
            counterparty_name="JP Morgan",
            counterparty_lei="8I5DZWZKVSZI1NUHU748",
            unrealized_appr="1234.56",
            swap_flag="N",
            termination_dt="2027-03-31",
            notional_amt="1000000.00",
            swap_cur_cd="USD",
            upfront_pmnt="0",
            pmnt_cur_cd="USD",
            upfront_rcpt="0",
            rcpt_cur_cd="USD",
            rec_fixed_or_floating="Floating",
            rec_floating_rt_index="USD-SOFR-OIS",
            rec_floating_rt_spread="0.50",
            rec_pmnt_amt="0",
            rec_cur_cd="USD",
            rec_rate_tenor="Day",
            rec_rate_unit="1",
            rec_reset_dt="Day",
            rec_reset_unit="1",
            pmnt_fixed_or_floating="Fixed",
            pmnt_fixed_rt="0.05",
            pmnt_pmnt_amt="0",
            pmnt_cur_cd_leg="USD",
            ref_inst_type="indexBasket",
            ref_index_name="S&P 500",
            ref_index_identifier="SPX",
            asset_cat="DE",
            cusip="N/A",
        )
        defaults.update(extra)
        return _holding(**defaults)

    def test_emitted(self):
        sec = _build_single(self._swap_holding())
        di = sec.find("n:derivativeInfo", NS)
        assert di is not None
        swap = di.find("n:swapDeriv", NS)
        assert swap is not None

    def test_deriv_cat_attribute(self):
        """derivCat is an attribute on swapDeriv."""
        sec = _build_single(self._swap_holding())
        swap = sec.find(".//n:swapDeriv", NS)
        assert swap.get("derivCat") == "SWP"

    def test_counterparty_structure(self):
        """counterparties is the repeating element."""
        sec = _build_single(self._swap_holding())
        cp = sec.find(".//n:counterparties", NS)
        assert cp is not None
        assert cp.find("n:counterpartyName", NS).text == "JP Morgan"
        assert cp.find("n:counterpartyLei", NS).text == "8I5DZWZKVSZI1NUHU748"

    def test_termination_and_notional(self):
        sec = _build_single(self._swap_holding())
        swap = sec.find(".//n:swapDeriv", NS)
        assert swap.find("n:terminationDt", NS).text == "2027-03-31"
        assert swap.find("n:notionalAmt", NS).text == "1000000.00"

    def test_floating_receive_leg_attributes(self):
        """The floating leg uses schema-defined attributes."""
        sec = _build_single(self._swap_holding())
        fl = sec.find(".//n:floatingRecDesc", NS)
        assert fl is not None
        assert fl.get("fixedOrFloating") == "Floating"
        assert fl.get("floatingRtIndex") == "USD-SOFR-OIS"
        assert fl.get("floatingRtSpread") == "0.50"
        assert fl.get("curCd") == "USD"

    def test_floating_receive_leg_rt_reset_tenor(self):
        """rtResetTenor uses schema-defined attributes."""
        sec = _build_single(self._swap_holding())
        rt = sec.find(".//n:rtResetTenor", NS)
        assert rt is not None
        assert rt.get("rateTenor") == "Day"
        assert rt.get("rateTenorUnit") == "1"

    def test_fixed_pay_leg_attributes(self):
        """The fixed leg uses schema-defined attributes."""
        sec = _build_single(self._swap_holding())
        fp = sec.find(".//n:fixedPmntDesc", NS)
        assert fp is not None
        assert fp.get("fixedOrFloating") == "Fixed"
        assert fp.get("fixedRt") == "0.05"
        assert fp.get("curCd") == "USD"

    def test_swap_element_order(self):
        """Swap children follow XSD element order."""
        sec = _build_single(self._swap_holding())
        swap = sec.find(".//n:swapDeriv", NS)
        children = [c.tag.split("}")[-1] if "}" in c.tag else c.tag for c in swap]
        # XSD: counterparties → descRefInstrmnt → swapFlag → [legs] →
        #      terminationDt → upfrontPmnt → ... → notionalAmt → curCd → unrealizedAppr
        cp_idx = children.index("counterparties")
        ref_idx = children.index("descRefInstrmnt")
        flag_idx = children.index("swapFlag")
        term_idx = children.index("terminationDt")
        appr_idx = children.index("unrealizedAppr")
        assert cp_idx < ref_idx < flag_idx < term_idx < appr_idx

    def test_ref_instrument_index(self):
        sec = _build_single(self._swap_holding())
        ib = sec.find(".//n:indexBasketInfo", NS)
        assert ib is not None
        assert ib.find("n:indexName", NS).text == "S&P 500"
        assert ib.find("n:indexIdentifier", NS).text == "SPX"

    def test_unrealized_appr(self):
        sec = _build_single(self._swap_holding())
        swap = sec.find(".//n:swapDeriv", NS)
        assert swap.find("n:unrealizedAppr", NS).text == "1234.56"


# ── Conditional Elements ──────────────────────────────────


class TestIssuerConditional:
    def test_emitted(self):
        h = _holding(issuer_cat="OTHER", issuer_conditional_desc="Private fund")
        sec = _build_single(h)
        ic = sec.find("n:issuerConditional", NS)
        assert ic is not None
        assert ic.get("desc") == "Private fund"
        assert ic.get("issuerCat") == "OTHER"
        assert sec.find("n:issuerCat", NS) is None

    def test_not_emitted_when_empty(self):
        h = _holding()
        sec = _build_single(h)
        assert sec.find("n:issuerConditional", NS) is None
        assert sec.find("n:issuerCat", NS) is not None


class TestAssetConditional:
    def test_emitted(self):
        h = _holding(asset_cat="OTHER", asset_conditional_desc="FLEX option")
        sec = _build_single(h)
        ac = sec.find("n:assetConditional", NS)
        assert ac is not None
        assert ac.get("desc") == "FLEX option"
        assert ac.get("assetCat") == "OTHER"
        assert sec.find("n:assetCat", NS) is None


class TestCurrencyConditional:
    def test_emitted(self):
        h = _holding(exchange_rt="1.25")
        sec = _build_single(h)
        cc = sec.find("n:currencyConditional", NS)
        assert cc is not None
        assert cc.get("curCd") == "USD"
        assert cc.get("exchangeRt") == "1.25"
        assert sec.find("n:curCd", NS) is None


# ── Other Identifier ──────────────────────────────────────


class TestOtherIdentifier:
    def test_emitted(self):
        h = _holding(other_desc="INTERNAL_ID", other_value="ABC123")
        sec = _build_single(h)
        ids = sec.find("n:identifiers", NS)
        other = ids.find("n:other", NS)
        assert other is not None
        assert other.get("otherDesc") == "INTERNAL_ID"
        assert other.get("value") == "ABC123"


# ── Risk Metrics ──────────────────────────────────────────


class TestRiskMetrics:
    @staticmethod
    def _payloads():
        periods = ("3month", "1year", "5year", "10year", "30year")
        metric = {"curCd": "USD"}
        metric.update({f"dv01_{period}": "100" for period in periods})
        metric.update({f"dv100_{period}": "200" for period in periods})
        spread = {period: "0" for period in periods}
        return [metric], spread

    def test_cur_metrics_emitted(self):
        metrics, spread = self._payloads()
        f = _filing(
            cur_metrics_json=json.dumps(metrics),
            credit_sprd_risk_ig_json=json.dumps(spread),
            credit_sprd_risk_nonig_json=json.dumps(spread),
        )
        xml = NportBuilder(_config(), f, [_holding()]).to_xml_bytes()
        root = etree.fromstring(xml)
        cm = root.find(".//n:curMetrics", NS)
        assert cm is not None
        cur_metric = cm.find("n:curMetric", NS)
        assert cur_metric.find("n:curCd", NS).text == "USD"
        dv01 = cur_metric.find("n:intrstRtRiskdv01", NS)
        assert dv01 is not None
        assert dv01.get("period3Mon") == "100"
        dv100 = cur_metric.find("n:intrstRtRiskdv100", NS)
        assert dv100 is not None
        assert dv100.get("period3Mon") == "200"

    def test_credit_spread_ig(self):
        metrics, non_ig = self._payloads()
        ig = {"3month": "10", "1year": "20", "5year": "30", "10year": "40", "30year": "50"}
        f = _filing(
            cur_metrics_json=json.dumps(metrics),
            credit_sprd_risk_ig_json=json.dumps(ig),
            credit_sprd_risk_nonig_json=json.dumps(non_ig),
        )
        xml = NportBuilder(_config(), f, [_holding()]).to_xml_bytes()
        root = etree.fromstring(xml)
        ig_el = root.find(".//n:creditSprdRiskInvstGrade", NS)
        assert ig_el is not None
        assert ig_el.get("period3Mon") == "10"
        assert ig_el.get("period1Yr") == "20"

    def test_credit_spreads_are_emitted_from_explicit_inputs(self):
        metrics, spread = self._payloads()
        f = _filing(
            cur_metrics_json=json.dumps(metrics),
            credit_sprd_risk_ig_json=json.dumps(spread),
            credit_sprd_risk_nonig_json=json.dumps(spread),
        )
        xml = NportBuilder(_config(), f, [_holding()]).to_xml_bytes()
        root = etree.fromstring(xml)
        ig_el = root.find(".//n:creditSprdRiskInvstGrade", NS)
        nig_el = root.find(".//n:creditSprdRiskNonInvstGrade", NS)
        assert ig_el is not None
        assert nig_el is not None
        assert ig_el.get("period3Mon") == "0"
        assert nig_el.get("period3Mon") == "0"

    def test_no_metrics_when_empty(self):
        f = _filing()
        xml = NportBuilder(_config(), f, [_holding()]).to_xml_bytes()
        root = etree.fromstring(xml)
        assert root.find(".//n:curMetrics", NS) is None


# ── Monthly derivative return categories ─────────────────


class TestMonthlyReturnCategories:
    def test_validated_input_months_map_to_instrument_xml_months(self):
        def month(realized, unrealized):
            return {
                "netRealizedGain": realized,
                "netUnrealizedAppr": unrealized,
            }

        payload = {
            "equityContracts": {
                "mon1": month("1", "2"),
                "mon2": month("3", "4"),
                "mon3": month("5", "6"),
                "optionCategory": {
                    "mon1": month("7", "8"),
                    "mon2": month("9", "10"),
                    "mon3": month("11", "12"),
                },
            }
        }
        filing = _filing(monthly_return_categories_json=json.dumps(payload))

        xml = NportBuilder(_config(), filing, [_holding()]).to_xml_bytes()
        root = etree.fromstring(xml)

        contract = root.find(".//n:monthlyReturnCats/n:equityContracts", NS)
        assert contract.find("n:mon1", NS).get("netRealizedGain") == "1"
        instrument = contract.find("n:optionCategory", NS)
        assert instrument.find("n:instrMon1", NS).get("netRealizedGain") == "7"
        assert instrument.find("n:instrMon3", NS).get("netUnrealizedAppr") == "12"


# ── XSD Element Order ─────────────────────────────────────


class TestElementOrder:
    """Verify that elements appear in the correct XSD-mandated order."""

    def test_holding_order_with_debt(self):
        h = _holding(
            maturity_dt="2030-01-01", coupon_kind="Fixed", annualized_rt="3.0",
            is_default="N", are_intrst_pmnts_in_arrs="N", is_paid_kind="N",
        )
        sec = _build_single(h)
        children = [c.tag.split("}")[-1] if "}" in c.tag else c.tag for c in sec]
        # debtSec must come after fairValLevel and before securityLending
        fair_idx = children.index("fairValLevel")
        debt_idx = children.index("debtSec")
        sl_idx = children.index("securityLending")
        assert fair_idx < debt_idx < sl_idx

    def test_holding_order_with_derivative(self):
        h = _holding(
            deriv_cat="OPT", counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Put", written_or_pur="Written",
            share_no="100", exercise_price="50",
            exercise_price_cur_cd="USD",
            exp_dt="2026-01-01", delta="-0.35",
            unrealized_appr="-100",
            ref_inst_type="otherRefInst",
            ref_issuer_name="Test", ref_issue_title="Test",
            ref_ticker="TEST",
            cusip="N/A",
        )
        sec = _build_single(h)
        children = [c.tag.split("}")[-1] if "}" in c.tag else c.tag for c in sec]
        fair_idx = children.index("fairValLevel")
        deriv_idx = children.index("derivativeInfo")
        sl_idx = children.index("securityLending")
        assert fair_idx < deriv_idx < sl_idx
