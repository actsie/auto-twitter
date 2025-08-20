import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from .twitter_client import twitter_client
from .database import db, TweetRecord
from .config import settings

class TweetPoller:
    def __init__(self):
        self.last_poll_time = datetime.now(timezone.utc)
        self.processed_tweet_ids = set()
    
    async def initialize(self):
        """Initialize the poller"""
        await db.init_database()
        # Load recently processed tweets to avoid duplicates
        recent_tweets = db.get_recent_tweets(limit=100)
        self.processed_tweet_ids = {tweet['tweet_id'] for tweet in recent_tweets}
        print(f"Initialized poller with {len(self.processed_tweet_ids)} recent tweets")
    
    def get_new_tweets(self) -> List[Dict[str, Any]]:
        """Poll for new tweets from target accounts"""
        if not settings.target_accounts or settings.target_accounts == ['']:
            print("No target accounts configured")
            return []
        
        print(f"Polling tweets from accounts: {settings.target_accounts}")
        
        # Get recent tweets from all target accounts
        all_tweets = twitter_client.get_multiple_users_recent_tweets(
            usernames=settings.target_accounts,
            max_results_per_user=10
        )
        
        # Filter for new tweets (posted after last poll and not already processed)
        new_tweets = []
        current_time = datetime.now(timezone.utc)
        
        for tweet in all_tweets:
            tweet_id = str(tweet['id'])
            tweet_time = tweet['created_at']
            
            # Ensure tweet_time is timezone aware
            if tweet_time.tzinfo is None:
                tweet_time = tweet_time.replace(tzinfo=timezone.utc)
            
            # Check if tweet is new and not already processed
            if (tweet_time > self.last_poll_time and 
                tweet_id not in self.processed_tweet_ids and
                not db.tweet_exists(tweet_id)):
                
                new_tweets.append(tweet)
                self.processed_tweet_ids.add(tweet_id)
        
        self.last_poll_time = current_time
        print(f"Found {len(new_tweets)} new tweets")
        return new_tweets
    
    def filter_tweets_for_response(self, tweets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter tweets that are suitable for responses"""
        filtered_tweets = []
        
        for tweet in tweets:
            text = tweet['text'].lower()
            
            # Skip tweets that are too short
            if len(tweet['text']) < 20:
                continue
            
            # Skip tweets with certain keywords that might not be suitable for responses
            skip_keywords = ['#ad', '#sponsored', '#promo', 'rt @', 'retweet', 'giveaway']
            if any(keyword in text for keyword in skip_keywords):
                continue
            
            # Skip tweets that are primarily links
            if text.count('http') > 1:
                continue
            
            # Skip tweets that are questions directed at specific users
            if text.startswith('@') and '?' in text:
                continue
            
            filtered_tweets.append(tweet)
        
        return filtered_tweets
    
    async def poll_and_process(self) -> List[Dict[str, Any]]:
        """Main polling method that returns new tweets ready for processing"""
        try:
            new_tweets = self.get_new_tweets()
            if not new_tweets:
                return []
            
            # Filter tweets suitable for responses
            suitable_tweets = self.filter_tweets_for_response(new_tweets)
            
            print(f"Found {len(suitable_tweets)} tweets suitable for responses")
            return suitable_tweets
            
        except Exception as e:
            print(f"Error during polling: {e}")
            return []
    
    def should_respond_to_tweet(self, tweet: Dict[str, Any]) -> bool:
        """Determine if we should respond to a specific tweet"""
        # Check engagement level - respond to tweets with some engagement
        metrics = tweet.get('public_metrics', {})
        like_count = metrics.get('like_count', 0)
        retweet_count = metrics.get('retweet_count', 0)
        
        # Respond to tweets with at least some engagement or very recent tweets
        min_engagement = like_count + retweet_count
        tweet_age_hours = (datetime.now(timezone.utc) - tweet['created_at']).total_seconds() / 3600
        
        # Respond if tweet has engagement or is very recent (within 1 hour)
        return min_engagement > 0 or tweet_age_hours < 1
    
    def get_response_type(self, tweet: Dict[str, Any]) -> str:
        """Determine whether to reply or quote tweet"""
        text = tweet['text'].lower()
        
        # Use quote tweet for:
        # - Tweets with questions
        # - Tweets with strong opinions
        # - Tweets with interesting facts
        quote_indicators = ['?', 'think', 'believe', 'amazing', 'incredible', 'fact:', 'tip:']
        
        if any(indicator in text for indicator in quote_indicators):
            return 'quote_rt'
        
        # Default to reply for most tweets
        return 'reply'

poller = TweetPoller()