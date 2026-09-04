"""Tests for schema file checking and version monitoring."""

import json
from datetime import datetime

import nport.schema_check as schema_check
from nport.constants import DEFAULT_SCHEMA_DIR
from nport.schema_check import (
    CURRENT_SCHEMA_VERSION,
    EXPECTED_SCHEMA_FILES,
    check_schema_files,
    get_schema_integrity_report,
)


class _Response:
    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class TestCheckFiles:
    def test_valid_dir(self, schema_dir):
        assert check_schema_files(schema_dir)[0] == []

    def test_missing_dir(self, tmp_path):
        errors, _ = check_schema_files(tmp_path / "nope")
        assert len(errors) == 1 and "not found" in errors[0]

    def test_missing_single_file(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        for f in EXPECTED_SCHEMA_FILES[1:]:
            (d / f).write_text("<xs:schema/>")
        errors, _ = check_schema_files(d)
        assert len(errors) == 1 and EXPECTED_SCHEMA_FILES[0] in errors[0]

    def test_empty_file(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        for f in EXPECTED_SCHEMA_FILES:
            (d / f).write_text("")
        errors, _ = check_schema_files(d)
        assert len(errors) == len(EXPECTED_SCHEMA_FILES)

    def test_all_files_present(self, schema_dir):
        for f in EXPECTED_SCHEMA_FILES:
            assert (schema_dir / f).exists()


class TestIntegrityReport:
    def test_structure(self, schema_dir):
        r = get_schema_integrity_report(schema_dir)
        assert r["schema_version"] == CURRENT_SCHEMA_VERSION
        for f in EXPECTED_SCHEMA_FILES:
            assert r["files"][f]["size"] > 0
            assert len(r["files"][f]["sha256"]) == 64

    def test_missing_dir(self, tmp_path):
        r = get_schema_integrity_report(tmp_path / "nope")
        assert all(r["files"][f] == {"missing": True} for f in EXPECTED_SCHEMA_FILES)


class TestUpdateCheckCache:
    def test_default_cache_is_not_inside_bundled_schema_directory(self):
        assert DEFAULT_SCHEMA_DIR not in schema_check._CACHE_FILE.parents

    def test_fresh_cache_prevents_network_access(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "schema-cache.json"
        cache_file.write_text(json.dumps({
            "last_check": "2026-09-01T12:00:00",
            "current_version": CURRENT_SCHEMA_VERSION,
            "newer_version": "1.14",
        }), encoding="utf-8")
        monkeypatch.setattr(schema_check, "_CACHE_FILE", cache_file)

        def unexpected_network_call(*args, **kwargs):
            raise AssertionError("a fresh cache must prevent a network call")

        monkeypatch.setattr(schema_check.urllib.request, "urlopen", unexpected_network_call)
        version, warnings = schema_check.check_for_schema_update(
            now=datetime(2026, 9, 4, 12, 0, 0),
        )
        assert version == "1.14"
        assert warnings and "Schema update available" in warnings[0]

    def test_expired_cache_is_refreshed_and_version_is_parsed(
        self, tmp_path, monkeypatch,
    ):
        cache_file = tmp_path / "schema-cache.json"
        cache_file.write_text(json.dumps({
            "last_check": "2026-08-01T12:00:00",
            "current_version": CURRENT_SCHEMA_VERSION,
            "newer_version": None,
        }), encoding="utf-8")
        monkeypatch.setattr(schema_check, "_CACHE_FILE", cache_file)
        monkeypatch.setattr(
            schema_check.urllib.request,
            "urlopen",
            lambda *args, **kwargs: _Response(
                '<a href="edgar-form-n-port-xml-tech-spec-114.zip">schema</a>'
            ),
        )

        now = datetime(2026, 9, 4, 12, 0, 0)
        version, warnings = schema_check.check_for_schema_update(now=now)
        assert version == "1.14"
        assert warnings and "SCHEMA UPDATE" in warnings[0]
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        assert cache == {
            "last_check": now.isoformat(),
            "current_version": CURRENT_SCHEMA_VERSION,
            "newer_version": "1.14",
        }

    def test_network_failure_is_a_warning_and_does_not_create_cache(
        self, tmp_path, monkeypatch,
    ):
        cache_file = tmp_path / "schema-cache.json"
        monkeypatch.setattr(schema_check, "_CACHE_FILE", cache_file)

        def fail_network(*args, **kwargs):
            raise OSError("offline")

        monkeypatch.setattr(schema_check.urllib.request, "urlopen", fail_network)
        version, warnings = schema_check.check_for_schema_update(
            force=True, now=datetime(2026, 9, 4, 12, 0, 0),
        )
        assert version is None
        assert warnings == ["Could not check for schema updates: offline"]
        assert not cache_file.exists()
