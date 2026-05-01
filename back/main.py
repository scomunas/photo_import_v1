from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import database
import uvicorn
import os
import exifread
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
from datetime import datetime
from pathlib import Path

app = FastAPI(title="NAS File Monitor Backend")

# Data Models
class FileMetadata(BaseModel):
    path: str
    filename: str
    size: int
    timestamp: str

class HeartbeatData(BaseModel):
    status: str
    nas_id: str

def get_date_taken(filepath):
    """Extracts the capture date from EXIF (photos) or Metadata (videos)."""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        
        # --- PHOTOS (EXIF) ---
        if ext in ['.jpg', '.jpeg', '.tiff', '.heic']:
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f, stop_at_idx='EXIF DateTimeOriginal')
                date_str = tags.get('EXIF DateTimeOriginal') or tags.get('Image DateTime')
                if date_str:
                    # Format: YYYY:MM:DD HH:MM:SS
                    return datetime.strptime(str(date_str), '%Y:%m:%d %H:%M:%S')

        # --- VIDEOS (Hachoir) ---
        elif ext in ['.mp4', '.mov', '.avi', '.mkv']:
            parser = createParser(filepath)
            if parser:
                with parser:
                    metadata = extractMetadata(parser)
                    if metadata and metadata.has('creation_date'):
                        return metadata.get('creation_date')
    except Exception as e:
        print(f"Error extracting metadata from {filepath}: {e}")
    
    return None

# Startup Event
@app.on_event("startup")
def startup_event():
    database.init_db()

@app.get("/")
def read_root():
    return {"message": "NAS Monitor Backend is running"}

def resolve_template(template: str, dt: datetime):
    """Replaces wildcards in the template with actual date values."""
    if not dt:
        return ""
    # We use :02d to ensure 2 digits for months/days/etc.
    return template.format(
        year=dt.year,
        month=f"{dt.month:02d}",
        day=f"{dt.day:02d}",
        hour=f"{dt.hour:02d}",
        minute=f"{dt.minute:02d}",
        second=f"{dt.second:02d}"
    )

@app.post("/new-file")
async def receive_file(data: FileMetadata):
    try:
        # 1. Guardar registro inicial y buscar configuración
        config = database.save_file_record(data.dict())
        if not config:
            return {"status": "error", "message": "No configuration found for this path"}

        # 2. La ruta es idéntica gracias al montaje espejo en /volumeX/...
        full_path = os.path.join(data.path, data.filename)

        # 3. Extraer la fecha de captura (o usar la del sistema como fallback)
        date_taken = get_date_taken(full_path)
        if not date_taken:
            # Fallback: intentar parsear el timestamp que envía la NAS (time.ctime format)
            try:
                date_taken = datetime.strptime(data.timestamp, "%a %b %d %H:%M:%S %Y")
            except:
                date_taken = datetime.now()

        # 4. Calcular ruta de destino final
        folder_structure = resolve_template(config['path_template'], date_taken)
        # La ruta final para la NAS (donde ella debe ejecutar el comando)
        final_nas_folder = os.path.join(config['target_path'], folder_structure)
        final_nas_path = os.path.join(final_nas_folder, data.filename)

        # 5. Actualizar registro con la fecha real detectada
        data_dict = data.dict()
        data_dict['date_taken'] = date_taken
        database.save_file_record(data_dict) 

        return {
            "status": "success",
            "action": config['action'],
            "target_folder": final_nas_folder,
            "target_path": final_nas_path,
            "date_detected": str(date_taken)
        }
    except Exception as e:
        print(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
