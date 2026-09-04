"""Source-boundary rules shared by ingestion, policy, and preflight."""

PROHIBITED_SOURCE_TOKENS = (
    "us bank", "u.s. bank", "usbank", "eaglestar", "custodian",
    "administrator", "prepared filing", "prepared n-port",
    "reference filing", "filing comparison", "comparison filing",
    "historical xml", "generated xml", "output/", "output\\",
)


def is_prohibited_source(*values: str) -> bool:
    """Return whether source metadata identifies a prohibited upstream source."""
    source = " | ".join(str(value) for value in values).strip().lower()
    return any(token in source for token in PROHIBITED_SOURCE_TOKENS)
