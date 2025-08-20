import asyncio
import signal
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from .tweet_processor import processor
from .engagement_tracker import engagement_tracker
from .config import settings

class TwitterBotScheduler:
    def __init__(self):
        self.running = False
        self.tweet_poll_interval = settings.poll_interval_minutes * 60  # Convert to seconds
        self.engagement_check_interval = settings.engagement_check_hours * 3600  # Convert to seconds
        self.stats = {
            'cycles_completed': 0,
            'total_tweets_processed': 0,
            'total_successful_posts': 0,
            'total_errors': 0,
            'last_poll_time': None,
            'last_engagement_update': None
        }
    
    async def initialize(self):
        """Initialize the scheduler and all components"""
        try:
            print("Initializing Twitter Bot Scheduler...")
            
            # Test Twitter connection
            if not twitter_client.test_connection():
                raise Exception("Failed to connect to Twitter API")
            
            # Initialize database
            await db.init_database()
            print("Database initialized")
            
            # Initialize poller
            await poller.initialize()
            print("Tweet poller initialized")
            
            print("Scheduler initialization complete")
            return True
            
        except Exception as e:
            print(f"Failed to initialize scheduler: {e}")
            return False
    
    async def run_tweet_polling_cycle(self):
        """Run a single tweet polling and processing cycle"""
        try:
            print(f"\n{'='*50}")
            print(f"Running tweet polling cycle at {datetime.now(timezone.utc)}")
            print(f"{'='*50}")
            
            # Process tweets
            cycle_stats = await processor.run_single_cycle()
            
            # Update overall stats
            self.stats['cycles_completed'] += 1
            self.stats['total_tweets_processed'] += cycle_stats['processed']
            self.stats['total_successful_posts'] += cycle_stats['successful']
            self.stats['total_errors'] += cycle_stats['errors']
            self.stats['last_poll_time'] = datetime.now(timezone.utc)
            
            print(f"Cycle complete. Stats: {cycle_stats}")
            
        except Exception as e:
            print(f"Error in tweet polling cycle: {e}")
            self.stats['total_errors'] += 1
    
    async def run_engagement_update_cycle(self):
        """Run engagement metrics update cycle"""
        try:
            print(f"\n{'='*30}")
            print(f"Checking for engagement updates at {datetime.now(timezone.utc)}")
            print(f"{'='*30}")
            
            # Update engagement metrics
            update_stats = await engagement_tracker.run_scheduled_update()
            
            if update_stats['updated'] > 0:
                self.stats['last_engagement_update'] = datetime.now(timezone.utc)
                print(f"Updated engagement metrics for {update_stats['updated']} tweets")
            
        except Exception as e:
            print(f"Error in engagement update cycle: {e}")
    
    async def run_continuous(self):
        """Run the scheduler continuously"""
        self.running = True
        last_tweet_poll = datetime.now(timezone.utc)
        last_engagement_check = datetime.now(timezone.utc)
        
        print(f"\n🚀 Starting Twitter Bot Scheduler")
        print(f"Tweet polling interval: {self.tweet_poll_interval} seconds ({settings.poll_interval_minutes} minutes)")
        print(f"Engagement check interval: {self.engagement_check_interval} seconds ({settings.engagement_check_hours} hours)")
        print(f"Target accounts: {settings.target_accounts}")
        print("Press Ctrl+C to stop\n")
        
        while self.running:
            try:
                current_time = datetime.now(timezone.utc)
                
                # Check if it's time to poll tweets
                if (current_time - last_tweet_poll).total_seconds() >= self.tweet_poll_interval:
                    await self.run_tweet_polling_cycle()
                    last_tweet_poll = current_time
                
                # Check if it's time to update engagement metrics
                if (current_time - last_engagement_check).total_seconds() >= self.engagement_check_interval:
                    await self.run_engagement_update_cycle()
                    last_engagement_check = current_time
                
                # Sleep for a short interval before checking again
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except KeyboardInterrupt:
                print("\nReceived interrupt signal. Shutting down gracefully...")
                break
            except Exception as e:
                print(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
        
        self.running = False
        print("Scheduler stopped")
    
    async def run_once(self):
        """Run a single cycle of both tweet processing and engagement updates"""
        print("Running single cycle...")
        
        # Run tweet processing
        await self.run_tweet_polling_cycle()
        
        # Run engagement update
        await self.run_engagement_update_cycle()
        
        print("Single cycle complete")
    
    def stop(self):
        """Stop the scheduler"""
        print("Stopping scheduler...")
        self.running = False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current scheduler statistics"""
        return {
            **self.stats,
            'is_running': self.running,
            'uptime_seconds': (datetime.now(timezone.utc) - self.stats.get('start_time', datetime.now(timezone.utc))).total_seconds() if self.stats.get('start_time') else 0
        }
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            print(f"\nReceived signal {signum}")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

# Import after class definition to avoid circular imports
from .twitter_client import twitter_client
from .database import db
from .tweet_poller import poller

scheduler = TwitterBotScheduler()