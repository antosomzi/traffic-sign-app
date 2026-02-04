"""SQLite database connection management"""

import sqlite3
import os
from contextlib import contextmanager


def get_db_path():
    """Get database path based on environment (EC2 vs local)"""
    if os.path.exists("/home/ec2-user"):
        return "/home/ec2-user/app.db"
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, "app.db")


@contextmanager
def get_db():
    """Context manager for database connections"""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database tables"""
    db_path = get_db_path()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create organizations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            organization_id INTEGER NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_org_owner INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )
    """)
    
    # Create recordings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recordings (
            id TEXT PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )
    """)
    
    # Create auth_tokens table (for mobile authentication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Create indexes for auth_tokens
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_tokens_token 
        ON auth_tokens(token)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id 
        ON auth_tokens(user_id)
    """)
    
    # Create signs table (for storing detected traffic signs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id TEXT NOT NULL,
            mutcd_code TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
        )
    """)
    
    # Create indexes for signs table
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signs_recording_id 
        ON signs(recording_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_signs_mutcd_code 
        ON signs(mutcd_code)
    """)
    
    conn.commit()
    conn.close()
    
    print(f"✅ Database initialized at: {db_path}")
