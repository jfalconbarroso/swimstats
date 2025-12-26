from pathlib import Path
import streamlit as st

DATABASE_DIR = Path("databases")

def select_or_create_database(*, key_prefix: str = "db"):
    """Return Path to selected database or None if not ready."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted([p.name for p in DATABASE_DIR.glob("*.sqlite")])

    mode = st.radio(
        "Modo",
        ["Usar existente", "Crear nueva"],
        horizontal=True,
        key=f"{key_prefix}_mode",
    )

    if mode == "Usar existente":
        if not existing:
            st.info("No hay bases de datos aún. Crea una nueva.")
            return None
        name = st.selectbox(
            "Selecciona una base de datos",
            options=existing,
            key=f"{key_prefix}_existing",
        )
        return DATABASE_DIR / name

    # Crear nueva
    new_name = st.text_input(
        "Nombre de la nueva base de datos",
        placeholder="temporada_2025",
        key=f"{key_prefix}_newname",
    ).strip()

    if not new_name:
        return None

    if any(sep in new_name for sep in ["/", "\\"]):
        st.error("Introduce solo un nombre (sin rutas).")
        return None

    if not new_name.lower().endswith(".sqlite"):
        new_name += ".sqlite"

    path = DATABASE_DIR / new_name
    if path.exists():
        st.error("Esa base de datos ya existe. Elige otra o selecciona la existente.")
        return None
    return path

def select_database(*, key_prefix: str = "db"):
    """Return Path to selected database or None if not ready."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted([p.name for p in DATABASE_DIR.glob("*.sqlite")])

    if not existing:
        st.info("No hay bases de datos aún. Crea una nueva.")
        return None
    name = st.selectbox(
        "Selecciona una base de datos",
        options=existing,
        key=f"{key_prefix}_existing",
    )
    return DATABASE_DIR / name
