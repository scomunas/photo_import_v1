import os
import time
import json
import requests
import logging
import exifread
import re
import subprocess
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Librerías opcionales para vídeo
try:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser
    HACHOIR_AVAILABLE = True
except ImportError:
    HACHOIR_AVAILABLE = False

# --- CONFIGURACIÓN ---
CONFIG_FILE = "nas_monitor.config.json"
LOG_DIR = "logs"

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return None

config = load_config()
if not config:
    exit(1)

BACKEND_URL = f"http://{config['endpoint_ip']}:{config['endpoint_port']}"
FOLDERS_TO_WATCH = config['folders_to_watch']
HEARTBEAT_INTERVAL = config['heartbeat_minutes'] * 60
PHOTO_EXTENSIONS = tuple(config['photo_extensions'])
VIDEO_EXTENSIONS = tuple(config['video_extensions'])

# --- LOGGING ---
log_filename = datetime.now().strftime("%Y%m%d_%H%M%S.log")
log_path = os.path.join(LOG_DIR, log_filename)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # logging.StreamHandler(), # Uncomment to see logs in console
        logging.FileHandler(log_path)
    ]
)

# --- LÓGICA DE EXTRACCIÓN DE FECHAS ---
class PhotoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            self.process_file(event.src_path)

    def process_file(self, file_path):
        if "@eaDir" in file_path or "/." in file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in PHOTO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
            return

        time.sleep(2) 
        
        try:
            if not os.path.exists(file_path):
                return

            filename = os.path.basename(file_path)
            logging.info(f"Procesando: {filename}")

            # ORDEN DE PRIORIDAD DE FECHAS
            # 1. EXIF (Solo para fotos)
            date_taken = None

            # 1. METADATOS (EXIF para fotos / Hachoir para vídeos)
            if ext in PHOTO_EXTENSIONS:
                date_taken = self.get_exif_date(file_path)
            elif ext in VIDEO_EXTENSIONS and HACHOIR_AVAILABLE:
                date_taken = self.get_video_date(file_path)
            
            # 2. NOMBRE DEL ARCHIVO
            if not date_taken:
                date_taken = self.get_date_from_filename(filename)
                if date_taken:
                    logging.info(f"Fecha extraída del NOMBRE: {date_taken}")

            # 3. FECHA DE CREACIÓN ORIGINAL DEL SISTEMA
            if not date_taken:
                st = os.stat(file_path)
                try:
                    # Intentar obtener birth time (fecha de creación)
                    timestamp = st.st_birthtime
                except AttributeError:
                    # Si no está disponible (algunos sistemas Linux), usamos ctime
                    timestamp = st.st_ctime
                
                date_taken = datetime.fromtimestamp(timestamp)
                logging.info(f"Usando fecha de CREACIÓN original: {date_taken}")

            data = {
                "path": os.path.dirname(file_path),
                "filename": filename,
                "date_taken": date_taken.isoformat()
            }
            
            response = requests.post(f"{BACKEND_URL}/new-file", json=data, timeout=5)
            if response.status_code == 200:
                logging.info(f"Backend notificado: {filename} -> {date_taken}")
            else:
                logging.error(f"Error Backend ({response.status_code}): {response.text}")

        except Exception as e:
            logging.error(f"Error CRÍTICO en {file_path}: {e}")

    def get_exif_date(self, file_path):
        """Prioridad 1: Metadatos EXIF."""
        try:
            with open(file_path, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                
                # Lista de tags donde suele estar la fecha de captura
                date_keys = [
                    'EXIF DateTimeOriginal', 
                    'Image DateTime', 
                    'EXIF DateTimeDigitized',
                    'Image DateTimeOriginal'
                ]
                
                for key in date_keys:
                    date_tag = tags.get(key)
                    if date_tag:
                        try:
                            # Intentamos parsear el formato estándar EXIF
                            dt = datetime.strptime(str(date_tag), '%Y:%m:%d %H:%M:%S')
                            logging.info(f"Fecha extraída de EXIF ({key}): {dt}")
                            return dt
                        except:
                            continue
            return None
        except:
            return None

    def get_video_date(self, file_path):
        """Intenta extraer la fecha de creación del vídeo usando Hachoir."""
        try:
            parser = createParser(file_path)
            if not parser:
                return None
            with parser:
                metadata = extractMetadata(parser)
                if metadata:
                    creation_date = metadata.get('creation_date')
                    if creation_date:
                        # FILTRO DE SEGURIDAD: Si la fecha es el "punto cero" (1904), ignoramos
                        if creation_date.year > 1970:
                            logging.info(f"Fecha extraída de VÍDEO (Hachoir): {creation_date}")
                            return creation_date
                        else:
                            logging.warning(f"Ignorando fecha de vídeo sospechosa (época 1904): {creation_date}")
            return None
        except Exception as e:
            logging.warning(f"Error leyendo metadatos de vídeo: {e}")
            return None

    def get_date_from_filename(self, filename):
        """Prioridad 2: Buscar patrones YYYYMMDD_HHMMSS en el nombre."""
        # Regex mejorada para capturar más variaciones
        patterns = [
            r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',       # 20170224_163048
            r'(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})', # 2022-05-25-14-15-27
            r'(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})(\d{2})',    # 2021-08-08-212208
            r'IMG_(\d{4})(\d{2})(\d{2})_(\d{6})'                 # IMG_20170224_163048
        ]
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                try:
                    parts = match.groups()
                    if len(parts) == 6:
                        return datetime(int(parts[0]), int(parts[1]), int(parts[2]), 
                                        int(parts[3]), int(parts[4]), int(parts[5]))
                    elif len(parts) == 4: # Caso IMG_...
                        d = parts[0]+parts[1]+parts[2]
                        t = parts[3]
                        return datetime.strptime(f"{d}_{t}", "%Y%m%d_%H%M%S")
                except:
                    continue
        return None

def heartbeat_loop():
    while True:
        try:
            requests.get(f"{BACKEND_URL}/heartbeat", timeout=5)
        except:
            pass 
        time.sleep(HEARTBEAT_INTERVAL)

def check_and_fix_inotify_limit():
    """Comprueba el límite de inotify y trata de subirlo automáticamente si es muy bajo."""
    try:
        with open('/proc/sys/fs/inotify/max_user_watches', 'r') as f:
            current_limit = int(f.read().strip())
        
        target_limit = 1048576
        if current_limit < 100000:
            logging.warning(f"Límite inotify actual ({current_limit}) es bajo. Intentando ajustarlo a {target_limit}...")
            
            # 1. Intentar directamente (si somos root)
            res = subprocess.run(["sysctl", f"fs.inotify.max_user_watches={target_limit}"], capture_output=True)
            if res.returncode != 0:
                # 2. Intentar con sudo no interactivo (-n)
                res = subprocess.run(["sudo", "-n", "sysctl", f"fs.inotify.max_user_watches={target_limit}"], capture_output=True)
                
            if res.returncode == 0:
                logging.info(f"Límite inotify ajustado correctamente a {target_limit}.")
            else:
                logging.error("\n" + "!"*65)
                logging.error("ATENCIÓN: No se pudo aumentar el límite de inotify automáticamente.")
                logging.error("Si el script falla (OSError 28), ejecuta esto manualmente:")
                logging.error(f"  sudo sysctl fs.inotify.max_user_watches={target_limit}")
                logging.error("!"*65 + "\n")
    except Exception as e:
        pass # Ignorar si no estamos en Linux o no existe el archivo

def start_monitor():
    check_and_fix_inotify_limit()
    
    observer = Observer()
    handler = PhotoHandler()
    
    for folder in FOLDERS_TO_WATCH:
        if os.path.exists(folder):
            observer.schedule(handler, folder, recursive=True)
            logging.info(f"Vigilando: {folder}")
        else:
            logging.error(f"Carpeta no existe: {folder}")

    try:
        observer.start()
    except OSError as e:
        if getattr(e, 'errno', None) == 28:
            logging.error("\n[CRÍTICO] ERROR 28: Límite inotify alcanzado. Hay demasiadas carpetas.")
            logging.error("Por favor, ejecuta el siguiente comando en la terminal para solucionarlo:")
            logging.error("sudo sysctl fs.inotify.max_user_watches=1048576\n")
            exit(1)
        raise
    
    import threading
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    logging.info(f"Monitor iniciado (Backend: {BACKEND_URL})")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_monitor()