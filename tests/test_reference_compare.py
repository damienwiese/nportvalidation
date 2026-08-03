from nport.reference_compare import compare_reference


def test_reference_compare_is_structural_and_read_only(tmp_path):
    internal = tmp_path / "internal.xml"
    reference = tmp_path / "reference.xml"
    internal.write_text(
        "<root><repPdEnd>2026-12-31</repPdEnd><repPdDate>2026-06-30</repPdDate>"
        "<fundInfo><totAssets>100</totAssets></fundInfo></root>", encoding="utf-8",
    )
    reference.write_text(
        "<root><repPdEnd>2026-12-31</repPdEnd><repPdDate>2026-04-30</repPdDate>"
        "<fundInfo><totAssets>999</totAssets><cshNotRptdInCorD>5</cshNotRptdInCorD>"
        "</fundInfo></root>", encoding="utf-8",
    )
    result = compare_reference(internal, reference)
    assert result.internal_report_date == "2026-06-30"
    assert result.reference_report_date == "2026-04-30"
    assert result.missing_structures == ("/root/fundInfo/cshNotRptdInCorD",)
    assert result.extra_structures == ()
    assert internal.read_text(encoding="utf-8").find("100") > 0
