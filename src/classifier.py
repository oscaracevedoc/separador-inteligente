"""Clasificacion de una pagina (imagen) usando la API de Claude.

Cada pagina se manda como imagen (no como texto extraido del PDF) para que
Claude pueda "ver" el contenido incluso si la pagina viene de un documento
escaneado sin capa de texto. La respuesta se fuerza a un JSON con schema fijo
(structured outputs) para no depender de parsear texto libre.
"""

from __future__ import annotations

import base64
import json

import anthropic

MODEL = "claude-sonnet-5"
MAX_OUTPUT_TOKENS = 512

SYSTEM_PROMPT = (
    "Eres un asistente que clasifica paginas sueltas de documentos "
    "administrativos digitalizados (facturas, contratos, comprobantes, "
    "cartas, formularios, boletas, etc.). Analizas el contenido visual y "
    "textual de cada imagen y devuelves solo la clasificacion solicitada, "
    "sin comentarios adicionales."
)

USER_PROMPT = (
    "Analiza esta pagina de un PDF y devuelve:\n"
    "1. filename_slug: un nombre de archivo corto y descriptivo del "
    "contenido, de maximo 5-6 palabras, en minusculas, sin tildes ni "
    "caracteres especiales, con guiones bajos en vez de espacios. "
    "Ejemplos: 'factura_proveedor_acme', 'contrato_arriendo_local', "
    "'boleta_honorarios_marzo'.\n"
    "2. description: una descripcion de una sola linea (maximo 20 palabras) "
    "resumiendo el contenido de la pagina.\n"
    "Si la pagina esta en blanco, ilegible, o no tiene contenido "
    "identificable, usa filename_slug='pagina_en_blanco' o "
    "'pagina_ilegible' segun corresponda."
)

RESPONSE_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "filename_slug": {
                "type": "string",
                "description": "Nombre de archivo corto en snake_case, sin extension.",
            },
            "description": {
                "type": "string",
                "description": "Resumen de una linea del contenido de la pagina.",
            },
        },
        "required": ["filename_slug", "description"],
        "additionalProperties": False,
    },
}


class ClassificationError(Exception):
    """Fallo esperable al clasificar una pagina (se captura por-pagina, no aborta el lote)."""


def classify_page(client: anthropic.Anthropic, png_bytes: bytes) -> tuple[str, str]:
    """Clasifica una pagina renderizada como PNG y devuelve (filename_slug, description).

    Lanza `ClassificationError` en cualquier fallo esperable (rate limit,
    error de red, rechazo del modelo, respuesta invalida) para que el
    llamador pueda seguir procesando el resto de las paginas.
    """
    image_b64 = base64.standard_b64encode(png_bytes).decode("ascii")

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            output_config={"format": RESPONSE_SCHEMA},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ],
                }
            ],
        )
    except anthropic.RateLimitError as exc:
        raise ClassificationError("Limite de velocidad de la API alcanzado.") from exc
    except anthropic.APIStatusError as exc:
        raise ClassificationError(f"Error de la API de Claude ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise ClassificationError("No se pudo conectar con la API de Claude.") from exc

    if response.stop_reason == "refusal":
        raise ClassificationError("Claude rechazo analizar esta pagina.")

    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise ClassificationError("La respuesta de Claude no incluyo contenido de texto.")

    try:
        data = json.loads(text_blocks[0])
        filename_slug = str(data["filename_slug"])
        description = str(data["description"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ClassificationError(f"Respuesta de Claude con formato invalido: {exc}") from exc

    return filename_slug, description
