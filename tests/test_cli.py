"""CLI integration tests."""

import hashlib
import shutil

import pytest

import nport.cli as climod
from nport.cli import main


class TestBuildAllFunds:
    def test_no_fund_builds_every_fund_with_filing(self, monkeypatch, tmp_path):
        funds = tmp_path / "funds"
        for t in ("aaa", "bbb"):
            (funds / t / "filings" / "2026-06").mkdir(parents=True)
            (funds / t / "fund_config.txt").write_text("x")
            (funds / t / "filings" / "2026-06" / "filing_data.txt").write_text("x")
        (funds / "nofiling").mkdir()                       # no period filing → skipped
        (funds / "nofiling" / "fund_config.txt").write_text("x")
        monkeypatch.setattr(climod, "_DEFAULT_FUNDS_DIR", funds)
        seen = []
        monkeypatch.setattr(climod, "_ingest_one", lambda args: seen.append(args.pos[0]))
        main(["build", "2026-06"])
        assert sorted(seen) == ["AAA", "BBB"]

    def test_named_fund_routes_to_single(self, monkeypatch):
        called = {}
        monkeypatch.setattr(climod, "_ingest_one", lambda args: called.setdefault("pos", args.pos))
        main(["build", "fdrs", "2026-06"])
        assert called["pos"] == ["fdrs", "2026-06"]


def _fdrs_paths(fdrs_dir):
    return {
        "config": str(fdrs_dir / "fund_config.txt"),
        "filing": str(fdrs_dir / "filings" / "2025-12" / "filing_data.txt"),
        "holdings": str(fdrs_dir / "filings" / "2025-12" / "holdings.csv"),
    }


def _evidence_args(tmp_path, holdings_path):
    registry = tmp_path / "registry.csv"
    registry.write_text(
        "ticker,fiscal_year_end_mmdd,derivatives_regime,liquidity_required,"
        "cash_b2f_required,active_from,active_to,approved_by,approved_at,"
        "source_system,source_ref,required_sources\n"
        "FDRS,12-31,NONE,N,N,2025-01-01,,Compliance,2025-01-02T00:00:00Z,"
        "Internal Test Governance,TEST-1,canonical_holdings\n",
        encoding="utf-8",
    )
    # Source evidence must not point at the repository's existing canonical
    # files; those are deliberately quarantined. This copied fixture stands in
    # for an independently delivered test input.
    independent_source = tmp_path / "independent_positions_fixture.csv"
    shutil.copyfile(holdings_path, independent_source)
    digest = hashlib.sha256(independent_source.read_bytes()).hexdigest()
    manifest = tmp_path / "sources.csv"
    manifest.write_text(
        "dataset,source_system,source_path,as_of,acquired_at,sha256,record_count,approved_by\n"
        f"canonical_holdings,Synthetic Test Input,{independent_source},2025-12-31,"
        f"2026-01-01T00:00:00Z,{digest},54,Test Reviewer\n",
        encoding="utf-8",
    )
    return ["--account", "FDRS", "--registry", str(registry),
            "--source-manifest", str(manifest)]


class TestGenerate:
    def test_succeeds(self, fdrs_dir, tmp_path):
        p = _fdrs_paths(fdrs_dir)
        out = tmp_path / "out.xml"
        main(["generate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"],
              "--output", str(out), "--skip-schema-check",
              *_evidence_args(tmp_path, fdrs_dir / "filings" / "2025-12" / "holdings.csv")])
        assert out.exists()
        assert "edgarSubmission" in out.read_text()

    def test_verbose(self, fdrs_dir, tmp_path, capsys):
        p = _fdrs_paths(fdrs_dir)
        main(["generate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"],
              "--output", str(tmp_path / "out.xml"),
              "--skip-schema-check", "--verbose",
              *_evidence_args(tmp_path, fdrs_dir / "filings" / "2025-12" / "holdings.csv")])
        assert "54 holdings" in capsys.readouterr().out

    def test_creates_parent_dirs(self, fdrs_dir, tmp_path):
        p = _fdrs_paths(fdrs_dir)
        out = tmp_path / "a" / "b" / "out.xml"
        main(["generate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"],
              "--output", str(out), "--skip-schema-check", "--skip-validation",
              *_evidence_args(tmp_path, fdrs_dir / "filings" / "2025-12" / "holdings.csv")])
        assert out.exists()

    @pytest.mark.parametrize("missing", ["config", "filing", "holdings"])
    def test_missing_file_exits(self, fdrs_dir, tmp_path, missing):
        paths = _fdrs_paths(fdrs_dir)
        paths[missing] = "/nonexistent"
        with pytest.raises(SystemExit):
            main(["generate", "--config", paths["config"],
                  "--filing", paths["filing"], "--holdings", paths["holdings"],
                  "--output", str(tmp_path / "out.xml"), "--skip-schema-check",
                  *_evidence_args(tmp_path, fdrs_dir / "filings" / "2025-12" / "holdings.csv")])


class TestValidate:
    def test_passes(self, fdrs_dir, capsys):
        p = _fdrs_paths(fdrs_dir)
        main(["validate", "--config", p["config"],
              "--filing", p["filing"], "--holdings", p["holdings"]])
        assert "PASSED" in capsys.readouterr().out


class TestNoCommand:
    def test_exits(self):
        with pytest.raises(SystemExit):
            main([])


# ── LIVE gate ─────────────────────────────────────────────────


def test_live_gate_blocks_on_review_flag(tmp_path, monkeypatch):
    """A fund with an unresolved reconciliation REVIEW flag is blocked from LIVE."""
    from nport import cli
    monkeypatch.setattr(cli, "_MASTER_DIR", tmp_path)
    (tmp_path / "reconciliation_2026-06.csv").write_text(
        "check,fund,source_a,value_a,source_b,value_b,diff,flag\n"
        "netAssets,BRZX,custodian,338695.50,NAV@20260624,564492.50,-225797.00,REVIEW\n"
        "netAssets,ACLZ,custodian,243854.00,NAV@20260624,243854.26,-0.26,\n",
        encoding="utf-8",
    )
    assert cli._live_gate_reasons("BRZX", "2026-06")          # blocked
    assert cli._live_gate_reasons("ACLZ", "2026-06") == []    # clean → clear to file


def test_live_gate_blocks_when_no_report(tmp_path, monkeypatch):
    """No reconciliation report at all → LIVE can't be verified → blocked."""
    from nport import cli
    monkeypatch.setattr(cli, "_MASTER_DIR", tmp_path)
    reasons = cli._live_gate_reasons("FDRS", "2026-06")
    assert reasons and "reconciliation report" in reasons[0]
