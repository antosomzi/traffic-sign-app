#!/usr/bin/env python3
"""
Initialize database with tables, default organization, admin user, and migrate existing recordings
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import init_db, get_db_path
from models.organization import Organization
from models.user import User
from models.recording import Recording
from config import Config


def migrate_existing_recordings(org_id):
    """Associate existing recordings on disk to default organization"""
    recordings_path = Config.EXTRACT_FOLDER
    
    if not os.path.isdir(recordings_path):
        print(f"⚠️  No recordings folder found at {recordings_path}")
        return 0
    
    count = 0
    for recording_id in os.listdir(recordings_path):
        recording_folder = os.path.join(recordings_path, recording_id)
        
        # Skip non-directories
        if not os.path.isdir(recording_folder):
            continue
        
        # Skip if already exists in DB
        if Recording.exists(recording_id):
            print(f"  ⏭️  {recording_id} already in database, skipping")
            continue
        
        # Create recording entry
        try:
            Recording.create(recording_id, org_id)
            print(f"  ✅ Migrated: {recording_id}")
            count += 1
        except Exception as e:
            print(f"  ❌ Failed to migrate {recording_id}: {e}")
    
    return count


def main():
    """Main initialization function"""
    print("=" * 60)
    print("🚀 Initializing Traffic Sign App Database")
    print("=" * 60)
    
    # Step 1: Create tables
    print("\n📊 Creating database tables...")
    init_db()
    
    # Step 2: Create default organization
    print("\n🏢 Creating default organization...")
    org = Organization.get_by_name("Default Organization")
    if not org:
        org = Organization.create("Default Organization")
        print(f"  ✅ Created: {org.name} (ID: {org.id})")
    else:
        print(f"  ⏭️  Already exists: {org.name} (ID: {org.id})")
    
    # Step 3: Create admin user
    print("\n👤 Creating admin user...")
    admin_email = "arevel3@gatech.edu"
    admin_password = "Admin123!"  # Temporary password
    
    user = User.get_by_email(admin_email)
    if not user:
        user = User.create(
            email=admin_email,
            password=admin_password,
            name="Antoine Revel",
            organization_id=org.id,
            is_admin=True
        )
        print(f"  ✅ Created admin user: {user.name}")
        print(f"     📧 Email: {admin_email}")
        print(f"     🔑 Password: {admin_password}")
        print(f"     ⚠️  PLEASE CHANGE THIS PASSWORD AFTER FIRST LOGIN!")
    else:
        print(f"  ⏭️  Admin user already exists: {user.email}")
    
    # Step 4: Migrate existing recordings
    print("\n📁 Migrating existing recordings...")
    migrated_count = migrate_existing_recordings(org.id)
    print(f"  ✅ Migrated {migrated_count} recordings to '{org.name}'")
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Database initialization complete!")
    print("=" * 60)
    print(f"📍 Database location: {get_db_path()}")
    print(f"🏢 Default organization: {org.name} (ID: {org.id})")
    print(f"👤 Admin: {admin_email}")
    print(f"🔑 Temporary password: {admin_password}")
    print("\n🌐 You can now start the app and login at http://localhost:5000/login")
    print("=" * 60)


if __name__ == "__main__":
    main()
