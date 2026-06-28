"""Render source PDF pages into artifact images.

The renderer is intentionally import-light. PyMuPDF is loaded only when
``render_page_images`` is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docmirror.runtime.optional_deps import require_optional_module


def _fitz() -> Any:
    return require_optional_module("fitz", feature="page image artifact rendering", extra="pdf")


def render_page_images(pdf_path: str | Path, output_dir: str | Path, *, dpi: int = 150) -> list[Path]:
    """Render each PDF page to a PNG file and return generated paths."""
    fitz = _fitz()
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document, start=1):
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            out = output_dir / f"page_{index:04d}.png"
            pix.save(out)
            generated.append(out)
    return generated
