"""Tests for scripts/verify_output.py — the output XML auditor.

Focus: the cross-field NAV checks must FAIL on missing data rather than silently
passing ("looks good"), and the pctVal heuristic flags notional overstatement.
"""
import importlib.util
from pathlib import Path

import pytest

from nport.xsd_validator import NportValidator

_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "verify_output", _ROOT / "scripts" / "verify_output.py"
)
verify_output = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verify_output)


_NS = 'xmlns="http://www.sec.gov/edgar/nport"'


def _write_xml(tmp_path, body: str) -> Path:
    p = tmp_path / "f.xml"
    p.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<edgarSubmission {_NS}><formData><fundInfo>{body}</fundInfo></formData></edgarSubmission>\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture(scope="module")
def validator(request):
    return NportValidator(schema_dir=str(_ROOT / "schemas" / "v1_13"))


def test_missing_totassets_is_error_not_silent_pass(tmp_path, validator):
    """A filing with no <totAssets> must be flagged — the old code skipped the NAV
    identity check entirely when a total was missing, so it 'looked good'."""
    path = _write_xml(tmp_path, "<totLiabs>100.00</totLiabs><netAssets>900.00</netAssets>")
    errs, _warns, _ = verify_output.verify_file(path, validator)
    assert any("totAssets" in e for e in errs)


def test_nav_identity_mismatch_flagged(tmp_path, validator):
    path = _write_xml(
        tmp_path,
        "<totAssets>1000.00</totAssets><totLiabs>100.00</totLiabs><netAssets>500.00</netAssets>",
    )
    errs, _warns, _ = verify_output.verify_file(path, validator)
    assert any("NAV identity" in e for e in errs)


def test_pctval_overstatement_is_error(tmp_path, validator):
    """A holding summing to ~200% of net assets (the swap-at-notional bug) is now an ERROR."""
    holding = (
        "<invstOrSec><pctVal>199.21</pctVal><invCountry>US</invCountry></invstOrSec>"
        "<invstOrSec><pctVal>11.23</pctVal><invCountry>US</invCountry></invstOrSec>"
    )
    path = _write_xml(
        tmp_path,
        "<totAssets>1000.00</totAssets><totLiabs>100.00</totLiabs>"
        f"<netAssets>900.00</netAssets>{holding}",
    )
    errs, _warns, _ = verify_output.verify_file(path, validator)
    assert any("overstatement" in e for e in errs)


def test_low_pctval_not_flagged(tmp_path, validator):
    """A swap fund holding most of its assets as cash (Part C << 100%) must NOT be flagged."""
    holding = "<invstOrSec><pctVal>8.6</pctVal><invCountry>US</invCountry></invstOrSec>"
    path = _write_xml(
        tmp_path,
        "<totAssets>1000.00</totAssets><totLiabs>100.00</totLiabs>"
        f"<netAssets>900.00</netAssets>{holding}",
    )
    errs, _warns, _ = verify_output.verify_file(path, validator)
    assert not any("pctVal" in e or "overstatement" in e for e in errs)


def test_missing_invcountry_is_error(tmp_path, validator):
    """A holding with no invCountry is an error — country must be sourced, never blank."""
    holding = "<invstOrSec><pctVal>8.6</pctVal></invstOrSec>"   # no invCountry
    path = _write_xml(
        tmp_path,
        "<totAssets>1000.00</totAssets><totLiabs>100.00</totLiabs>"
        f"<netAssets>900.00</netAssets>{holding}",
    )
    errs, _warns, _ = verify_output.verify_file(path, validator)
    assert any("invCountry" in e for e in errs)
