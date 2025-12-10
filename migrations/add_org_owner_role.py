#!/usr/bin/env python3
"""
Add is_org_owner column to users table for organization owner role
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import get_db_path
import sqlite3


def main():
    """Add is_org_owner column to users table"""
    db_path = get_db_path()
    
    print("=" * 60)
    print("🔧 Adding Organization Owner Role")
    print("=" * 60)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'is_org_owner' in columns:
            print("  ⏭️  Column 'is_org_owner' already exists, skipping")
        else:
            # Add is_org_owner column (default 0 = False)
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN is_org_owner INTEGER DEFAULT 0
            """)
            conn.commit()
            print("  ✅ Added column 'is_org_owner' to users table")
        
        print("\n" + "=" * 60)
        print("✅ Migration complete!")
        print("=" * 60)
        print(f"📍 Database: {db_path}")
        print("\n💡 Organization owners can now manage users in their organization")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
