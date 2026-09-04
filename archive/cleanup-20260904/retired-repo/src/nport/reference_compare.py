"""Read-only structural comparison of internally generated and reference XML.

This module has no imports from the generation pipeline and returns observations
only.  It cannot populate, patch, or approve a filing field.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from lxml import etree


@dataclass(frozen=True)
class ReferenceComparison:
    internal_report_date: str
    reference_report_date: str
    internal_fiscal_year_end: str
    reference_fiscal_year_end: str
    missing_structures: tuple[str, ...]
    extra_structures: tuple[str, ...]


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _shape(root: etree._Element) -> Counter[str]:
    """Count element paths while collapsing repeated portfolio positions."""
    counts: Counter[str] = Counter()

    def walk(node: etree._Element, path: str) -> None:
        name = _local(node.tag)
        current = f"{path}/{name}"
        # Presence is the relevant comparison for repeated holding structures;
        # holding counts and values legitimately differ across dates.
        counts[current] = 1 if "/invstOrSec/" in current else counts[current] + 1
        for child in node:
            walk(child, current)

    walk(root, "")
    return counts


def _text(root: etree._Element, name: str) -> str:
    result = root.xpath(f"string(.//*[local-name()='{name}'][1])")
    return str(result).strip()


def compare_reference(internal_xml: str | Path, reference_xml: str | Path) -> ReferenceComparison:
    internal = etree.parse(str(internal_xml)).getroot()
    reference = etree.parse(str(reference_xml)).getroot()
    internal_shape = _shape(internal)
    reference_shape = _shape(reference)
    return ReferenceComparison(
        internal_report_date=_text(internal, "repPdDate"),
        reference_report_date=_text(reference, "repPdDate"),
        internal_fiscal_year_end=_text(internal, "repPdEnd"),
        reference_fiscal_year_end=_text(reference, "repPdEnd"),
        missing_structures=tuple(sorted(reference_shape.keys() - internal_shape.keys())),
        extra_structures=tuple(sorted(internal_shape.keys() - reference_shape.keys())),
    )
