"""Contract tests for every active per-fund reference configuration."""

import csv
from collections import Counter
from pathlib import Path

import pytest

from nport.config import parse_config
from nport.input_validation import validate_config
from nport.input_workbook import _expected_sheet_names, _fund_entries

_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_PATHS = tuple(sorted((_ROOT / "data" / "funds").glob("*/fund_config.txt")))
_UNIVERSE_PATH = _ROOT / "data" / "funds" / "fund_universe.csv"


def _fund_universe() -> list[dict[str, str]]:
    with _UNIVERSE_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == ["fund", "category"]
        return list(reader)


def test_fund_universe_is_complete_deterministic_and_contains_active_funds():
    rows = _fund_universe()
    funds = [row["fund"] for row in rows]
    active = {path.parent.name.upper() for path in _CONFIG_PATHS}
    assert len(funds) == 197
    assert len(funds) == len(set(funds))
    assert all(fund.isascii() and fund.isalnum() for fund in funds)
    assert active <= set(funds)
    assert not {"BOND_FUND", "BUFFERED_ETF", "LEVERAGED_ETF"} & set(funds)
    counts = Counter(row["category"] for row in rows)
    assert counts == {
        "Thematic": 30,
        "2x Leveraged": 125,
        "Structured Buffer": 36,
        "Fixed Income": 6,
    }
    assert (funds[0], funds[29]) == ("AV", "YUNG")
    assert (funds[30], funds[154]) == ("SK", "EO")
    assert (funds[155], funds[190]) == ("HAUG", "QJN")
    assert funds[191:] == ["CBIL", "CGOV", "CUST", "CIEI", "CIVG", "CHYG"]


def test_fund_universe_drives_the_complete_workbook_sheet_contract():
    rows = _fund_universe()
    funds = [row["fund"] for row in rows]
    entries = _fund_entries(_ROOT / "data" / "funds")
    assert [fund for fund, _config, _category in entries] == funds
    assert sum(config is not None for _fund, config, _category in entries) == 16
    assert len(_expected_sheet_names(funds)) == 592


def test_active_fund_registry_is_nonempty_and_directory_names_are_unique():
    assert _CONFIG_PATHS, "data/funds must contain active fund configurations"
    names = [path.parent.name.lower() for path in _CONFIG_PATHS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("path", _CONFIG_PATHS, ids=lambda path: path.parent.name)
def test_active_fund_configs_are_not_synthetic_fixtures(path):
    text = path.read_text(encoding="utf-8").casefold()
    assert "synthetic" not in text, f"synthetic config is in production registry: {path}"


@pytest.mark.parametrize("path", _CONFIG_PATHS, ids=lambda path: path.parent.name)
def test_every_active_fund_config_parses_and_has_valid_static_identity(path):
    config = parse_config(path)
    errors, _warnings = validate_config(config)
    assert errors == [], f"{path}: {errors}"


def test_series_and_class_identifiers_are_unique_across_active_funds():
    configs = [parse_config(path) for path in _CONFIG_PATHS]
    for label, values in (
        ("seriesId", [config.series_id.upper() for config in configs]),
        ("classId", [config.class_id.upper() for config in configs]),
    ):
        duplicates = sorted(
            value for value, count in Counter(values).items() if count > 1
        )
        assert duplicates == [], f"duplicate active {label} values: {duplicates}"
