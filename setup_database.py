#!/usr/bin/env python3
"""
Setup database tables for Twitter Auto Bot
"""

import os
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.database import db

def setup_discovery_lists_table():
    """Create the discovery_lists table if it doesn't exist"""
    
    if not db.client:
        print("❌ Error: Supabase client not configured")
        return False
    
    # Read the SQL file
    sql_file = Path(__file__).parent / "create_discovery_lists_table.sql"
    
    try:
        with open(sql_file, 'r') as f:
            sql_content = f.read()
        
        # Split the SQL into individual statements
        statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip() and not stmt.strip().startswith('--')]
        
        print("🔧 Setting up discovery_lists table...")
        
        for i, statement in enumerate(statements):
            if statement:
                try:
                    print(f"   Executing statement {i+1}/{len(statements)}...")
                    # Use the Supabase SQL function to execute raw SQL
                    result = db.client.postgrest.session.post(
                        f"{db.client.supabase_url}/rest/v1/rpc/exec_sql",
                        json={"query": statement},
                        headers={"Authorization": f"Bearer {db.client.supabase_key}"}
                    )
                    
                    if result.status_code not in [200, 201]:
                        print(f"   ⚠️  SQL statement {i+1} result: {result.status_code} - {result.text}")
                    else:
                        print(f"   ✅ Statement {i+1} executed successfully")
                        
                except Exception as e:
                    print(f"   ⚠️  Error executing statement {i+1}: {e}")
                    continue
        
        # Test if the table exists by trying to query it
        try:
            result = db.client.table("discovery_lists").select("count", count="exact").limit(0).execute()
            print(f"✅ discovery_lists table is ready! (contains {result.count} rows)")
            return True
            
        except Exception as e:
            print(f"❌ Table verification failed: {e}")
            print("\n🔧 Alternative: Create table manually in Supabase dashboard using:")
            print(f"   SQL file: {sql_file}")
            return False
            
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        return False

def main():
    print("🚀 Twitter Auto Bot - Database Setup")
    print("=" * 40)
    
    # Initialize database connection
    try:
        print("📡 Connecting to database...")
        # The db connection should already be initialized
        if db.client:
            print("✅ Database connection established")
        else:
            print("❌ Failed to establish database connection")
            print("   Check your SUPABASE_URL and SUPABASE_KEY environment variables")
            return False
            
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False
    
    # Setup tables
    success = setup_discovery_lists_table()
    
    if success:
        print("\n🎉 Database setup completed successfully!")
        print("\n📋 Next steps:")
        print("   1. The discovery_lists table is ready")
        print("   2. Two default lists have been added")
        print("   3. You can now use the Lists Management UI")
    else:
        print("\n⚠️  Database setup encountered issues")
        print("   Please check the errors above and try again")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)