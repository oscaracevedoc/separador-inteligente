# Separador Inteligente de PDF

App web (Streamlit) que separa un PDF en paginas individuales y usa la API
de Claude para analizar cada pagina como imagen y asignarle un nombre de
archivo descriptivo y una descripcion de una linea.

Pensada para correr **online** (Streamlit Community Cloud) y ser usada por
cualquier persona desde el navegador, sin instalar nada. Cada usuario usa su
propia clave de API de Anthropic; nada se guarda en el servidor.

## Funcionalidad

1. Subir un PDF (drag & drop o selector de archivo).
2. Cada pagina se renderiza como imagen y se manda a Claude, que devuelve un
   nombre de archivo corto (`factura_proveedor_xyz`) y una descripcion de una
   linea.
3. Se muestra una tabla con: pagina original, nombre asignado, descripcion y
   estado.
4. Se descarga un ZIP con un PDF por pagina (nombrado `01_nombre.pdf`,
   `02_nombre.pdf`, ...) y un log `log_clasificacion.csv`.

Todo el procesamiento ocurre en memoria durante la sesion del navegador; no
se persiste ningun archivo en el servidor (asi funciona de forma segura con
varios usuarios usando la app al mismo tiempo).

## Stack y decisiones de diseno

- **Streamlit** para la interfaz web.
- **pypdf** para separar el PDF en paginas individuales.
- **PyMuPDF** (`fitz`) en vez de `pdf2image` para renderizar cada pagina a
  PNG antes de mandarla a Claude — no depende de instalar el binario
  `poppler` en el servidor, solo `pip install`. Esto permite analizar cada
  pagina como **imagen** (no solo texto extraido), por lo que tambien
  funciona con PDFs escaneados sin capa de texto.
- **Anthropic SDK** (`claude-sonnet-5`) con `output_config.format` (JSON
  schema) para forzar una respuesta estructurada (`filename_slug` +
  `description`).
- Sin base de datos ni almacenamiento persistente: el resultado se entrega
  como descarga (ZIP + CSV) generada en memoria, no como archivos en el
  servidor.

## Manejo de errores

- **PDF invalido/corrupto, protegido con contrasena, o sin paginas**: error
  claro antes de llamar a la API.
- **Fallas de la API en una pagina puntual** (rate limit, rechazo del
  modelo, respuesta invalida): esa pagina queda con nombre de respaldo
  (`NN_pagina_sin_clasificar.pdf`) y estado `error`; el resto del PDF se
  sigue procesando.
- **Nombres de archivo**: sanitizados (sin tildes, minusculas, solo
  `[a-z0-9_]`, maximo 6 palabras), con prefijo de pagina (`01_`, `02_`, ...).
- **Limite de tamano**: 40 MB por archivo y 300 paginas (configurable en
  `app.py` / `src/pdf_split.py`), para evitar procesos excesivamente largos
  o costosos.

## Uso local (desarrollo)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # pega tu ANTHROPIC_API_KEY ahi
streamlit run app.py
```

## Desplegar online (Streamlit Community Cloud, gratis)

1. Entra a **https://share.streamlit.io** e inicia sesion con tu cuenta de
   GitHub (la misma cuenta donde vive este repositorio).
2. Click en **"Create app"** (o "New app") → **"Deploy a public app from
   GitHub"**.
3. Selecciona:
   - Repository: `oscaracevedoc/separador-inteligente`
   - Branch: `main`
   - Main file path: `app.py`
4. Antes de desplegar, abre **"Advanced settings"** → **Secrets**, y pega:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-tu-clave-aqui"
   APP_PASSWORD = "una-clave-que-tu-elijas"
   ```
   - `ANTHROPIC_API_KEY` es opcional: si lo dejas vacio, cada persona que use
     la app debe pegar su propia clave en la barra lateral. Si lo configuras
     aqui, la app ya viene con una clave por defecto para todos — util para
     un grupo cerrado, pero cada pagina procesada consume tu cuota de la API.
   - `APP_PASSWORD` es opcional y controla el acceso a la app: si lo
     configuras, cualquiera que entre al link debe ingresar esa clave antes
     de ver la app (una pantalla simple, la misma clave para todos). Si lo
     dejas vacio, la app queda abierta a cualquiera con el link.
5. Click en **Deploy**. En 1-2 minutos la app queda disponible en una URL
   publica del tipo `https://separador-inteligente-xxxx.streamlit.app`,
   accesible desde cualquier navegador, en cualquier dispositivo.

Cada vez que se haga `git push` a `main`, Streamlit Community Cloud
redespliega la app automaticamente con los cambios.

## Estructura

```
separador-inteligente/
  app.py                Interfaz Streamlit
  src/
    pdf_split.py          Separa el PDF en paginas (PDF individual + PNG para vision)
    classifier.py         Llamada a la API de Claude (prompt + structured output)
    naming.py              Sanitizacion de nombres + numeracion
    pipeline.py             Orquesta split -> clasificar -> nombrar -> empaquetar en ZIP
  requirements.txt
  .env.example
```
