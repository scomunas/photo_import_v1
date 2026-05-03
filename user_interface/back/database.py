import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "photo_db"),
        user=os.getenv("DB_USER", "photo_user"),
        password=os.getenv("DB_PASSWORD", "photo_pass")
    )

def init_db():
    conn = get_connection()
    with conn.cursor() as cur:
        # Tabla de configuraciones
        cur.execute("""
            CREATE TABLE IF NOT EXISTS import_configs (
                id SERIAL PRIMARY KEY,
                source_path TEXT NOT NULL,
                target_path TEXT NOT NULL,
                path_template TEXT NOT NULL,
                name_template TEXT NOT NULL DEFAULT '{filename}',
                action TEXT NOT NULL DEFAULT 'move'
            )
        """)
        
        # Tabla de archivos procesados
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                id SERIAL PRIMARY KEY,
                original_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                target_path TEXT NOT NULL, 
                target_filename TEXT NOT NULL,
                date_taken TIMESTAMP,
                action TEXT DEFAULT 'move',
                status TEXT DEFAULT 'pending',
                processed_at TIMESTAMP,
                error_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migración para añadir la columna si la tabla ya existía
        cur.execute("""
            ALTER TABLE processed_files 
            ADD COLUMN IF NOT EXISTS action TEXT DEFAULT 'move'
        """)
    conn.commit()
    conn.close()

def get_config_for_path(path):
    """Busca una configuración que coincida con el path de origen."""
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM import_configs 
                WHERE %s LIKE source_path || '%%'
                ORDER BY length(source_path) DESC 
                LIMIT 1
            """, (path,))
            return cur.fetchone()
    except Exception as e:
        print(f"[ERROR] Error buscando config: {e}")
        return None
    finally:
        if 'conn' in locals(): conn.close()

def save_processed_file(data):
    """Guarda el registro del archivo una vez validado y calculado el destino."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO processed_files 
                (original_path, original_filename, target_path, target_filename, date_taken, action, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            """, (data['original_path'], data['original_filename'], 
                  data['target_path'], data['target_filename'], data['date_taken'], data.get('action', 'move')))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Error guardando archivo procesado: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def get_all_files(status=None):
    """Obtiene el listado de archivos filtrado por estado."""
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT * FROM processed_files"
            params = []
            if status:
                query += " WHERE status = %s"
                params = [status]
            query += " ORDER BY created_at DESC"
            cur.execute(query, params)
            return cur.fetchall()
    except Exception as e:
        print(f"[ERROR] Error obteniendo archivos: {e}")
        return []
    finally:
        if 'conn' in locals(): conn.close()

def get_file_by_id(file_id):
    """Obtiene un archivo procesado por su ID."""
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM processed_files WHERE id = %s", (file_id,))
            return cur.fetchone()
    except Exception as e:
        print(f"[ERROR] Error obteniendo archivo {file_id}: {e}")
        return None
    finally:
        if 'conn' in locals(): conn.close()

def check_db_health():
    """Verifica si la conexión con la base de datos está operativa."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"[ERROR] Health check fallido: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def get_all_configs():
    """Obtiene todas las configuraciones de importación."""
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM import_configs ORDER BY id")
            return cur.fetchall()
    except Exception as e:
        print(f"[ERROR] Error obteniendo configs: {e}")
        return []
    finally:
        if 'conn' in locals(): conn.close()

def add_config(data):
    """Añade una nueva configuración de importación."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO import_configs (source_path, target_path, path_template, name_template, action)
                VALUES (%s, %s, %s, %s, %s)
            """, (data['source_path'], data['target_path'], data['path_template'], 
                  data['name_template'], data['action']))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Error añadiendo config: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def update_config(config_id, data):
    """Actualiza una configuración existente."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE import_configs 
                SET source_path = %s, target_path = %s, path_template = %s, name_template = %s, action = %s
                WHERE id = %s
            """, (data['source_path'], data['target_path'], data['path_template'], 
                  data['name_template'], data['action'], config_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Error actualizando config {config_id}: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def set_file_status(file_id: int, status: str, error_details: str = None):
    """Actualiza únicamente el estado y el error de un archivo procesado."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE processed_files
                SET status = %s,
                    error_details = %s,
                    processed_at = CASE WHEN %s IN ('completed', 'error') THEN NOW() ELSE processed_at END
                WHERE id = %s
            """, (status, error_details, status, file_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Error actualizando estado del archivo {file_id}: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def update_processed_file(file_id, data):
    """Actualiza un archivo procesado manualmente."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE processed_files 
                SET target_path = %s, target_filename = %s, status = %s, error_details = %s
                WHERE id = %s
            """, (data.get('target_path'), data.get('target_filename'), 
                  data.get('status'), data.get('error_details'), file_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Error actualizando archivo {file_id}: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def get_stats_kpis(start_date=None, end_date=None):
    """Calcula los totales de ficheros por estado con fechas inclusivas."""
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = "SELECT status, COUNT(*) as count FROM processed_files"
            params = []
            if start_date and end_date:
                # Comparamos solo la parte de la FECHA para que sea inclusive
                query += " WHERE created_at::date BETWEEN %s AND %s"
                params = [start_date, end_date]
            query += " GROUP BY status"
            cur.execute(query, params)
            return cur.fetchall()
    except Exception as e:
        print(f"[ERROR] Error en KPIs: {e}")
        return []
    finally:
        if 'conn' in locals(): conn.close()

def get_daily_stats(start_date=None, end_date=None):
    """Agrupa ficheros por día y estado para la gráfica con fechas inclusivas."""
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT created_at::date as day, status, COUNT(*) as count 
                FROM processed_files
            """
            params = []
            if start_date and end_date:
                # Comparamos solo la parte de la FECHA para que sea inclusive
                query += " WHERE created_at::date BETWEEN %s AND %s"
                params = [start_date, end_date]
            query += " GROUP BY day, status ORDER BY day"
            cur.execute(query, params)
            return cur.fetchall()
    except Exception as e:
        print(f"[ERROR] Error en daily stats: {e}")
        return []
    finally:
        if 'conn' in locals(): conn.close()
