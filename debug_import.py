#!/usr/bin/env python3
"""
Debug script for Twitter list import issues
Run this to get detailed logging when testing list imports
"""

import asyncio
import json
import logging
import sys
from src.apify_client import apify_client
from src.database import db, TwitterList, ListTweet

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_import.log')
    ]
)

async def debug_import(list_url: str = "https://x.com/i/lists/1957324919269929248"):
    """Debug a Twitter list import with full logging"""
    
    print(f"🔍 Debug Import for: {list_url}")
    print("=" * 60)
    
    try:
        print("Step 1: Validating URL...")
        is_valid = apify_client._validate_list_url(list_url)
        print(f"URL valid: {is_valid}")
        
        if not is_valid:
            print("❌ URL validation failed!")
            return
        
        print("\nStep 2: Testing Apify connection...")
        connected = await apify_client.test_connection()
        print(f"Apify connected: {connected}")
        
        if not connected:
            print("❌ Apify connection failed!")
            return
        
        print("\nStep 3: Attempting to scrape tweets...")
        tweets = await apify_client.scrape_twitter_list(list_url, max_items=5)
        
        print(f"\n✅ Successfully scraped {len(tweets)} tweets!")
        
        for i, tweet in enumerate(tweets[:3]):  # Show first 3
            print(f"\nTweet {i+1}:")
            print(f"  ID: {tweet.tweet_id}")
            print(f"  Author: @{tweet.author_username}")
            print(f"  Text: {tweet.text[:100]}...")
            print(f"  Date: {tweet.created_at}")
            print(f"  Metrics: ❤️{tweet.like_count} 🔄{tweet.retweet_count} 💬{tweet.reply_count}")
        
        print(f"\n🎉 Import would work! Found {len(tweets)} tweets to process.")
        
        # Test database operations (without actually saving)
        print("\nStep 4: Testing database operations...")
        list_obj = TwitterList(name="Debug Test List", list_url=list_url)
        print(f"Created TwitterList object: {list_obj.name}")
        
        if tweets:
            tweet = tweets[0]
            list_tweet = ListTweet(
                list_id=1,  # Mock ID
                tweet_id=tweet.tweet_id,
                url=tweet.url,
                text=tweet.text,
                author_username=tweet.author_username,
                author_display_name=tweet.author_display_name,
                created_at=apify_client._parse_tweet_date(tweet.created_at),
                retweet_count=tweet.retweet_count,
                reply_count=tweet.reply_count,
                like_count=tweet.like_count,
                quote_count=tweet.quote_count,
                bookmark_count=tweet.bookmark_count,
                is_retweet=tweet.is_retweet,
                is_quote=tweet.is_quote
            )
            print(f"Created ListTweet object for: {list_tweet.tweet_id}")
            print(f"Parsed date: {list_tweet.created_at}")
            
        print("\n✅ All operations successful! The import should work now.")
        
    except Exception as e:
        print(f"\n❌ Error during debug import: {str(e)}")
        print(f"Exception type: {type(e)}")
        import traceback
        traceback.print_exc()
        
        # Save detailed error to file
        with open('import_error.log', 'w') as f:
            f.write(f"Error: {str(e)}\n")
            f.write(f"Type: {type(e)}\n")
            f.write("Traceback:\n")
            traceback.print_exc(file=f)

if __name__ == "__main__":
    import sys
    
    # Allow custom URL as command line argument
    url = sys.argv[1] if len(sys.argv) > 1 else "https://x.com/i/lists/1957324919269929248"
    
    print("Running debug import...")
    print(f"Logs will be saved to: debug_import.log")
    print(f"If errors occur, check: import_error.log")
    print()
    
    asyncio.run(debug_import(url))