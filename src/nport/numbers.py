"""Numeric coercion shared across the pipeline — one implementation, one behavior.

Every module that reads numbers out of CSV/xlsx/text (custodian, EagleSTAR, AP orders,
filing master, CLI reconciliation) needs the same tolerant parse: strip commas and
whitespace, return 0.0 when the value is missing or non-numeric. Centralizing it here
keeps that behavior identical everywhere and removes the four duplicate ``_fnum`` copies.
"""


def fnum(x) -> float:
    """Parse a numeric string (commas/whitespace tolerated); 0.0 if unparseable/None."""
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0
