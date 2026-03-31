"""Migration: Add note column to recordings table"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import get_db

def upgrade():
    """Add note column to recordings table."""
    print("Migrating: Adding 'note' column to recordings table...")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(recordings)")
        columns = [row['name'] for row in cursor.fetchall()]
        
        if 'note' in columns:
            print("Column 'note' already exists in table 'recordings'. Nothing to do.")
            return True
            
        try:
            # Add note column (TEXT, nullable)
            cursor.execute("ALTER TABLE recordings ADD COLUMN note TEXT")
            print("Successfully added 'note' column.")
            return True
        except Exception as e:
            print(f"Error adding column: {e}")
            return False

if __name__ == "__main__":
    if upgrade():
        print("Migration complete!")
    else:
        print("Migration failed!")