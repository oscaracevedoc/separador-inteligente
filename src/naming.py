"""Sanitizacion de nombres de archivo y numeracion de prefijos.

Convierte el "filename_slug" que devuelve Claude (texto libre, potencialmente
con tildes, mayusculas o caracteres invalidos en un nombre de archivo) en un
nombre final seguro: sin tildes, sin caracteres especiales, en minusculas,
con guiones bajos, con prefijo numerico segun el orden original de la pagina
y sin colisiones con otras paginas del mismo PDF.
"""

from __future__ import annotations

import re
import unicodedata

MAX_SLUG_WORDS = 6
MAX_SLUG_LENGTH = 60
FALLBACK_SLUG = "pagina_sin_clasificar"


def sanitize_slug(raw: str) -> str:
    """Normaliza un texto libre a un slug de archivo: `factura_proveedor_xyz`."""
    if not raw:
        return FALLBACK_SLUG

    # Quita tildes/diacriticos (NFKD separa la letra del acento, luego se
    # descarta todo lo que no sea ASCII).
    text = unicodedata.normalize("NFKD", raw)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()

    # Cualquier caracter que no sea letra/numero se vuelve separador.
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")

    words = [w for w in text.split("_") if w][:MAX_SLUG_WORDS]
    slug = "_".join(words)[:MAX_SLUG_LENGTH].strip("_")

    return slug or FALLBACK_SLUG


def build_filenames(page_numbers: list[int], slugs: list[str]) -> list[str]:
    """Combina numero de pagina + slug en nombres finales `NN_slug.pdf`.

    - El ancho del prefijo numerico se ajusta al total de paginas (2 digitos
      minimo: "01", "02"... o mas si hay 100+ paginas).
    - Si dos paginas terminan con el mismo `NN_slug`, se agrega un sufijo
      `_2`, `_3`, etc. para evitar sobrescribir archivos.
    """
    if len(page_numbers) != len(slugs):
        raise ValueError("page_numbers y slugs deben tener la misma longitud")

    total = len(page_numbers)
    width = max(2, len(str(total)))

    seen: dict[str, int] = {}
    filenames: list[str] = []
    for page_num, slug in zip(page_numbers, slugs):
        prefix = str(page_num).zfill(width)
        base = f"{prefix}_{slug}"

        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        final_base = base if occurrence == 0 else f"{base}_{occurrence + 1}"

        filenames.append(f"{final_base}.pdf")

    return filenames
