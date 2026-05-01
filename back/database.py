import psycopg2
from psycopg2.extras import RealDictCursor
import os
import time
from dotenv import load_dotenv

# Load variables from .env file if it exists
load_dotenv()

# Database configuration from environment variables
# In Docker, DB_HOST will be 'db'. In local dev, it will default to 'localhost'.
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "photo_import")
DB_USER = os.getenv("DB_USER", "user_photo")
DB_PASS = os.getenv("DB_PASSWORD", "password_photo")

def get_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def init_db():
    """Initializes the PostgreSQL database and creates necessary tables."""
    retries = 5
    while retries > 0:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # 1. Table for import configurations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS import_configs (
                    id SERIAL PRIMARY KEY,
                    source_path TEXT UNIQUE NOT NULL, -- Folder monitored in NAS (must be unique)
                    target_path TEXT NOT NULL,        -- Base destination folder in NAS (for the NAS to execute)
                    action TEXT NOT NULL,             -- 'copy' or 'move'
                    path_template TEXT NOT NULL,      -- e.g. "{year}/{month}/{day}"
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 2. Table for imported files
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS imported_files (
                    id SERIAL PRIMARY KEY,
                    path TEXT NOT NULL,               -- Original folder from NAS
                    filename TEXT NOT NULL,
                    size BIGINT NOT NULL,
                    timestamp TEXT NOT NULL,          -- File modification time (filesystem)
                    date_taken TIMESTAMP,             -- Actual EXIF/Metadata capture date
                    status TEXT DEFAULT 'pending',    -- 'pending', 'done', 'failed'
                    processed_at TIMESTAMP,
                    error_msg TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 3. Table for heartbeats (Legacy)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS heartbeats (
                    id SERIAL PRIMARY KEY,
                    nas_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # --- SEED DATA ---
            cursor.execute("SELECT COUNT(*) FROM import_configs")
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO import_configs (source_path, target_path, action, path_template)
                    VALUES (%s, %s, %s, %s)
                ''', ("/volume2/photo", "/volume2/photo_organized", "copy", "{year}/{month}/{day}"))
            
            conn.commit()
            cursor.close()
            conn.close()
            print("Database initialized with simplified schema.")
            break
        except Exception as e:
            print(f"Database connection failed. Retrying... ({retries} left). Error: {e}")
            retries -= 1
            time.sleep(2)

def save_file_record(data: dict):
    """Saves a new file record and returns its configuration if found."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Buscar la configuración para este path
    cursor.execute("SELECT * FROM import_configs WHERE source_path = %s AND is_active = TRUE", (data['path'],))
    config = cursor.fetchone()
    
    # 2. Insertar el registro
    cursor.execute(
        """INSERT INTO imported_files (path, filename, size, timestamp, date_taken, status) 
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (data['path'], data['filename'], data['size'], data['timestamp'], data.get('date_taken'), 
         'pending' if config else 'failed')
    )
    file_id = cursor.fetchone()['id']
    
    if not config:
        cursor.execute("UPDATE imported_files SET error_msg = 'No matching configuration found' WHERE id = %s", (file_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return dict(config) if config else None

def save_heartbeat(data: dict):
    """Saves a heartbeat record to the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO heartbeats (nas_id, status) VALUES (%s, %s)",
        (data['nas_id'], data['status'])
    )
    conn.commit()
    cursor.close()
    conn.close()

def get_recent_files(limit: int = 50):
    """Retrieves recent file records."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM imported_files ORDER BY created_at DESC LIMIT %s", (limit,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [dict(row) for row in rows]
