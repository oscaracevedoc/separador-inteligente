"""Interfaz Streamlit del Separador Inteligente de PDF.

Flujo: subir un PDF (drag & drop o selector) -> separar en paginas -> cada
pagina se analiza con Claude (como imagen) para generar un nombre de archivo
descriptivo y una descripcion -> se muestra una tabla con el resultado -> se
descarga todo como un ZIP (un PDF por pagina + log CSV).

Todo se procesa en memoria, sin escribir nada en el servidor: la app esta
pensada para correr online (Streamlit Community Cloud) con multiples
usuarios al mismo tiempo, cada uno con su propia clave de API.
"""

from __future__ import annotations

import hmac
import os

import streamlit as st

from src.pdf_split import PdfSplitError
from src.pipeline import build_csv_log, build_zip, classify_pdf

MAX_UPLOAD_MB = 40


def _get_secret(name: str) -> str:
    """Busca `name` en variables de entorno (.env local) o en st.secrets
    (Streamlit Community Cloud). Devuelve "" si no esta configurado.
    """
    env_value = os.environ.get(name)
    if env_value:
        return env_value
    try:
        return str(st.secrets.get(name, ""))
    except Exception:
        return ""


def _check_access() -> bool:
    """Pantalla de clave de acceso opcional.

    Si se configura el secret/variable de entorno APP_PASSWORD, la app pide
    esa clave antes de mostrar cualquier otra cosa (para no dejarla abierta a
    cualquiera con el link). Si no se configura nada, la app queda publica
    sin clave.
    """
    app_password = _get_secret("APP_PASSWORD")
    if not app_password:
        return True

    if st.session_state.get("access_granted"):
        return True

    st.title("Separador Inteligente de PDF")
    entered = st.text_input("Clave de acceso", type="password")
    if st.button("Entrar", type="primary"):
        if hmac.compare_digest(entered, app_password):
            st.session_state["access_granted"] = True
            st.rerun()
        else:
            st.error("Clave incorrecta.")
    return False


st.set_page_config(page_title="Separador Inteligente de PDF", layout="wide")

if not _check_access():
    st.stop()

st.title("Separador Inteligente de PDF")
st.caption(
    "Sube un PDF, se separa en paginas individuales y cada pagina se nombra "
    "automaticamente segun su contenido, usando la API de Claude para "
    "analizar cada pagina como imagen."
)

with st.sidebar:
    st.header("Configuracion")
    api_key = st.text_input(
        "Anthropic API key",
        value=_get_secret("ANTHROPIC_API_KEY"),
        type="password",
        help="Consiguela en https://console.anthropic.com/settings/keys. "
        "No se guarda en ningun lado: solo se usa durante esta sesion.",
    )
    save_png = st.checkbox(
        "Incluir tambien la imagen PNG de cada pagina en el ZIP",
        value=False,
        help="Ademas del PDF, incluye el render usado para clasificar cada pagina.",
    )

uploaded_file = st.file_uploader("Arrastra o selecciona un archivo PDF", type=["pdf"])

if uploaded_file is not None:
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        st.error(f"El archivo pesa {size_mb:.1f} MB; el limite es {MAX_UPLOAD_MB} MB.")
        st.stop()

    if st.button("Procesar PDF", type="primary"):
        if not api_key:
            st.error("Falta la Anthropic API key. Pegala en la barra lateral.")
            st.stop()

        pdf_bytes = uploaded_file.getvalue()

        status_text = st.empty()
        progress_bar = st.progress(0.0)

        def _on_progress(done: int, total: int) -> None:
            progress_bar.progress(done / total)
            status_text.text(f"Clasificando pagina {done} de {total}...")

        try:
            with st.spinner("Separando el PDF en paginas..."):
                results = classify_pdf(
                    pdf_bytes=pdf_bytes,
                    api_key=api_key,
                    save_png=save_png,
                    progress_callback=_on_progress,
                )
        except PdfSplitError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:  # noqa: BLE001 - error inesperado, se muestra igual
            st.error(f"Error inesperado al procesar el PDF: {exc}")
            st.stop()

        status_text.empty()
        progress_bar.empty()

        n_ok = sum(1 for r in results if r.status == "ok")
        n_error = len(results) - n_ok
        if n_error == 0:
            st.success(f"Listo: {len(results)} paginas procesadas y clasificadas correctamente.")
        else:
            st.warning(
                f"Procesadas {len(results)} paginas: {n_ok} clasificadas, "
                f"{n_error} con error (revisa la columna Descripcion)."
            )

        table_rows = [
            {
                "Pagina original": r.original_page,
                "Nombre asignado": r.assigned_name,
                "Descripcion": r.description,
                "Estado": "OK" if r.status == "ok" else "Error",
            }
            for r in results
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Descargar todo (ZIP)",
                data=build_zip(results),
                file_name=f"{uploaded_file.name.rsplit('.', 1)[0]}_clasificado.zip",
                mime="application/zip",
                type="primary",
            )
        with col2:
            st.download_button(
                "Descargar solo el log (CSV)",
                data=build_csv_log(results),
                file_name="log_clasificacion.csv",
                mime="text/csv",
            )
