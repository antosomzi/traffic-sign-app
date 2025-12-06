"""Add auth_tokens table for mobile API authentication"""

import os
import sys

# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import get_db


def migrate():
    """Add auth_tokens table to existing database"""
    print("🔄 Adding auth_tokens table...")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='auth_tokens'
        """)
        
        if cursor.fetchone():
            print("✅ Table 'auth_tokens' already exists")
            return
        
        # Create auth_tokens table
        cursor.execute("""
            CREATE TABLE auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Create index for faster token lookups
        cursor.execute("""
            CREATE INDEX idx_auth_tokens_token ON auth_tokens(token)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_auth_tokens_user_id ON auth_tokens(user_id)
        """)
        
        conn.commit()
        
        print("✅ Table 'auth_tokens' created successfully")
        print("✅ Indexes created for optimal performance")


if __name__ == "__main__":
    print("=" * 60)
    print("Mobile API Authentication Migration")
    print("=" * 60)
    
    try:
        migrate()
        print("\n✅ Migration completed successfully!")
        print("\nYou can now use the mobile API endpoints:")
        print("  - POST /api/login")
        print("  - POST /api/logout")
        print("  - POST /api/upload")
        print("  - GET /api/status/<job_id>")
        print("  - GET /api/recordings")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
