"""Command-line interface for the reviewed N-PORT filing pipeline."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from nport.builder import NportBuilder
from nport.config import parse_config, parse_filing, parse_holdings
from nport.constants import NPORT_SCHEMA_VERSION, validate_artifact_component
from nport.input_workbook import (
    INPUT_WORKBOOK_FORMAT_VERSION,
    create_input_workbook_template,
    prepare_from_input_workbook,
)
from nport.pipeline import (
    ReviewBlocked,
    evaluate_inputs,
    finalize_inputs,
    prepare_inputs,
)
from nport.policy import derive_context_from_config, report_date_for_period
from nport.preflight import Finding, run_preflight, write_release_manifest
from nport.schema_check import check_for_schema_update, check_schema_files
from nport.xsd_validator import NportValidator

DEFAULT_FUNDS_DIR = Path("data/funds")
DEFAULT_BUILDS_DIR = Path("data/builds")
DEFAULT_RELEASES_DIR = Path("output")


def _target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("fund", help="Fund ticker")
    parser.add_argument("period", help="Reporting period in YYYY-MM format")
    parser.add_argument("--fund-dir", default=None, help="Exact fund directory (default: data/funds/<fund>)")


def _validation_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--schema-dir", default=None, help="SEC XSD directory")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nport", description="Prepare, review, validate, and build SEC N-PORT XML"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Create or refresh one fund-period input workbook")
    _target_arguments(prepare)
    prepare_source = prepare.add_mutually_exclusive_group(required=True)
    prepare_source.add_argument("--positions", help="Canonical positions CSV")
    prepare_source.add_argument(
        "--input-workbook", help="Versioned multi-fund input workbook"
    )
    prepare.add_argument("--orders", default=None, help="Optional create/redeem orders CSV")

    input_template = sub.add_parser(
        "input-template", help="Create one input-only workbook for active funds"
    )
    input_template.add_argument("periods", nargs="+", help="Reporting periods in YYYY-MM format")
    input_template.add_argument(
        "--funds-dir", default=str(DEFAULT_FUNDS_DIR), help="Active fund registry root"
    )
    input_template.add_argument(
        "--output", default=None, help="Output .xlsx path; default is data/inputs/nport-v<schema>"
    )

    status = sub.add_parser("status", help="Show unresolved workbook and reconciliation items")
    _target_arguments(status)

    preflight = sub.add_parser("preflight", help="Check policy, applicability, and reconciliation")
    _target_arguments(preflight)

    validate = sub.add_parser("validate", help="Finalize temporarily and run all validation gates")
    _target_arguments(validate)
    _validation_arguments(validate)

    build = sub.add_parser("build", help="Build only from a complete reviewed workbook")
    _target_arguments(build)
    _validation_arguments(build)
    build.add_argument("--bundle-root", default=str(DEFAULT_BUILDS_DIR), help="Versioned canonical-bundle root")
    build.add_argument("--release-root", default=str(DEFAULT_RELEASES_DIR), help="Versioned XML-release root")
    build.add_argument("--dry-run", action="store_true", help="Validate without retaining files")
    build.add_argument("--verbose", action="store_true")

    sub.add_parser("schema", help="Print the canonical holdings input schema")
    schema_check = sub.add_parser("check-schema", help="Verify bundled XSDs and check for updates")
    schema_check.add_argument("--schema-dir", default=None)
    schema_check.add_argument("--force", action="store_true", help="Ignore the update-check cache")
    return parser


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    args = _parser().parse_args(argv)
    handlers = {
        "prepare": _prepare,
        "input-template": _input_template,
        "status": _status,
        "preflight": _preflight,
        "validate": _validate,
        "build": _build,
        "schema": _schema,
        "check-schema": _check_schema,
    }
    handlers[args.command](args)


def _resolve_target(args: argparse.Namespace) -> tuple[Path, str, str]:
    fund = args.fund.strip().upper()
    period = args.period.strip()
    try:
        validate_artifact_component(fund, "fund ticker")
    except ValueError as exc:
        _fail(str(exc))
    try:
        report_date_for_period(period)
    except ValueError as exc:
        _fail(str(exc))
    fund_dir = Path(args.fund_dir) if args.fund_dir else DEFAULT_FUNDS_DIR / fund.lower()
    if not fund_dir.is_dir():
        _fail(f"fund directory not found: {fund_dir}")
    return fund_dir, fund, period


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _item_label(code: str) -> str:
    if code.startswith("G-012"):
        return "RECONCILIATION"
    if code.startswith(("POLICY_", "COVERAGE_")) or code == "G-004":
        return "POLICY"
    if code.startswith("G-") or code.startswith("INPUT_"):
        return "INPUT"
    return "BLOCKER"


def _print_findings(findings: list[Finding]) -> None:
    for finding in findings:
        print(f"{_item_label(finding.code)} {finding.code}: {finding.plain}")
        print(f"  Location: {finding.technical}")


def _evaluate(fund_dir: Path, fund: str, period: str) -> dict:
    try:
        result = evaluate_inputs(fund_dir, period)
    except (OSError, ValueError) as exc:
        _fail(f"inputs could not be evaluated: {exc}")
    blockers = result.get("blockers", [])
    if blockers:
        print(f"{fund} {period}: NOT READY ({len(blockers)} blocker(s))", file=sys.stderr)
        _print_findings(blockers)
        raise SystemExit(1)
    return result


def _context_and_preflight(result: dict, fund: str, period: str) -> tuple[object, list[Finding]]:
    try:
        context = derive_context_from_config(result["config"], fund, period, "fund_config.txt")
    except ValueError as exc:
        _fail(f"policy could not be resolved: {exc}")
    findings = run_preflight(context, result["filing"], result["holdings"])
    blockers = [finding for finding in findings if finding.severity == "BLOCKER"]
    if blockers:
        print(f"{fund} {period}: PREFLIGHT FAILED ({len(blockers)} blocker(s))", file=sys.stderr)
        _print_findings(blockers)
        raise SystemExit(1)
    return context, findings


def _validate_xml(xml_bytes: bytes, schema_dir: str | None) -> None:
    schema_errors, _ = check_schema_files(schema_dir)
    if schema_errors:
        _fail("schema files are unavailable: " + "; ".join(schema_errors))
    errors = NportValidator(schema_dir=schema_dir).validate_xsd(xml_bytes)
    if errors:
        print("XSD validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        raise SystemExit(1)


def _validate_result(
    result: dict, fund: str, period: str, schema_dir: str | None
) -> tuple[bytes, object, list[Finding]]:
    context, findings = _context_and_preflight(result, fund, period)
    try:
        xml_bytes = NportBuilder(
            result["config"], result["filing"], result["holdings"]
        ).to_xml_bytes()
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"canonical data could not be serialized to XML: {exc}")
    _validate_xml(xml_bytes, schema_dir)
    return xml_bytes, context, findings


def _load_bundle(bundle: Path) -> dict:
    try:
        return {
            "config": parse_config(bundle / "fund_config.txt"),
            "filing": parse_filing(bundle / "filing_data.txt"),
            "holdings": parse_holdings(bundle / "holdings.csv"),
        }
    except (OSError, TypeError, ValueError) as exc:
        _fail(f"canonical bundle could not be reloaded: {exc}")


def _prepare(args: argparse.Namespace) -> None:
    fund_dir, fund, period = _resolve_target(args)
    try:
        if args.input_workbook:
            if args.orders:
                _fail("--orders cannot be combined with --input-workbook; use the Orders sheet")
            path = prepare_from_input_workbook(
                fund_dir, fund, period, args.input_workbook,
            )
        else:
            path = prepare_inputs(
                fund_dir, period, positions=args.positions, orders=args.orders,
            )
    except (OSError, ValueError) as exc:
        _fail(f"input workbook could not be prepared: {exc}")
    print(f"Prepared: {path}")
    print("Next: calculate the Bloomberg sheet, complete all MISSING rows and reconciliation controls,")
    print(f"then run: nport status {fund.lower()} {period}")


def _input_template(args: argparse.Namespace) -> None:
    periods = []
    for raw in args.periods:
        period = raw.strip()
        try:
            report_date_for_period(period)
        except ValueError as exc:
            _fail(str(exc))
        if period not in periods:
            periods.append(period)
    period_label = "_".join(periods)
    output = Path(args.output) if args.output else (
        Path("data/inputs") / f"nport-v{NPORT_SCHEMA_VERSION}"
        / (
            f"nport-inputs-v{INPUT_WORKBOOK_FORMAT_VERSION}_{period_label}"
            f"_nport-v{NPORT_SCHEMA_VERSION}.xlsx"
        )
    )
    try:
        path = create_input_workbook_template(args.funds_dir, periods, output)
    except (OSError, ValueError) as exc:
        _fail(f"input template could not be created: {exc}")
    print(f"Created: {path}")
    print("Complete the workbook, then import each fund-period with:")
    print("  nport prepare <fund> <YYYY-MM> --input-workbook <workbook.xlsx>")


def _status(args: argparse.Namespace) -> None:
    fund_dir, fund, period = _resolve_target(args)
    result = _evaluate(fund_dir, fund, period)
    _context_and_preflight(result, fund, period)
    print(f"{fund} {period}: READY - workbook, policy, applicability, and reconciliation are complete.")


def _preflight(args: argparse.Namespace) -> None:
    fund_dir, fund, period = _resolve_target(args)
    result = _evaluate(fund_dir, fund, period)
    _, findings = _context_and_preflight(result, fund, period)
    for finding in findings:
        print(f"{finding.severity} {finding.code}: {finding.technical}")
    print(f"{fund} {period}: PREFLIGHT PASSED")


def _validate(args: argparse.Namespace) -> None:
    fund_dir, fund, period = _resolve_target(args)
    result = _evaluate(fund_dir, fund, period)
    _validate_result(result, fund, period, args.schema_dir)
    with tempfile.TemporaryDirectory() as scratch:
        bundle = finalize_inputs(fund_dir, period, bundle_root=Path(scratch) / "builds")
        _validate_result(_load_bundle(bundle), fund, period, args.schema_dir)
    print(f"{fund} {period}: VALID - canonical serialization and SEC XSD validation passed.")


def _write_atomic(path: Path, content: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing release artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _build(args: argparse.Namespace) -> None:
    fund_dir, fund, period = _resolve_target(args)
    result = _evaluate(fund_dir, fund, period)
    _validate_result(result, fund, period, args.schema_dir)

    if args.dry_run:
        with tempfile.TemporaryDirectory() as scratch:
            bundle = finalize_inputs(fund_dir, period, bundle_root=Path(scratch) / "builds")
            _validate_result(_load_bundle(bundle), fund, period, args.schema_dir)
        print(f"{fund} {period}: DRY RUN PASSED; no bundle or XML retained.")
        return

    try:
        bundle = finalize_inputs(fund_dir, period, bundle_root=args.bundle_root)
    except ReviewBlocked as exc:
        _print_findings(exc.blockers)
        raise SystemExit(1) from exc
    except (OSError, TypeError, ValueError) as exc:
        _fail(f"canonical bundle could not be finalized: {exc}")

    canonical = _load_bundle(bundle)
    xml_bytes, context, findings = _validate_result(canonical, fund, period, args.schema_dir)
    release_stem = (
        f"{fund}_{period}_nport-v{NPORT_SCHEMA_VERSION}_{bundle.name}"
    )
    output = (
        Path(args.release_root) / fund.lower() / period
        / f"nport-v{NPORT_SCHEMA_VERSION}" / bundle.name / f"{release_stem}.xml"
    )
    try:
        _write_atomic(output, xml_bytes)
    except OSError as exc:
        _fail(f"XML release artifact could not be written: {exc}")
    inputs = [
        bundle / "fund_config.txt", bundle / "filing_data.txt", bundle / "holdings.csv",
        bundle / "source_manifest.csv", bundle / "field_provenance.csv",
        bundle / "reconciliation.csv", bundle / "input_receipt.json",
    ]
    try:
        write_release_manifest(
            output.with_suffix(".manifest.json"), ticker=fund, period=period, context=context,
            xml_path=output, input_paths=inputs, xsd_version=NPORT_SCHEMA_VERSION,
            findings=findings, live_test_flag=canonical["filing"].live_test_flag,
        )
    except (OSError, TypeError, ValueError) as exc:
        # The XML was created by this invocation and is rolled back so consumers
        # never see a release without its integrity manifest.
        output.unlink(missing_ok=True)
        _fail(f"release manifest could not be written; XML was rolled back: {exc}")
    print(f"Written: {output} ({len(xml_bytes)} bytes)")
    print(f"Clean canonical bundle: {bundle}")
    if args.verbose:
        print(f"Holdings: {len(canonical['holdings'])}; schema: v{NPORT_SCHEMA_VERSION}")


def _schema(args: argparse.Namespace) -> None:
    from nport.schema import print_schema
    print_schema()


def _check_schema(args: argparse.Namespace) -> None:
    errors, warnings = check_schema_files(args.schema_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print("Bundled schema files are present.")
    newer, update_warnings = check_for_schema_update(force=args.force)
    for warning in warnings + update_warnings:
        print(f"WARNING: {warning}")
    print(f"Schema update available: v{newer}" if newer else f"Bundled schema version: v{NPORT_SCHEMA_VERSION}")

if __name__ == "__main__":
    main()
