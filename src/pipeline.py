"""Orquesta el flujo completo: separar el PDF, clasificar cada pagina con
Claude, y empaquetar los resultados (PDFs nombrados + log CSV) en memoria.

Todo se mantiene en memoria (sin escribir a disco) a proposito: la app corre
como servicio web multiusuario (Streamlit Community Cloud), y escribir a una
carpeta del servidor mezclaria archivos entre distintos usuarios y no
persiste entre despliegues. El resultado se entrega como un ZIP descargable.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from . import naming
from .classifier import ClassificationError, classify_page
from .pdf_split import split_pdf

CSV_FIELDNAMES = ["pagina_original", "nombre_asignado", "descripcion", "estado"]
LOG_FILENAME = "log_clasificacion.csv"

ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class PageResult:
    original_page: int
    assigned_name: str
    description: str
    status: str  # "ok" | "error"
    pdf_bytes: bytes
    png_bytes: bytes | None = None


def classify_pdf(
    pdf_bytes: bytes,
    api_key: str,
    save_png: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> list[PageResult]:
    """Separa y clasifica un PDF completo, devolviendo un `PageResult` por pagina.

    Lanza `PdfSplitError` (ver `pdf_split.py`) si el PDF no se puede leer. Los
    errores de clasificacion de paginas individuales NO abortan el proceso:
    la pagina queda con un nombre de respaldo y estado "error".
    """
    pages = split_pdf(pdf_bytes)  # puede lanzar PdfSplitError
    client = anthropic.Anthropic(api_key=api_key)

    slugs: list[str] = []
    descriptions: list[str] = []
    statuses: list[str] = []

    total = len(pages)
    for index, page in enumerate(pages):
        try:
            raw_slug, description = classify_page(client, page.png_bytes)
            status = "ok"
        except ClassificationError as exc:
            raw_slug = f"pagina_{page.page_number}_sin_clasificar"
            description = f"No se pudo clasificar: {exc}"
            status = "error"

        slugs.append(naming.sanitize_slug(raw_slug))
        descriptions.append(description)
        statuses.append(status)

        if progress_callback is not None:
            progress_callback(index + 1, total)

    filenames = naming.build_filenames([p.page_number for p in pages], slugs)

    results: list[PageResult] = []
    for page, filename, description, status in zip(pages, filenames, descriptions, statuses):
        results.append(
            PageResult(
                original_page=page.page_number,
                assigned_name=filename,
                description=description,
                status=status,
                pdf_bytes=page.pdf_bytes,
                png_bytes=page.png_bytes if save_png else None,
            )
        )

    return results


def build_csv_log(results: list[PageResult]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    for r in results:
        writer.writerow(
            {
                "pagina_original": r.original_page,
                "nombre_asignado": r.assigned_name,
                "descripcion": r.description,
                "estado": r.status,
            }
        )
    return buf.getvalue().encode("utf-8")


def build_zip(results: list[PageResult]) -> bytes:
    """Empaqueta todos los PDFs (y PNGs si se generaron) + el log CSV en un ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in results:
            zf.writestr(r.assigned_name, r.pdf_bytes)
            if r.png_bytes is not None:
                png_name = r.assigned_name.rsplit(".", 1)[0] + ".png"
                zf.writestr(png_name, r.png_bytes)
        zf.writestr(LOG_FILENAME, build_csv_log(results))
    return buf.getvalue()
