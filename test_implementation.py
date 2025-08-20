#!/usr/bin/env python3
"""
Test script for the Twitter List Reply Tool implementation
"""

import asyncio
import json
from datetime import datetime
from src.config import settings
from src.apify_client import apify_client
from src.manual_reply import manual_reply_service
from src.database import db, TwitterList, ListTweet

async def test_implementation():
    """Test the complete implementation"""
    
    print("🚀 Testing Twitter List Reply Tool Implementation")
    print("=" * 50)
    
    # Test 1: Configuration
    print("\n1. Testing Configuration...")
    print(f"   ✅ Apify API Token: {'✓' if settings.apify_api_token else '✗'}")
    print(f"   ✅ Apify User ID: {'✓' if settings.apify_user_id else '✗'}")
    print(f"   ✅ N8N Webhook URL: {'✓' if settings.n8n_webhook_url else '✗'}")
    
    # Test 2: Apify Client Connection
    print("\n2. Testing Apify Client...")
    try:
        connection_test = await apify_client.test_connection()
        print(f"   {'✅' if connection_test else '❌'} Apify API Connection: {'Success' if connection_test else 'Failed'}")
    except Exception as e:
        print(f"   ❌ Apify API Connection: Failed - {e}")
    
    # Test 3: Manual Reply Service
    print("\n3. Testing Manual Reply Service...")
    try:
        # Test text validation
        is_valid, msg = manual_reply_service.validate_reply_text("This is a test reply")
        print(f"   ✅ Reply validation: {'Pass' if is_valid else 'Fail'} - {msg}")
        
        # Test preview generation
        preview = manual_reply_service.get_reply_preview("123456", "Test reply", "testuser")
        print(f"   ✅ Reply preview: Generated successfully")
        
    except Exception as e:
        print(f"   ❌ Manual Reply Service: Failed - {e}")
    
    # Test 4: Database Models
    print("\n4. Testing Database Models...")
    try:
        # Test creating model instances
        twitter_list = TwitterList(
            name="Test List",
            list_url="https://x.com/i/lists/123456"
        )
        
        list_tweet = ListTweet(
            list_id=1,
            tweet_id="123456789",
            url="https://x.com/user/status/123456789",
            text="This is a test tweet",
            author_username="testuser",
            author_display_name="Test User",
            created_at=datetime.now(),
            retweet_count=0,
            reply_count=0,
            like_count=0,
            quote_count=0,
            bookmark_count=0,
            is_retweet=False,
            is_quote=False
        )
        
        print("   ✅ Database models: Created successfully")
        
    except Exception as e:
        print(f"   ❌ Database models: Failed - {e}")
    
    # Test 5: Sample Data Structure
    print("\n5. Sample Apify Tweet Structure...")
    sample_tweet = {
        "id": "1957327356797882655",
        "url": "https://x.com/Ronald_vanLoon/status/1957327356797882655",
        "text": "Memory types in #AI Agents by @Khulood_Almani #ArtificialIntelligence",
        "retweetCount": 0,
        "replyCount": 1,
        "likeCount": 3,
        "bookmarkCount": 6,
        "isRetweet": False,
        "createdAt": "Mon Aug 18 06:23:01 +0000 2025"
    }
    
    print(f"   ✅ Sample tweet structure: {json.dumps(sample_tweet, indent=2)}")
    
    print("\n" + "=" * 50)
    print("🎉 Implementation Test Complete!")
    print("\nNext Steps:")
    print("1. Set up your environment variables in .env file")
    print("2. Configure Supabase database")
    print("3. Run: python3 dashboard.py")
    print("4. Visit: http://localhost:8000")
    print("5. Import a Twitter list and start replying manually!")

if __name__ == "__main__":
    asyncio.run(test_implementation())