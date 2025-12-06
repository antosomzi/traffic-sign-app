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
    
    conn.commit()
    conn.close()
    
    print(f"✅ Database initialized at: {db_path}")
