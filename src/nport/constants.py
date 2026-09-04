"""Namespace URIs and paths for N-PORT XML generation."""

from pathlib import Path

NPORT_SCHEMA_VERSION = "1.13"
NPORT_SCHEMA_DIRECTORY = "v" + NPORT_SCHEMA_VERSION.replace(".", "_")

# XML Namespaces
NS_NPORT = "http://www.sec.gov/edgar/nport"
NS_COMMON = "http://www.sec.gov/edgar/common"
NS_NPORTCOMMON = "http://www.sec.gov/edgar/nportcommon"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    None: NS_NPORT,
    "com": NS_COMMON,
    "ncom": NS_NPORTCOMMON,
    "xsi": NS_XSI,
}

# Editable checkouts keep schemas at the project root. Built wheels include the
# same files inside the package so validation works after installation.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas" / NPORT_SCHEMA_DIRECTORY
PROJECT_SCHEMA_DIR = PROJECT_ROOT / "schemas" / NPORT_SCHEMA_DIRECTORY
DEFAULT_SCHEMA_DIR = PACKAGE_SCHEMA_DIR if PACKAGE_SCHEMA_DIR.is_dir() else PROJECT_SCHEMA_DIR
ROOT_SCHEMA_FILE = "eis_NPORT_Filer.xsd"


def validate_artifact_component(value: str, label: str) -> str:
    """Validate one user-controlled component of a bundle or release path."""
    if not value or not all(
        character.isascii() and (character.isalnum() or character in "-_")
        for character in value
    ):
        raise ValueError(
            f"{label} must contain only ASCII letters, digits, hyphens, and underscores"
        )
    return value
