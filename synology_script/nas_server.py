import os
import shutil
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

def normalize_path(p: str) -> str:
    """Convierte barras invertidas a slash de Linux y elimina trailing slash."""
    return p.replace('\\', '/').rstrip('/')

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = FastAPI(title="NAS Action Server")


class ActionRequest(BaseModel):
    original_path: str
    original_filename: str
    target_path: str
    target_filename: str
    action: str = "move"  # "move" o "copy"


def resolve_unique_target(target_path: str, target_filename: str) -> str:
    """Devuelve un nombre de fichero único añadiendo _1, _2... si ya existe."""
    full = os.path.join(target_path, target_filename)
    if not os.path.exists(full):
        return target_filename

    name, ext = os.path.splitext(target_filename)
    counter = 1
    while True:
        candidate = f"{name}_{counter}{ext}"
        if not os.path.exists(os.path.join(target_path, candidate)):
            logging.info(f"[RENAME] '{target_filename}' ya existe -> usando '{candidate}'")
            return candidate
        counter += 1


@app.post("/action")
def execute_action(data: ActionRequest):
    """Mueve o copia un fichero según la instrucción recibida."""
    # Normalizar rutas: el backend puede venir de Windows con barras invertidas
    original_path = normalize_path(data.original_path)
    target_path   = normalize_path(data.target_path)

    source_full = f"{original_path}/{data.original_filename}"
    target_full = f"{target_path}/{data.target_filename}"

    if not os.path.exists(source_full):
        logging.error(f"Fichero origen no encontrado: {source_full}")
        raise HTTPException(status_code=404, detail=f"Source file not found: {source_full}")

    try:
        # Crear carpetas de destino si no existen
        os.makedirs(target_path, exist_ok=True)

        # Resolver nombre único para no sobreescribir
        final_filename = resolve_unique_target(target_path, data.target_filename)
        target_full = f"{target_path}/{final_filename}"

        if data.action == "copy":
            shutil.copy2(source_full, target_full)
            logging.info(f"[COPY] {source_full} -> {target_full}")
        else:
            shutil.move(source_full, target_full)
            logging.info(f"[MOVE] {source_full} -> {target_full}")

        return {"status": "success", "target": target_full, "final_filename": final_filename}

    except Exception as e:
        logging.error(f"Error ejecutando acción '{data.action}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
