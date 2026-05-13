from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import database
import os
import httpx
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("backend.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Load environment variables from user_interface/.env
from dotenv import load_dotenv
load_dotenv(dotenv_path="./user_interface/.env")

# Read variables
NAS_SERVER_URL = os.getenv("NAS_SERVER_URL")
NAS_API_KEY = os.getenv("NAS_API_KEY")
BACKEND_PORT = os.getenv("BACKEND_PORT", "8080")

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar Base de Datos al arrancar
@app.on_event("startup")
async def startup_event():
    print("[INIT] Starting Backend...")
    try:
        database.init_db()
        print("[INIT] Database initialized successfully.")
    except Exception as e:
        print(f"[CRITICAL] Failed to initialize database: {e}")

# Estado global para la NAS
nas_status = {
    "last_heartbeat": None,
    "online": False
}

class FileData(BaseModel):
    path: str
    filename: str
    date_taken: str

def resolve_template(template, data_dict):
    """Resuelve variables temporales y de nombre en un template."""
    try:
        dt = datetime.fromisoformat(data_dict['date_taken'])
        # Añadimos todas las posibles variables que el usuario pueda usar en el UI
        return template.format(
            year=dt.year,
            month=f"{dt.month:02d}",
            day=f"{dt.day:02d}",
            hour=f"{dt.hour:02d}",
            minute=f"{dt.minute:02d}",
            second=f"{dt.second:02d}",
            filename=os.path.splitext(data_dict['filename'])[0],
            ext=os.path.splitext(data_dict['filename'])[1]
        )
    except Exception as e:
        print(f"[ERROR] Error resolviendo template: {e}")
        return template

@app.post("/new-file")
async def receive_file(data: FileData):
    data_dict = data.dict()
    print(f"[NEW] Archivo detectado: {data_dict['filename']}")
    
    # 1. Buscar configuración
    config = database.get_config_for_path(data_dict['path'])
    
    if not config:
        print(f"[ERROR] Import Config not found for: {data_dict['path']}")
        raise HTTPException(status_code=404, detail="Import Config not found")

    # 2. Calcular Destino
    target_folder = resolve_template(config['path_template'], data_dict)
    target_filename_raw = resolve_template(config['name_template'], data_dict)
    
    # Asegurar extensión
    ext = os.path.splitext(data_dict['filename'])[1]
    if not target_filename_raw.lower().endswith(ext.lower()):
        target_filename = target_filename_raw + ext
    else:
        target_filename = target_filename_raw

    # Forzamos barras de Linux (/) y quitamos la barra final si existe
    final_target_path = os.path.join(config['target_path'], target_folder).replace('\\', '/').rstrip('/')
    
    print(f"[OK] Destino calculado: {final_target_path}/{target_filename}")

    # 3. Guardar con el esquema completo
    success = database.save_processed_file({
        "original_path": data_dict['path'],
        "original_filename": data_dict['filename'],
        "target_path": final_target_path,
        "target_filename": target_filename,
        "date_taken": data_dict['date_taken'],
        "action": config.get('action', 'move')
    })

    if not success:
        raise HTTPException(status_code=500, detail="Error saving to database")

    return {"status": "success", "target": os.path.join(final_target_path, target_filename)}

@app.get("/health")
async def health_check():
    db_ok = database.check_db_health()
    nas_ok = False
    if nas_status["last_heartbeat"]:
        delta = datetime.now() - nas_status["last_heartbeat"]
        if delta.total_seconds() < 120:
            nas_ok = True
    return {
        "database": "online" if db_ok else "offline",
        "nas": "online" if nas_ok else "offline"
    }

@app.get("/heartbeat")
async def heartbeat():
    nas_status["last_heartbeat"] = datetime.now()
    nas_status["online"] = True
    return {"status": "ok", "time": nas_status["last_heartbeat"]}

@app.get("/configs")
async def get_configs():
    return database.get_all_configs()

@app.post("/configs")
async def add_config(data: dict):
    if database.add_config(data): return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to add configuration")

@app.put("/configs/{config_id}")
async def update_config(config_id: int, data: dict):
    if database.update_config(config_id, data): return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to update configuration")

@app.post("/configs/{config_id}/scan")
async def trigger_scan(config_id: int):
    config = database.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"X-API-KEY": os.getenv("NAS_API_KEY", "")}
            response = await client.post(
                f"{NAS_SERVER_URL}/scan",
                json={"path": config["source_path"]},
                headers=headers
            )
        if response.status_code == 202:
            return response.json()
        else:
            error_msg = response.json().get("detail", f"NAS error {response.status_code}")
            raise HTTPException(status_code=response.status_code, detail=error_msg)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"NAS unreachable: {str(e)}")

@app.get("/configs/{config_id}/scans")
async def get_config_scans(config_id: int):
    config = database.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return database.get_scans_by_path(config["source_path"])

async def process_import(config: dict):
    config_id = config['id']
    try:
        files = database.get_unprocessed_nas_files(config['source_path'])
        if not files:
            return
            
        scan_id = files[0].get('scan_id')
        processed_count = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"X-API-KEY": os.getenv("NAS_API_KEY", "")}
            for file in files:
                file_path = f"{file['file_path']}/{file['file_name']}".replace('\\', '/').replace('//', '/')
                
                try:
                    response = await client.post(
                        f"{NAS_SERVER_URL}/metadata",
                        json={"file_path": file_path},
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        meta = response.json()
                        date_taken = meta.get("date_taken")
                        if not date_taken:
                            logging.warning(f"Skipped {file_path}: No date_taken returned")
                            continue
                            
                        data_dict = {
                            "path": file['file_path'],
                            "filename": file['file_name'],
                            "date_taken": date_taken
                        }
                        
                        target_folder = resolve_template(config['path_template'], data_dict)
                        target_filename_raw = resolve_template(config['name_template'], data_dict)
                        
                        ext = os.path.splitext(file['file_name'])[1]
                        if not target_filename_raw.lower().endswith(ext.lower()):
                            target_filename = target_filename_raw + ext
                        else:
                            target_filename = target_filename_raw

                        final_target_path = os.path.join(config['target_path'], target_folder).replace('\\', '/').rstrip('/')

                        success = database.save_processed_file({
                            "original_path": file['file_path'],
                            "original_filename": file['file_name'],
                            "target_path": final_target_path,
                            "target_filename": target_filename,
                            "date_taken": date_taken,
                            "action": config.get('action', 'move')
                        })
                        if success:
                            processed_count += 1
                        else:
                            logging.warning(f"Skipped {file_path}: Failed to save in processed_files")
                except Exception as e:
                    logging.error(f"Import failed for {file_path}: {e}")
                    
        if scan_id and processed_count > 0:
            database.update_scan_imported_count(scan_id, processed_count)
            
    finally:
        database.set_config_import_status(config_id, 'idle')

@app.post("/configs/{config_id}/import")
async def trigger_import(config_id: int, background_tasks: BackgroundTasks):
    config = database.get_config_by_id(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
        
    database.set_config_import_status(config_id, 'importing')
    background_tasks.add_task(process_import, config)
    
    return {"status": "importing"}

@app.get("/stats/kpis")
async def get_stats_kpis(start_date: str = None, end_date: str = None):
    return database.get_stats_kpis(start_date, end_date)

@app.get("/stats/daily")
async def get_daily_stats(start_date: str = None, end_date: str = None):
    return database.get_daily_stats(start_date, end_date)

@app.get("/files")
async def get_files(status: str = None):
    """Obtiene el listado de archivos procesados."""
    return database.get_all_files(status)

@app.put("/files/{file_id}")
async def update_file(file_id: int, data: dict):
    """Actualiza manualmente un registro de archivo."""
    if database.update_processed_file(file_id, data):
        return {"status": "success"}
    raise HTTPException(status_code=500, detail="Failed to update file")

@app.post("/files/{file_id}/process")
async def process_file(file_id: int):
    """Ordena al NAS server que mueva/copie el fichero y actualiza el estado en BD."""
    # 1. Leer el registro
    file = database.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File record not found")

    action = file.get("action", "move")
    print(f"[PROCESS] Iniciando '{action}' para: {file['original_filename']}")

    # 2. Llamar al NAS server
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"X-API-KEY": os.getenv("NAS_API_KEY", os.getenv("API_KEY", ""))}
            source_file = f"{file['original_path']}/{file['original_filename']}".replace('\\', '/').replace('//', '/')
            destination_file = f"{file['target_path']}/{file['target_filename']}".replace('\\', '/').replace('//', '/')
            
            response = await client.post(
                f"{NAS_SERVER_URL}/file",
                json={
                    "source": source_file,
                    "destination": destination_file,
                    "action": action
                },
                headers=headers
            )
        if response.status_code == 200:
            database.set_file_status(file_id, "completed")
            print(f"[PROCESS] OK: {file['original_filename']} -> completed")
            return {"status": "completed", "file_id": file_id}
        else:
            error_msg = response.json().get("detail", f"NAS error {response.status_code}")
            database.set_file_status(file_id, "error", error_msg)
            print(f"[PROCESS] Error NAS: {error_msg}")
            raise HTTPException(status_code=502, detail=error_msg)

    except httpx.ConnectError:
        error_msg = "NAS server unreachable"
        database.set_file_status(file_id, "error", error_msg)
        print(f"[PROCESS] {error_msg}")
        raise HTTPException(status_code=503, detail=error_msg)
    except httpx.TimeoutException:
        error_msg = "NAS server timeout"
        database.set_file_status(file_id, "error", error_msg)
        print(f"[PROCESS] {error_msg}")
        raise HTTPException(status_code=504, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        database.set_file_status(file_id, "error", error_msg)
        print(f"[PROCESS] Excepción inesperada: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/")
def read_root():
    return {"message": "NAS Monitor Backend is running"}
