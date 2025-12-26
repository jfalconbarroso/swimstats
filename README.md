# SwimStats Dashboard

## Overview
This project synchronizes swimming meet result PDFs from a public ownCloud/WebDAV share, extracts race times, stores them in a local SQLite database, and provides a Streamlit dashboard with percentiles, swimmer evolution charts, CSV export, and PDF reports.

## Important: ownCloud access modes (401 Unauthorized fix)

ownCloud public shares are commonly exposed via two WebDAV modes:

1) **Public Files WebDAV** (token in URL; often no auth required)
   - `https://<host>/owncloud/remote.php/dav/public-files/<SHARE_TOKEN>/...`

2) **Public Share WebDAV** (Basic Auth required)
   - `https://<host>/owncloud/public.php/webdav/...`
   - Username: `<SHARE_TOKEN>`
   - Password: share password (often empty if the share has no password)

This package now supports both modes. Configure it in:

- `swimstats/config.py`

Key settings:
- `USE_PUBLIC_SHARE_WEBDAV = True`  (recommended if you see 401 errors)
- `SHARE_PASSWORD = "..."` if the public link has a password

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```bash
## 1) Dashboard de SYNC (selección de carpetas + sincronización)
streamlit run sync_dashboard.py

## 2) Dashboard de análisis/plots (selección de DB + gráficos/informes)
streamlit run plot_dashboard.py
```


### Bases de datos (directorio único)

Todas las bases de datos SQLite se gestionan exclusivamente dentro del directorio `databases/` (se crea automáticamente si no existe).

En ambos dashboards podrás:
- **Usar una DB existente** desde un desplegable (archivos `*.sqlite` dentro de `databases/`).
- **Crear una DB nueva** indicando solo el nombre (se guardará como `databases/<nombre>.sqlite`).

No es necesario (ni posible) introducir rutas manuales: el objetivo es evitar errores y mantener todo centralizado.

> Nota: `dashboard.py` se mantiene como legado/monolítico, pero el flujo recomendado es ejecutar los dos dashboards separados.


## Dates and daily best marks
Event dates are normalized to day-only (YYYY-MM-DD). If multiple results exist for the same swimmer/event/sex/YY on the same day, only the best (minimum) time is kept.


## Campo YY
El número junto al nombre es el año de nacimiento en 2 dígitos (YY), no la edad.


## Normalización de nombres (acentos)
Durante el parsing se eliminan los acentos/diacríticos en los nombres para evitar duplicados (p. ej. `PÉREZ` vs `PEREZ`).


## Visualización: todo el histórico o por etiqueta
En el dashboard de plots (`plot_dashboard.py`) puedes elegir el **ámbito de datos**:

- **Todo el histórico**: ignora `dataset_tag` y analiza toda la base de datos.
- **Filtrar por etiqueta**: selecciona una o varias etiquetas (`dataset_tag`) para analizar un subconjunto (por ejemplo, temporada o fuente concreta).


## Etiquetas manuales (dataset_tag)
Cada sincronización en el dashboard de SYNC requiere una etiqueta manual (`dataset_tag`). Esa etiqueta se guarda en `results.dataset_tag` y sirve para segmentar análisis cuando lo necesites.
