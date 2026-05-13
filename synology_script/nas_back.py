import os
import uuid
import uvicorn
import asyncio
import shutil
import psycopg2
import exifread
import re
import logging
from datetime import datetime
from psycopg2.extras import execute_values, DictCursor
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from dotenv import load_dotenv

# --- LOGGING CONFIGURATION ---
# Create log directory if it doesn't exist
LOG_DIR = "log"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

# Generate log filename based on current date
log_filename = os.path.join(LOG_DIR, f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(), # Keeps output in console for real-time monitoring
        logging.FileHandler(log_filename)
    ]
)
logger = logging.getLogger("nas_manager")

# Try to load Hachoir for video metadata
try:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser
    HACHOIR_AVAILABLE = True
except ImportError:
    logger.debug("Hachoir not found. Video metadata extraction will be limited.")
    HACHOIR_AVAILABLE = False

load_dotenv()

# --- CONFIGURATION ---
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

API_KEY = os.getenv("API_KEY")
PORT = int(os.getenv("PORT", 9090))
BUFFER_SIZE = int(os.getenv("BUFFER_SIZE", 5000))

# --- EXTENSION & BLACKLIST CLEANING ---
def clean_env_list(env_key, default):
    raw = os.getenv(env_key, default)
    return [item.strip() for item in raw.split(',') if item.strip()]

PHOTO_EXTENSIONS = tuple(e.lower() if e.startswith('.') else f".{e.lower()}" for e in clean_env_list("PHOTO_EXTENSIONS", ".jpg,.jpeg,.png"))
VIDEO_EXTENSIONS = tuple(e.lower() if e.startswith('.') else f".{e.lower()}" for e in clean_env_list("VIDEO_EXTENSIONS", ".mp4,.mov,.avi"))
ALL_EXTENSIONS = PHOTO_EXTENSIONS + VIDEO_EXTENSIONS
PATH_BLACKLIST = clean_env_list("PATH_BLACKLIST", "@eaDir,#recycle,.DS_Store")

app = FastAPI(title="Synology NAS Media Manager API")
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=True)
worker_lock = asyncio.Lock()

# --- MODELS ---
class ScanRequest(BaseModel):
    path: str

class FileOperationRequest(BaseModel):
    source: str
    destination: str
    action: str

class MetadataRequest(BaseModel):
    file_path: str

# --- DATABASE INITIALIZATION ---
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    logger.debug("Initializing database tables...")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS nas_scans (
                            id UUID PRIMARY KEY, 
                            path TEXT NOT NULL, 
                            status TEXT DEFAULT 'pending', 
                            total_count INTEGER DEFAULT 0,
                            imported_count INTEGER DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
            cur.execute('''CREATE TABLE IF NOT EXISTS nas_files (
                            id SERIAL PRIMARY KEY,
                            scan_id UUID REFERENCES nas_scans(id) ON DELETE CASCADE, 
                            file_path TEXT, 
                            file_name TEXT)''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_nas_scan_id ON nas_files(scan_id)')
            conn.commit()
            logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"CRITICAL ERROR during DB init: {e}")
    finally:
        conn.close()

init_db()

# --- SECURITY ---
async def verify_api_key(header_value: str = Depends(api_key_header)):
    if header_value != API_KEY:
        logger.warning(f"SECURITY ALERT: Invalid API Key attempt: {header_value}")
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return header_value

# --- METADATA UTILS ---
def get_exif_date(file_path):
    try:
        with open(file_path, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            for key in ['EXIF DateTimeOriginal', 'Image DateTime', 'EXIF DateTimeDigitized']:
                date_tag = tags.get(key)
                if date_tag:
                    return datetime.strptime(str(date_tag), '%Y:%m:%d %H:%M:%S')
    except Exception as e:
        logger.debug(f"Failed to read EXIF for {file_path}: {e}")
        return None

def get_video_date(file_path):
    if not HACHOIR_AVAILABLE: return None
    try:
        parser = createParser(file_path)
        with parser:
            metadata = extractMetadata(parser)
            if metadata:
                c_date = metadata.get('creation_date')
                if c_date and c_date.year > 1970: return c_date
    except Exception as e:
        logger.debug(f"Failed to read video metadata for {file_path}: {e}")
        return None

def get_date_from_filename(filename):
    patterns = [
        r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',
        r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})',
        r'IMG_(\d{4})(\d{2})(\d{2})_(\d{6})'
    ]
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            try:
                p = match.groups()
                return datetime(int(p[0]), int(p[1]), int(p[2]), int(p[3]), int(p[4]), int(p[5]))
            except: continue
    return None

def get_unique_path(target_path: str):
    if not os.path.exists(target_path): return target_path
    base, extension = os.path.splitext(target_path)
    counter = 1
    new_path = f"{base}_{counter}{extension}"
    while os.path.exists(new_path):
        counter += 1
        new_path = f"{base}_{counter}{extension}"
    return new_path

# --- SCAN PROCESS ---
def process_scan(scan_id: str, root_path: str):
    logger.debug(f"Starting scan process for ID: {scan_id} at Path: {root_path}")
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE nas_scans SET status = 'running' WHERE id = %s", (scan_id,))
            conn.commit()

            logger.debug(f"Cleaning old scan data for path: {root_path}")
            cur.execute("UPDATE nas_scans SET status = 'superseded' WHERE path = %s AND id != %s AND status = 'completed'", (root_path, scan_id))
            cur.execute("DELETE FROM nas_files WHERE scan_id IN (SELECT id FROM nas_scans WHERE path = %s AND id != %s AND status = 'superseded')", (root_path, scan_id))
            conn.commit()

            file_buffer = []
            count = 0
            
            for root, dirs, files in os.walk(root_path):
                original_dirs = list(dirs)
                dirs[:] = [d for d in dirs if not any(word in d for word in PATH_BLACKLIST)]
                for skipped in set(original_dirs) - set(dirs):
                    logger.debug(f"Skipping blacklisted directory: {skipped}")
                
                for name in files:
                    if any(word in name for word in PATH_BLACKLIST):
                        logger.debug(f"Skipping blacklisted file: {name}")
                        continue
                    
                    if name.lower().endswith(ALL_EXTENSIONS):
                        file_buffer.append((scan_id, root, name))
                        count += 1
                        
                        if len(file_buffer) >= BUFFER_SIZE:
                            logger.debug(f"Inserting batch of {len(file_buffer)} files...")
                            execute_values(cur, "INSERT INTO nas_files (scan_id, file_path, file_name) VALUES %s", file_buffer)
                            conn.commit()
                            file_buffer = []

            if file_buffer:
                logger.debug(f"Inserting final batch of {len(file_buffer)} files...")
                execute_values(cur, "INSERT INTO nas_files (scan_id, file_path, file_name) VALUES %s", file_buffer)
                conn.commit()
            
            cur.execute("UPDATE nas_scans SET status = 'completed', total_count = %s WHERE id = %s", (count, scan_id))
            conn.commit()
            logger.info(f"Scan {scan_id} finished successfully. {count} files found.")

    except Exception as e:
        logger.error(f"Error during scan {scan_id}: {e}")
        if conn: conn.rollback()
        with conn.cursor() as cur:
            cur.execute("UPDATE nas_scans SET status = %s WHERE id = %s", (f"error: {str(e)}", scan_id))
            conn.commit()
    finally:
        if conn: conn.close()

async def queue_orchestrator():
    logger.debug("Queue Orchestrator check started.")
    async with worker_lock:
        while True:
            conn = get_db_connection()
            next_task = None
            try:
                with conn.cursor(cursor_factory=DictCursor) as cur:
                    cur.execute("SELECT id FROM nas_scans WHERE status = 'running'")
                    if cur.fetchone():
                        logger.debug("A scan is already running. Orchestrator waiting.")
                        break
                    
                    cur.execute("SELECT id, path FROM nas_scans WHERE status IN ('pending', 'queued') ORDER BY created_at ASC LIMIT 1")
                    next_task = cur.fetchone()
            finally:
                conn.close()

            if not next_task:
                logger.debug("No more pending tasks.")
                break

            logger.info(f"Orchestrator starting task {next_task['id']}")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, process_scan, str(next_task['id']), next_task['path'])

# --- ENDPOINTS ---

@app.post("/scan", status_code=202)
async def start_scan(payload: ScanRequest, background_tasks: BackgroundTasks, api_key: str = Depends(verify_api_key)):
    logger.info(f"Request received: SCAN {payload.path}")
    target_path = os.path.abspath(payload.path)
    if not os.path.exists(target_path):
        logger.error(f"Scan failed: Path not found {target_path}")
        raise HTTPException(status_code=400, detail="Target path does not exist")
    
    new_id = str(uuid.uuid4())
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM nas_scans WHERE status = 'running'")
            status = 'queued' if cur.fetchone() else 'pending'
            cur.execute("INSERT INTO nas_scans (id, path, status) VALUES (%s, %s, %s)", (new_id, target_path, status))
            conn.commit()
    finally:
        conn.close()
    
    logger.info(f"Scan {new_id} added to queue as '{status}'")
    background_tasks.add_task(queue_orchestrator)
    return {"scan_id": new_id, "status": status}

@app.post("/metadata")
async def extract_metadata(payload: MetadataRequest, api_key: str = Depends(verify_api_key)):
    logger.debug(f"Request received: METADATA for {payload.file_path}")
    if not os.path.exists(payload.file_path):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(payload.file_path)
    ext = os.path.splitext(payload.file_path)[1].lower()
    date_taken, source = None, "unknown"

    if ext in PHOTO_EXTENSIONS:
        date_taken = get_exif_date(payload.file_path)
        source = "exif" if date_taken else source
    elif ext in VIDEO_EXTENSIONS:
        date_taken = get_video_date(payload.file_path)
        source = "hachoir" if date_taken else source

    if not date_taken:
        date_taken = get_date_from_filename(filename)
        source = "filename" if date_taken else source

    if not date_taken:
        st = os.stat(payload.file_path)
        try: date_taken = datetime.fromtimestamp(st.st_birthtime)
        except AttributeError: date_taken = datetime.fromtimestamp(st.st_ctime)
        source = "os_stats"

    logger.debug(f"Metadata result for {filename}: {date_taken} (Source: {source})")
    return {"filename": filename, "date_taken": date_taken.isoformat(), "source": source}

@app.post("/file")
async def file_operation(payload: FileOperationRequest, api_key: str = Depends(verify_api_key)):
    logger.info(f"Request received: {payload.action} from {payload.source}")
    if not os.path.exists(payload.source):
        logger.error(f"File op failed: Source missing {payload.source}")
        raise HTTPException(status_code=404, detail="Source not found")
    
    os.makedirs(os.path.dirname(payload.destination), exist_ok=True)
    final_dest = get_unique_path(payload.destination)
    
    try:
        if payload.action == "move":
            shutil.move(payload.source, final_dest)
        elif payload.action == "copy":
            if os.path.isdir(payload.source):
                shutil.copytree(payload.source, final_dest)
            else:
                shutil.copy2(payload.source, final_dest)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        
        logger.info(f"File operation successful: {final_dest}")
        return {"status": "success", "destination": final_dest}
    except Exception as e:
        logger.error(f"File operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    logger.info("--- SERVER STARTING ---")
    logger.info(f"Log file: {log_filename}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)