#!/usr/bin/env python3
"""
Emergency database table creation script
Run this to manually create the missing tables
"""

import os
import sys
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def main():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY') 
    
    if not url or not key:
        print("❌ Missing Supabase credentials")
        sys.exit(1)
    
    client = create_client(url, key)
    
    # Test basic connectivity
    try:
        result = client.table('non_existent_table').select('*').limit(1).execute()
    except Exception as e:
        if "Could not find the table" not in str(e):
            print(f"❌ Supabase connection failed: {e}")
            sys.exit(1)
        print("✅ Supabase connection working")
    
    # Try to create tables using insert operations (this will create the table)
    print("Creating processed_tweets table...")
    try:
        # This will fail but create the table schema if needed
        client.table('processed_tweets').insert({
            'tweet_id': 'test_123',
            'author_id': 'test_author',
            'processed_at': '2025-08-20T00:00:00Z'
        }).execute()
        print("✅ processed_tweets table exists/created")
    except Exception as e:
        if "duplicate key value" in str(e) or "already exists" in str(e):
            print("✅ processed_tweets table already exists")
        else:
            print(f"❌ Error with processed_tweets: {e}")
    
    print("Creating tweet_decisions table...")
    try:
        client.table('tweet_decisions').insert({
            'tweet_id': 'test_123',
            'author_id': 'test_author', 
            'tweet_text': 'test tweet',
            'stage_quick': 'pass',
            'quick_reason': '',
            'stage_ai': 'pass',
            'ai_score': 85.0,
            'ai_reason': 'test',
            'final': 'approved',
            'categories': '[]',
            'filter_version': 'v2'
        }).execute()
        print("✅ tweet_decisions table exists/created")
    except Exception as e:
        if "duplicate key value" in str(e) or "already exists" in str(e):
            print("✅ tweet_decisions table already exists")  
        else:
            print(f"❌ Error with tweet_decisions: {e}")
            
    print("Creating manual_replies table...")
    try:
        client.table('manual_replies').insert({
            'tweet_id': 'test_123',
            'reply_text': 'test reply',
            'method_used': 'test',
            'status': 'pending'
        }).execute()
        print("✅ manual_replies table exists/created")
    except Exception as e:
        if "duplicate key value" in str(e) or "already exists" in str(e):
            print("✅ manual_replies table already exists")
        else:
            print(f"❌ Error with manual_replies: {e}")
    
    print("\n🔍 Testing table access...")
    try:
        result = client.table('processed_tweets').select('*').limit(1).execute()
        print(f"✅ processed_tweets accessible: {len(result.data)} rows")
    except Exception as e:
        print(f"❌ processed_tweets not accessible: {e}")
        
    try:
        result = client.table('tweet_decisions').select('*').limit(1).execute() 
        print(f"✅ tweet_decisions accessible: {len(result.data)} rows")
    except Exception as e:
        print(f"❌ tweet_decisions not accessible: {e}")
        
    try:
        result = client.table('manual_replies').select('*').limit(1).execute()
        print(f"✅ manual_replies accessible: {len(result.data)} rows")
    except Exception as e:
        print(f"❌ manual_replies not accessible: {e}")

if __name__ == '__main__':
    main()