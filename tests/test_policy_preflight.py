import hashlib
import json
from dataclasses import replace
from datetime import date

from lxml import etree

from nport.builder import NportBuilder
from nport.constants import NS_NPORT
from nport.policy import (
    FundRegistry, apply_context, derive_context, fiscal_year_end_on_or_after,
    submission_type_for,
)
from nport.preflight import run_preflight, write_release_manifest


NS = {"n": NS_NPORT}


def _registry(tmp_path, *, regime="NONE", liquidity="N", cash="N", sources=""):
    path = tmp_path / "registry.csv"
    path.write_text(
        "ticker,fiscal_year_end_mmdd,derivatives_regime,liquidity_required,"
        "cash_b2f_required,active_from,active_to,approved_by,approved_at,"
        "source_system,source_ref,required_sources\n"
        f"TST,12-31,{regime},{liquidity},{cash},2026-01-01,,Compliance,"
        f"2026-01-02T12:00:00-06:00,Internal Board Records,TICKET-1,{sources}\n",
        encoding="utf-8",
    )
    return FundRegistry.from_csv(path)


def test_calendar_derives_apples_to_apples_dates_and_form(tmp_path):
    context = derive_context(_registry(tmp_path), "TST", "2026-06")
    assert context.report_date == date(2026, 6, 30)
    assert context.fiscal_year_end == date(2026, 12, 31)
    assert context.submission_type == "NPORT-P"
    assert submission_type_for(date(2026, 4, 30), "12-31") == "NPORT-NP"
    assert fiscal_year_end_on_or_after(date(2026, 12, 31), "12-31") == date(2026, 12, 31)


def test_external_comparison_cannot_be_policy_source(tmp_path):
    path = tmp_path / "registry.csv"
    path.write_text(
        "ticker,fiscal_year_end_mmdd,derivatives_regime,liquidity_required,"
        "cash_b2f_required,active_from,active_to,approved_by,approved_at,"
        "source_system,source_ref,required_sources\n"
        "TST,12-31,NONE,N,N,2026-01-01,,Ops,2026-01-02T00:00:00Z,"
        "US Bank filing,ref,\n",
        encoding="utf-8",
    )
    try:
        FundRegistry.from_csv(path)
    except ValueError as exc:
        assert "comparison data" in str(exc)
    else:
        raise AssertionError("comparison provider was accepted as a production source")


def test_builder_omits_inapplicable_var_and_sets_confidentiality(factories, tmp_path):
    context = derive_context(_registry(tmp_path), "TST", "2026-04")
    filing = apply_context(factories.filing(rep_pd_date="2026-04-30"), context)
    root = etree.fromstring(NportBuilder(factories.config(), filing, [factories.equity()]).to_xml_bytes())
    assert root.find(".//n:submissionType", NS).text == "NPORT-NP"
    assert root.find(".//n:isConfidential", NS).text == "true"
    assert root.find(".//n:varInfo", NS) is None


def test_complete_var_and_liquidity_are_emitted(factories, tmp_path):
    context = derive_context(_registry(tmp_path, regime="VAR_RELATIVE", liquidity="Y"), "TST", "2026-06")
    filing = apply_context(factories.filing(
        median_daily_var_pct="7.2", backtesting_exceptions="0",
        median_var_ratio_pct="84.1", name_designated_index="Internal Index",
        index_identifier="INTX",
    ), context)
    holding = factories.equity(
        liquidity_classification_json='[{"category":"Highly Liquid Investment","pct":"100"}]'
    )
    root = etree.fromstring(NportBuilder(factories.config(), filing, [holding]).to_xml_bytes())
    assert root.find(".//n:medianDailyVarPct", NS).text == "7.2"
    assert root.find(".//n:medianVarRatioPct", NS).text == "84.1"
    assert root.find(".//n:fundCats/n:fundCat", NS).get("pct") == "100"


def test_preflight_verifies_internal_source_hash_and_asof(factories, tmp_path):
    registry = _registry(tmp_path, sources="custodian")
    context = derive_context(registry, "TST", "2026-06")
    filing = apply_context(factories.filing(), context)
    source = tmp_path / "custodian.csv"
    source.write_text("row\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "sources.csv"
    manifest.write_text(
        "dataset,source_system,source_path,as_of,acquired_at,sha256,record_count,approved_by\n"
        f"custodian,Internal Custody Feed,{source},2026-06-30,"
        f"2026-07-01T00:00:00Z,{digest},1,Operations\n",
        encoding="utf-8",
    )
    assert run_preflight(context, filing, [factories.equity()], manifest) == []
    source.write_text("changed\n", encoding="utf-8")
    findings = run_preflight(context, filing, [factories.equity()], manifest)
    assert any(item.code == "EVIDENCE_HASH" for item in findings)


def test_all_us_bank_inputs_are_prohibited(factories, tmp_path):
    registry = _registry(tmp_path, sources="custodian")
    context = derive_context(registry, "TST", "2026-06")
    filing = apply_context(factories.filing(), context)
    source = tmp_path / "custodian.csv"
    source.write_text("row\n", encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    custody = tmp_path / "custody.csv"
    custody.write_text(
        "dataset,source_system,source_path,as_of,acquired_at,sha256,record_count,approved_by\n"
        f"custodian,U.S. Bank Custodian Holdings,{source},2026-06-30,"
        f"2026-07-01T00:00:00Z,{digest},1,Operations\n",
        encoding="utf-8",
    )
    findings = run_preflight(context, filing, [factories.equity()], custody)
    assert any(item.code == "EVIDENCE_MANIFEST" for item in findings)

    prohibited = tmp_path / "prohibited.csv"
    prohibited.write_text(
        "dataset,source_system,source_path,as_of,acquired_at,sha256,record_count,approved_by\n"
        f"custodian,U.S. Bank Filing Comparison,{source},2026-06-30,"
        f"2026-07-01T00:00:00Z,{digest},1,Operations\n",
        encoding="utf-8",
    )
    findings = run_preflight(context, filing, [factories.equity()], prohibited)
    assert any(item.code == "EVIDENCE_MANIFEST" for item in findings)

    eaglestar = tmp_path / "eaglestar.csv"
    eaglestar.write_text(
        "dataset,source_system,source_path,as_of,acquired_at,sha256,record_count,approved_by\n"
        f"custodian,Internal Fund Accounting EagleSTAR,{source},2026-06-30,"
        f"2026-07-01T00:00:00Z,{digest},1,Operations\n",
        encoding="utf-8",
    )
    findings = run_preflight(context, filing, [factories.equity()], eaglestar)
    assert any(item.code == "EVIDENCE_MANIFEST" for item in findings)


def test_preflight_surfaces_specific_coverage_gaps(factories, tmp_path):
    context = derive_context(
        _registry(tmp_path, regime="LIMITED", liquidity="Y", cash="Y"),
        "TST", "2026-06",
    )
    filing = apply_context(factories.filing(), context)
    findings = run_preflight(context, filing, [factories.equity()], None)
    assert {item.code for item in findings} >= {
        "COVERAGE_B9", "COVERAGE_B2F", "COVERAGE_C7", "EVIDENCE_MANIFEST",
    }


def test_derivative_c3_payoff_is_na(factories):
    xml = NportBuilder(factories.config(), factories.filing(), [factories.option()]).to_xml_bytes()
    root = etree.fromstring(xml)
    assert root.find(".//n:invstOrSec/n:payoffProfile", NS).text == "N/A"


def test_test_manifest_is_never_release_eligible(factories, tmp_path):
    context = derive_context(_registry(tmp_path), "TST", "2026-06")
    xml = tmp_path / "filing.xml"
    xml.write_bytes(NportBuilder(factories.config(), factories.filing(), [factories.equity()]).to_xml_bytes())
    manifest = tmp_path / "filing.manifest.json"
    write_release_manifest(
        manifest, ticker="TST", period="2026-06", context=context,
        xml_path=xml, input_paths=[], xsd_version="1.13", findings=[],
        live_test_flag="TEST",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["environment"] == "TEST"
    assert payload["release_eligible"] is False
