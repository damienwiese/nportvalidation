"""Tests for deterministic config and holdings ingestion contracts."""

import csv

import pytest

from nport.config import parse_config, parse_filing, parse_holdings


class TestParseConfig:
    def test_sample(self, fdrs_dir):
        c = parse_config(fdrs_dir / "fund_config.txt")
        assert c.cik == "0002078265"
        assert c.reg_name == "Corgi ETF Trust I"
        assert c.series_id == "S000096625"
        assert c.signer_title == "President & PEO"

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            parse_config("/nonexistent.txt")

    def test_missing_key(self, tmp_path):
        (tmp_path / "f.txt").write_text("cik=123\n")
        with pytest.raises(ValueError, match="missing required key"):
            parse_config(tmp_path / "f.txt")

    def test_malformed_line(self, tmp_path):
        (tmp_path / "f.txt").write_text("no separator here\n")
        with pytest.raises(ValueError, match="expected key=value"):
            parse_config(tmp_path / "f.txt")

    def test_value_with_equals(self, tmp_path):
        lines = _minimal_config(ccc="AB@3=XYZ")
        (tmp_path / "f.txt").write_text("\n".join(lines))
        assert parse_config(tmp_path / "f.txt").ccc == "AB@3=XYZ"

    def test_optional_street2(self, tmp_path):
        lines = _minimal_config()
        # Remove regStreet2 line
        lines = [line for line in lines if not line.startswith("regStreet2")]
        (tmp_path / "f.txt").write_text("\n".join(lines))
        assert parse_config(tmp_path / "f.txt").reg_street2 == ""

    def test_comments_skipped(self, tmp_path):
        lines = ["# comment", "", "  # indented"] + _minimal_config()
        (tmp_path / "f.txt").write_text("\n".join(lines))
        assert parse_config(tmp_path / "f.txt").cik == "0002078265"

    def test_duplicate_key_is_rejected(self, tmp_path):
        lines = _minimal_config() + ["cik=0000000001"]
        path = tmp_path / "f.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        with pytest.raises(ValueError, match="duplicate key 'cik'"):
            parse_config(path)

    def test_unknown_key_is_rejected(self, tmp_path):
        lines = _minimal_config() + ["legacyOverride=discard-me"]
        path = tmp_path / "f.txt"
        path.write_text("\n".join(lines), encoding="utf-8")
        with pytest.raises(ValueError, match=r"unknown key\(s\): legacyOverride"):
            parse_config(path)


class TestParseFiling:
    def test_sample(self, fdrs_dir):
        f = parse_filing(fdrs_dir / "filings" / "2025-12" / "filing_data.txt")
        assert f.submission_type == "NPORT-P"
        assert f.tot_assets == "19914806.890000000000"
        assert f.mon3_redemption == ".000000000000"

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            parse_filing("/nonexistent.txt")

    def test_missing_key(self, tmp_path):
        (tmp_path / "f.txt").write_text("submissionType=NPORT-P\n")
        with pytest.raises(ValueError, match="missing required key"):
            parse_filing(tmp_path / "f.txt")

    def test_duplicate_key_is_rejected(self, tmp_path, fdrs_dir):
        source = fdrs_dir / "filings" / "2025-12" / "filing_data.txt"
        path = tmp_path / "filing_data.txt"
        path.write_text(
            source.read_text(encoding="utf-8") + "\ntotAssets=1\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate key 'totAssets'"):
            parse_filing(path)


class TestParseHoldings:
    def test_sample(self, fdrs_dir):
        h = parse_holdings(fdrs_dir / "filings" / "2025-12" / "holdings.csv")
        assert len(h) == 54
        assert h[0].name == "MercadoLibre Inc"
        assert h[0].ticker == "MELI"

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            parse_holdings("/nonexistent.csv")

    def test_missing_column(self, tmp_path):
        (tmp_path / "f.csv").write_text("name,lei\nTest,N/A\n")
        with pytest.raises(ValueError, match="missing required column"):
            parse_holdings(tmp_path / "f.csv")

    def test_empty_csv(self, tmp_path):
        hdr = "name,lei,title,cusip,isin,ticker,balance,units,curCd,valUSD,pctVal,payoffProfile,assetCat,issuerCat,invCountry,isRestrictedSec,fairValLevel,isCashCollateral,isNonCashCollateral,isLoanByFund"
        (tmp_path / "f.csv").write_text(hdr + "\n")
        assert parse_holdings(tmp_path / "f.csv") == []

    def test_na_values_preserved(self, fdrs_dir):
        credo = [h for h in parse_holdings(fdrs_dir / "filings" / "2025-12" / "holdings.csv") if "Credo" in h.name]
        assert credo[0].lei == "N/A"
        assert credo[0].cusip == "N/A"

    @pytest.mark.parametrize("extra_header,error", [
        ("unexpectedColumn", "unknown columns: unexpectedColumn"),
        ("name", "duplicate columns: name"),
    ])
    def test_invalid_headers_fail_loudly(
        self, tmp_path, fdrs_dir, extra_header, error,
    ):
        source = fdrs_dir / "filings" / "2025-12" / "holdings.csv"
        lines = source.read_text(encoding="utf-8").splitlines()
        lines[0] += f",{extra_header}"
        path = tmp_path / "holdings.csv"
        path.write_text("\n".join(lines), encoding="utf-8")
        with pytest.raises(ValueError, match=error):
            parse_holdings(path)

    def test_split_satellite_orphan_is_rejected(self, tmp_path, fdrs_dir):
        base = _make_split_holdings(tmp_path, fdrs_dir)
        (tmp_path / "debt_securities.csv").write_text(
            "holdingId,couponKind\nNOT-IN-BASE,Fixed\n", encoding="utf-8",
        )
        with pytest.raises(ValueError, match="holdingId 'NOT-IN-BASE' not in"):
            parse_holdings(base)

    def test_split_satellite_conflict_is_rejected(self, tmp_path, fdrs_dir):
        base = _make_split_holdings(tmp_path, fdrs_dir)
        (tmp_path / "derivatives.csv").write_text(
            "holdingId,ticker\nH-1,CONFLICT\n", encoding="utf-8",
        )
        with pytest.raises(ValueError, match="conflicting value.*ticker"):
            parse_holdings(base)


def _minimal_config(**overrides):
    """Return lines for a minimal valid fund_config.txt."""
    defaults = {
        "cik": "0002078265", "ccc": "XXXXXXXX", "regName": "Trust",
        "regFileNumber": "811-24117", "regCik": "0002078265",
        "regLei": "529900HSQC73ZP7RGT16", "regStreet1": "123 Main",
        "regStreet2": "Ste 1", "regCity": "SF", "regState": "US-CA",
        "regCountry": "US", "regZipOrPostalCode": "94104",
        "regPhone": "555-1234", "seriesName": "Fund",
        "seriesId": "S000096625", "seriesLei": "529900Y4TPD7LE3K2C21",
        "classId": "C000265520", "signerOrg": "Trust",
        "signerName": "Jane", "signerTitle": "CEO",
    }
    defaults.update(overrides)
    return [f"{k}={v}" for k, v in defaults.items()]


def _make_split_holdings(tmp_path, fdrs_dir):
    """Copy the canonical flat fixture and add stable holding IDs."""
    source = fdrs_dir / "filings" / "2025-12" / "holdings.csv"
    with source.open(newline="", encoding="utf-8") as file:
        rows = list(csv.reader(file))
    rows[0].insert(0, "holdingId")
    for index, row in enumerate(rows[1:], 1):
        row.insert(0, f"H-{index}")
    target = tmp_path / "holdings.csv"
    with target.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(rows)
    return target
