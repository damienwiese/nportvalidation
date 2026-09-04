import hashlib
import json
from dataclasses import replace
from datetime import date

import pytest
from lxml import etree

from nport.builder import NportBuilder
from nport.constants import NS_NPORT
from nport.policy import (
    apply_context,
    derive_context_from_config,
    fiscal_year_end_on_or_after,
    report_date_for_period,
    submission_type_for,
)
from nport.preflight import run_preflight, write_release_manifest

NS = {"n": NS_NPORT}


def test_report_period_requires_canonical_year_month():
    assert report_date_for_period("2026-07") == date(2026, 7, 31)
    for invalid in ("2026-7", "26-07", "2026/07", "2026-13"):
        with pytest.raises(ValueError, match="period must be YYYY-MM"):
            report_date_for_period(invalid)


def _context(factories, period="2026-06", *, regime="NONE", liquidity="N", cash="N", sources=""):
    config = replace(
        factories.config(),
        fiscal_year_end_mmdd="12-31",
        derivatives_regime_policy=regime,
        liquidity_required=liquidity,
        cash_b2f_required=cash,
        policy_effective_from="2026-01-01",
        policy_effective_to="",
        policy_approved_by="Compliance",
        policy_approved_at="2026-01-02T12:00:00-06:00",
        policy_source_ref="TICKET-1",
        required_sources=sources,
    )
    return config, derive_context_from_config(config, "TST", period, "fund_config.txt")


def test_calendar_derives_dates_and_form(factories):
    _, context = _context(factories)
    assert context.report_date == date(2026, 6, 30)
    assert context.fiscal_year_end == date(2026, 12, 31)
    assert context.submission_type == "NPORT-P"
    assert submission_type_for(date(2026, 4, 30), "12-31") == "NPORT-NP"
    assert fiscal_year_end_on_or_after(date(2026, 12, 31), "12-31") == date(2026, 12, 31)


def test_builder_applies_config_policy(factories):
    config, context = _context(factories, "2026-04")
    filing = apply_context(factories.filing(rep_pd_date="2026-04-30"), context)
    root = etree.fromstring(NportBuilder(config, filing, [factories.equity()]).to_xml_bytes())
    assert root.find(".//n:submissionType", NS).text == "NPORT-NP"
    assert root.find(".//n:isConfidential", NS).text == "true"
    assert root.find(".//n:varInfo", NS) is None


def test_complete_var_and_liquidity_are_emitted(factories):
    config, context = _context(factories, regime="VAR_RELATIVE", liquidity="Y")
    filing = apply_context(factories.filing(
        median_daily_var_pct="7.2", backtesting_exceptions="0",
        median_var_ratio_pct="84.1", name_designated_index="Internal Index",
        index_identifier="INTX",
        ), context)
    holding = factories.equity(
        liquidity_classification_json='[{"category":"HLI","pct":"100"}]'
    )
    root = etree.fromstring(NportBuilder(config, filing, [holding]).to_xml_bytes())
    assert root.find(".//n:medianDailyVarPct", NS).text == "7.2"
    assert root.find(".//n:fundCats/n:fundCat", NS).get("pct") == "100"


def test_preflight_verifies_source_hash_and_asof(factories, tmp_path):
    _, context = _context(factories, sources="positions")
    filing = apply_context(factories.filing(), context)
    source = tmp_path / "positions.csv"
    source.write_text("row\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "sources.csv"
    manifest.write_text(
        "dataset,source_system,source_path,as_of,acquired_at,sha256,record_count,approved_by\n"
        f"positions,Internal Positions,{source},2026-06-30,2026-07-01T00:00:00Z,{digest},1,Operations\n",
        encoding="utf-8",
    )
    assert run_preflight(context, filing, [factories.equity()], manifest) == []
    source.write_text("changed\n", encoding="utf-8")
    assert any(item.code == "EVIDENCE_HASH" for item in run_preflight(context, filing, [factories.equity()], manifest))


def test_preflight_surfaces_coverage_gaps(factories):
    _, context = _context(factories, regime="LIMITED", liquidity="Y", cash="Y")
    filing = apply_context(factories.filing(), context)
    findings = run_preflight(context, filing, [factories.equity()])
    assert {item.code for item in findings} >= {"COVERAGE_B9", "COVERAGE_B2F", "COVERAGE_C7"}


def test_test_manifest_is_never_release_eligible(factories, tmp_path):
    config, context = _context(factories)
    xml = tmp_path / "filing.xml"
    xml.write_bytes(NportBuilder(config, apply_context(factories.filing(), context), [factories.equity()]).to_xml_bytes())
    manifest = tmp_path / "filing.manifest.json"
    write_release_manifest(
        manifest, ticker="TST", period="2026-06", context=context, xml_path=xml,
        input_paths=[], xsd_version="1.13", findings=[], live_test_flag="TEST",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["environment"] == "TEST"
    assert payload["release_eligible"] is False
