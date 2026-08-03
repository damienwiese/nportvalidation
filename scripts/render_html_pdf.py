"""Render local HTML audit documents to paginated PDFs with PyMuPDF."""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def render(source: Path, target: Path) -> None:
    page = fitz.paper_rect("a4")
    margin = 42.5  # approximately 15 mm
    content = fitz.Rect(page.x0 + margin, page.y0 + margin, page.x1 - margin, page.y1 - margin)
    story = fitz.Story(html=source.read_text(encoding="utf-8"), em=10)

    def rectfn(_page_number: int, _filled: fitz.Rect):
        return page, content, None

    target.parent.mkdir(parents=True, exist_ok=True)
    document = story.write_with_links(rectfn, pagefn=None, positionfn=None)
    for page_number, pdf_page in enumerate(document, 1):
        footer = fitz.Rect(page.x0 + margin, page.y1 - 30, page.x1 - margin, page.y1 - 12)
        pdf_page.insert_textbox(
            footer, f"Page {page_number} of {len(document)}", fontsize=7.5,
            fontname="helv", color=(0.40, 0.47, 0.54), align=fitz.TEXT_ALIGN_RIGHT,
        )
    document.save(target)
    document.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    render(args.source.resolve(), args.target.resolve())


if __name__ == "__main__":
    main()
