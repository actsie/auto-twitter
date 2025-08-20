import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from .twitter_client import twitter_client
from .response_generator import response_generator
from .database import db, TweetRecord
from .tweet_poller import poller

class TweetProcessor:
    def __init__(self):
        self.processed_count = 0
        self.success_count = 0
        self.error_count = 0
    
    async def process_tweet(self, tweet: Dict[str, Any]) -> bool:
        """Process a single tweet: generate response and post it"""
        try:
            tweet_id = str(tweet['id'])
            tweet_text = tweet['text']
            author_username = tweet['author_username']
            
            print(f"\nProcessing tweet from @{author_username}: {tweet_text[:100]}...")
            
            # Check if we should respond to this tweet
            if not poller.should_respond_to_tweet(tweet):
                print("Skipping tweet - doesn't meet response criteria")
                return False
            
            # Determine response type
            response_type = poller.get_response_type(tweet)
            print(f"Response type: {response_type}")
            
            # Generate response
            response_text = response_generator.generate_response(tweet, response_type)
            
            if not response_text:
                print("Failed to generate response")
                self.error_count += 1
                return False
            
            # Check if response is appropriate
            if not response_generator.is_response_appropriate(response_text, tweet_text):
                print("Generated response is not appropriate")
                self.error_count += 1
                return False
            
            print(f"Generated {response_type}: {response_text}")
            
            # Post the response
            posted_tweet_id = await self._post_response(tweet_id, response_text, response_type)
            
            if not posted_tweet_id:
                print("Failed to post response")
                self.error_count += 1
                return False
            
            # Save to database
            success = await self._save_tweet_record(
                tweet_id=posted_tweet_id,
                original_tweet=tweet_text,
                response=response_text,
                response_type=response_type,
                author_username=author_username
            )
            
            if success:
                print(f"Successfully processed and saved tweet {posted_tweet_id}")
                self.success_count += 1
                return True
            else:
                print("Failed to save tweet record")
                self.error_count += 1
                return False
                
        except Exception as e:
            print(f"Error processing tweet: {e}")
            self.error_count += 1
            return False
        finally:
            self.processed_count += 1
    
    async def _post_response(self, original_tweet_id: str, response_text: str, response_type: str) -> Optional[str]:
        """Post a reply or quote tweet"""
        try:
            if response_type == "reply":
                return twitter_client.post_reply(original_tweet_id, response_text)
            elif response_type == "quote_rt":
                return twitter_client.post_quote_tweet(original_tweet_id, response_text)
            else:
                print(f"Unknown response type: {response_type}")
                return None
        except Exception as e:
            print(f"Error posting response: {e}")
            return None
    
    async def _save_tweet_record(self, tweet_id: str, original_tweet: str, 
                                response: str, response_type: str, author_username: str) -> bool:
        """Save tweet record to database"""
        try:
            tweet_record = TweetRecord(
                tweet_id=tweet_id,
                original_tweet=original_tweet,
                response=response,
                type=response_type,
                time_posted=datetime.now(timezone.utc),
                author_username=author_username
            )
            
            return db.save_tweet(tweet_record)
        except Exception as e:
            print(f"Error saving tweet record: {e}")
            return False
    
    async def process_multiple_tweets(self, tweets: list[Dict[str, Any]]) -> Dict[str, int]:
        """Process multiple tweets and return statistics"""
        self.processed_count = 0
        self.success_count = 0
        self.error_count = 0
        
        print(f"\nProcessing {len(tweets)} tweets...")
        
        for tweet in tweets:
            await self.process_tweet(tweet)
            # Add a small delay between processing tweets to avoid rate limits
            await asyncio.sleep(2)
        
        stats = {
            'processed': self.processed_count,
            'successful': self.success_count,
            'errors': self.error_count
        }
        
        print(f"\nProcessing complete: {stats}")
        return stats
    
    async def run_single_cycle(self) -> Dict[str, int]:
        """Run a single polling and processing cycle"""
        try:
            # Initialize poller if needed
            if not hasattr(poller, 'last_poll_time'):
                await poller.initialize()
            
            # Poll for new tweets
            new_tweets = await poller.poll_and_process()
            
            if not new_tweets:
                print("No new tweets to process")
                return {'processed': 0, 'successful': 0, 'errors': 0}
            
            # Process the tweets
            return await self.process_multiple_tweets(new_tweets)
            
        except Exception as e:
            print(f"Error in processing cycle: {e}")
            return {'processed': 0, 'successful': 0, 'errors': 1}
    
    def get_processing_stats(self) -> Dict[str, int]:
        """Get current processing statistics"""
        return {
            'processed': self.processed_count,
            'successful': self.success_count,
            'errors': self.error_count
        }

processor = TweetProcessor()