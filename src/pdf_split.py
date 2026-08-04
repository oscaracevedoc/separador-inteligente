"""Separa un PDF en paginas individuales.

Cada pagina se produce en dos formas:
  - PDF de una sola pagina (via pypdf), que es el archivo final que se guarda.
  - PNG rasterizado (via PyMuPDF/fitz), que se envia a Claude como imagen para
    que pueda "ver" el contenido aunque el PDF sea un escaneo sin texto
    extraible.

Se usa PyMuPDF en lugar de pdf2image para el rasterizado porque no depende de
tener el binario poppler instalado en el sistema (pdf2image si lo requiere),
lo que hace la app mas facil de instalar con un solo `pip install`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

DEFAULT_DPI = 150
MAX_PAGES = 300


@dataclass(frozen=True)
class SplitPage:
    """Una pagina ya separada del PDF original."""

    page_number: int  # 1-indexado, posicion en el documento original
    pdf_bytes: bytes  # PDF de una sola pagina, listo para guardar
    png_bytes: bytes  # render PNG de la pagina, para enviar a Claude


class PdfSplitError(ValueError):
    """Error esperable al leer o separar el PDF (se muestra tal cual al usuario)."""


def split_pdf(pdf_bytes: bytes, dpi: int = DEFAULT_DPI) -> list[SplitPage]:
    """Separa `pdf_bytes` en una lista de `SplitPage`, una por pagina.

    Lanza `PdfSplitError` para casos esperables: PDF corrupto, protegido con
    contrasena, o sin paginas.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except PdfReadError as exc:
        raise PdfSplitError(f"El archivo no es un PDF valido o esta corrupto: {exc}") from exc

    if reader.is_encrypted:
        # Muchos PDFs "protegidos" solo tienen contrasena de propietario (owner
        # password) y se pueden abrir igual con una contrasena vacia.
        try:
            decrypt_result = reader.decrypt("")
        except Exception as exc:  # pypdf lanza distintos tipos segun el algoritmo
            raise PdfSplitError("El PDF esta protegido con contrasena y no se pudo abrir.") from exc
        if not decrypt_result:
            raise PdfSplitError("El PDF esta protegido con contrasena y no se pudo abrir.")

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise PdfSplitError("El PDF no contiene paginas.")
    if total_pages > MAX_PAGES:
        raise PdfSplitError(
            f"El PDF tiene {total_pages} paginas; el limite soportado es {MAX_PAGES}."
        )

    try:
        image_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # PyMuPDF lanza RuntimeError/fitz.FileDataError
        raise PdfSplitError(f"No se pudo abrir el PDF para renderizar imagenes: {exc}") from exc

    zoom = dpi / 72  # 72 dpi es la unidad base de PyMuPDF
    matrix = fitz.Matrix(zoom, zoom)

    pages: list[SplitPage] = []
    try:
        for index, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            page_buffer = io.BytesIO()
            writer.write(page_buffer)

            pixmap = image_doc[index].get_pixmap(matrix=matrix)
            png_bytes = pixmap.tobytes("png")

            pages.append(
                SplitPage(
                    page_number=index + 1,
                    pdf_bytes=page_buffer.getvalue(),
                    png_bytes=png_bytes,
                )
            )
    finally:
        image_doc.close()

    return pages
