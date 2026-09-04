import pytest

from nport.cli import _parser, main


def test_cli_exposes_only_supported_pipeline_commands():
    help_text = _parser().format_help()
    for command in (
        "input-template", "prepare", "status", "preflight", "validate",
        "build", "schema", "check-schema",
    ):
        assert command in help_text


def test_cli_creates_versioned_input_template(tmp_path, fdrs_dir, capsys):
    fund_dir = tmp_path / "funds" / "fdrs"
    fund_dir.mkdir(parents=True)
    (fund_dir / "fund_config.txt").write_bytes((fdrs_dir / "fund_config.txt").read_bytes())
    output = tmp_path / "nport-inputs-v4_2026-07_nport-v1.13.xlsx"

    main([
        "input-template", "2026-07", "--funds-dir", str(fund_dir.parent),
        "--output", str(output),
    ])

    assert output.is_file()
    assert f"Created: {output}" in capsys.readouterr().out


def test_status_fails_closed_without_workbook(tmp_path, fdrs_dir, capsys):
    fund_dir = tmp_path / "fdrs"
    fund_dir.mkdir()
    (fund_dir / "fund_config.txt").write_bytes((fdrs_dir / "fund_config.txt").read_bytes())
    with pytest.raises(SystemExit) as exc:
        main(["status", "FDRS", "2025-12", "--fund-dir", str(fund_dir)])
    assert exc.value.code == 1
    assert "NOT READY" in capsys.readouterr().err


@pytest.mark.parametrize("period", ["2026-7", "2026/07", "2026-13"])
def test_cli_rejects_noncanonical_period_before_accessing_data(period, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["status", "FDRS", period])
    assert exc.value.code == 1
    assert "period must be YYYY-MM" in capsys.readouterr().err


def test_cli_rejects_unsafe_fund_name_before_accessing_data(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["status", "../FDRS", "2026-07"])
    assert exc.value.code == 1
    assert "fund ticker must contain only" in capsys.readouterr().err
