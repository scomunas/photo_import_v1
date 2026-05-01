import os
import time
import json
import sqlite3
import requests
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- PATHS AND CONFIGURATION SETUP ---
from pathlib import Path

# Get the absolute path of the directory where the script is located
# .resolve() handles symlinks and .parent gets the folder
SCRIPT_DIR = Path(__file__).resolve().parent

# Define paths relative to the script directory
CONFIG_FILE = SCRIPT_DIR / "nas_monitor.config.json"
DB_FILE = SCRIPT_DIR / "nas_monitor.pending.db"
LOG_DIR = SCRIPT_DIR / "logs"

if not LOG_DIR.exists():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

# 2. Generate a unique ID for this execution session
exec_id = time.strftime("%Y%m%d_%H%M")
LOG_FILE = LOG_DIR / f"{exec_id}.log"

# 3. Configure the logging engine
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logging.info(f"--- Process Started (ID: {exec_id}) ---")
# logging.info(f"DEBUG: __file__ is: {__file__}")
# logging.info(f"DEBUG: SCRIPT_DIR is: {SCRIPT_DIR}")
# logging.info(f"DEBUG: CONFIG_FILE path: {CONFIG_FILE}")
# logging.info(f"DEBUG: DB_FILE path: {DB_FILE}")

def load_config():
    """Reads the JSON configuration file to get IPs, ports, and folders."""
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

# Initialize configuration globally
config = load_config()

# --- DATABASE LOGIC (RESILIENCE FALLBACK) ---

def save_to_fallback(data):
    """
    Saves file metadata to a local SQLite database if the WebService is unreachable.
    This acts as a 'Dead Letter Queue' to ensure no files are lost.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        # Enable WAL (Write-Ahead Logging) mode to prevent file locking issues
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        
        # Create table if it doesn't exist yet
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT,
                filename TEXT,
                size INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert the metadata of the file that failed to send over the network
        cursor.execute(
            "INSERT INTO pending_files (path, filename, size) VALUES (?, ?, ?)",
            (data['path'], data['filename'], data['size'])
        )
        conn.commit()
        conn.close() # Always close connection to free up the file
        logging.warning(f"Fallback: Saved to SQLite -> {data['filename']}")
    except Exception as e:
        logging.error(f"CRITICAL: Could not write to SQLite: {e}")

# --- NETWORK COMMUNICATION ---

def notify_webservice(data):
    """Attempts to send file metadata to the Windows WebService via POST."""
    url = f"http://{config['endpoint_ip']}:{config['endpoint_port']}/new-file"
    try:
        # 5-second timeout ensures the script doesn't hang if the network is flaky
        response = requests.post(url, json=data, timeout=5)
        if response.status_code == 200:
            logging.info(f"Success: Notified WebService -> {data['filename']}")
            return True
        else:
            logging.error(f"WS Error: Status {response.status_code} for {data['filename']}")
    except Exception as e:
        logging.info(f"Connection Failed: {e}")
    
    # If network fails or server returns error, trigger local SQLite fallback
    save_to_fallback(data)
    return False

def heartbeat_loop():
    """
    Background loop that periodically tells the Windows app the NAS is alive.
    Runs in a separate thread to avoid blocking file monitoring.
    """
    url = f"http://{config['endpoint_ip']}:{config['endpoint_port']}/heartbeat"
    while True:
        try:
            requests.post(url, json={"status": "alive", "nas_id": "DS218"}, timeout=5)
            logging.info("Heartbeat sent.")
        except:
            # Failure is expected if the Windows PC is turned off
            logging.warning("Heartbeat failed (PC might be OFF).")
        
        # Sleep interval defined in the config (e.g., every 5 minutes)
        time.sleep(config['heartbeat_minutes'] * 60)

# --- FILE SYSTEM MONITORING ---

class NewFileHandler(FileSystemEventHandler):
    """Custom handler that reacts to file system events."""
    
    def on_closed(self, event):
        """Triggered when a file is finished being written and closed."""
        if event.is_directory:
            return
        
        filepath = event.src_path
        ext = os.path.splitext(filepath)[1].lower()
        
        # Only process files that match our allowed extensions
        if ext in config['extensions']:
            logging.info(f"Detected: {filepath}")
            
            # 2-second buffer to ensure the NAS has fully 'settled' the file
            time.sleep(2)
            
            # Gather metadata to send to the Windows App
            file_data = {
                "path": os.path.dirname(filepath),
                "filename": os.path.basename(filepath),
                "size": os.path.getsize(filepath),
                "timestamp": time.ctime(os.path.getmtime(filepath))
            }
            
            notify_webservice(file_data)

# --- MAIN SERVICE STARTUP ---

if __name__ == "__main__":
    logging.info("Starting NAS Monitor Service...")
    
    # Initialize and start the Heartbeat background thread
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    
    # Setup the Watchdog Observer to monitor all folders listed in config
    observer = Observer()
    for folder in config['folders_to_watch']:
        if os.path.exists(folder):
            observer.schedule(NewFileHandler(), folder, recursive=False)
            logging.info(f"Monitoring folder: {folder}")
        else:
            logging.error(f"Folder not found: {folder}")

    observer.start()
    
    try:
        # Keep the main thread alive while observers run in the background
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        observer.stop()
    
    observer.join()