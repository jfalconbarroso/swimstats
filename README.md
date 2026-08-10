# SwimStats Dashboard

## Overview
This project synchronizes swimming meet result PDFs from a public ownCloud/WebDAV share, extracts race times, stores them in a local SQLite database, and provides a Streamlit dashboard with percentiles, swimmer evolution charts, CSV export, and PDF reports.

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
