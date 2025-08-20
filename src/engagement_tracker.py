import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from .twitter_client import twitter_client
from .database import db, EngagementMetrics
from .config import settings

class EngagementTracker:
    def __init__(self):
        self.last_update_time = datetime.now(timezone.utc)
    
    async def update_engagement_metrics(self) -> Dict[str, int]:
        """Update engagement metrics for all tweets needing updates"""
        try:
            # Get tweets that need engagement updates
            tweet_ids = db.get_tweets_needing_engagement_update()
            
            if not tweet_ids:
                print("No tweets found for engagement updates")
                return {'updated': 0, 'errors': 0}
            
            print(f"Updating engagement metrics for {len(tweet_ids)} tweets")
            
            updated_count = 0
            error_count = 0
            
            # Process tweets in batches to avoid rate limits
            batch_size = 10
            for i in range(0, len(tweet_ids), batch_size):
                batch_ids = tweet_ids[i:i + batch_size]
                
                # Get metrics for this batch
                metrics_data = twitter_client.get_multiple_tweet_metrics(batch_ids)
                
                # Save metrics to database
                for tweet_id, metrics in metrics_data.items():
                    success = await self._save_engagement_metrics(tweet_id, metrics)
                    if success:
                        updated_count += 1
                    else:
                        error_count += 1
                
                # Add delay between batches to respect rate limits
                if i + batch_size < len(tweet_ids):
                    await asyncio.sleep(2)
            
            self.last_update_time = datetime.now(timezone.utc)
            
            result = {'updated': updated_count, 'errors': error_count}
            print(f"Engagement update complete: {result}")
            return result
            
        except Exception as e:
            print(f"Error updating engagement metrics: {e}")
            return {'updated': 0, 'errors': 1}
    
    async def _save_engagement_metrics(self, tweet_id: str, metrics: Dict[str, int]) -> bool:
        """Save engagement metrics for a specific tweet"""
        try:
            engagement_metrics = EngagementMetrics(
                tweet_id=tweet_id,
                likes=metrics.get('likes', 0),
                retweets=metrics.get('retweets', 0),
                replies=metrics.get('replies', 0),
                timestamp=datetime.now(timezone.utc)
            )
            
            return db.save_engagement_metrics(engagement_metrics)
        except Exception as e:
            print(f"Error saving engagement metrics for tweet {tweet_id}: {e}")
            return False
    
    async def get_performance_analysis(self) -> Dict[str, Any]:
        """Analyze performance of tweets based on engagement metrics"""
        try:
            top_performing = db.get_top_performing_tweets(limit=10)
            recent_tweets = db.get_recent_tweets(limit=20)
            
            analysis = {
                'top_performing_tweets': top_performing,
                'recent_tweets': recent_tweets,
                'total_tweets': len(recent_tweets),
                'avg_engagement': self._calculate_average_engagement(recent_tweets),
                'performance_trends': self._analyze_performance_trends(recent_tweets)
            }
            
            return analysis
        except Exception as e:
            print(f"Error generating performance analysis: {e}")
            return {}
    
    def _calculate_average_engagement(self, tweets: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate average engagement metrics"""
        if not tweets:
            return {'likes': 0.0, 'retweets': 0.0, 'replies': 0.0}
        
        total_likes = sum(tweet.get('avg_likes', 0) for tweet in tweets)
        total_retweets = sum(tweet.get('avg_retweets', 0) for tweet in tweets)
        total_replies = sum(tweet.get('avg_replies', 0) for tweet in tweets)
        
        count = len(tweets)
        
        return {
            'likes': total_likes / count,
            'retweets': total_retweets / count,
            'replies': total_replies / count
        }
    
    def _analyze_performance_trends(self, tweets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze performance trends"""
        if len(tweets) < 5:
            return {'trend': 'insufficient_data'}
        
        # Sort tweets by time
        sorted_tweets = sorted(tweets, key=lambda x: x.get('time_posted', ''))
        
        # Split into early and recent halves
        mid_point = len(sorted_tweets) // 2
        early_tweets = sorted_tweets[:mid_point]
        recent_tweets = sorted_tweets[mid_point:]
        
        early_avg = self._calculate_average_engagement(early_tweets)
        recent_avg = self._calculate_average_engagement(recent_tweets)
        
        # Calculate trend
        total_early = early_avg['likes'] + early_avg['retweets'] + early_avg['replies']
        total_recent = recent_avg['likes'] + recent_avg['retweets'] + recent_avg['replies']
        
        if total_recent > total_early * 1.1:
            trend = 'improving'
        elif total_recent < total_early * 0.9:
            trend = 'declining'
        else:
            trend = 'stable'
        
        return {
            'trend': trend,
            'early_avg_engagement': total_early,
            'recent_avg_engagement': total_recent,
            'improvement_ratio': total_recent / total_early if total_early > 0 else 0
        }
    
    async def should_run_engagement_update(self) -> bool:
        """Check if it's time to run engagement updates"""
        time_since_last_update = datetime.now(timezone.utc) - self.last_update_time
        hours_since_update = time_since_last_update.total_seconds() / 3600
        
        return hours_since_update >= settings.engagement_check_hours
    
    async def run_scheduled_update(self) -> Dict[str, int]:
        """Run engagement update if scheduled"""
        if await self.should_run_engagement_update():
            print("Running scheduled engagement metrics update...")
            return await self.update_engagement_metrics()
        else:
            print("Engagement update not due yet")
            return {'updated': 0, 'errors': 0}
    
    def get_engagement_summary(self, tweet_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """Get current engagement metrics for specific tweets"""
        try:
            return twitter_client.get_multiple_tweet_metrics(tweet_ids)
        except Exception as e:
            print(f"Error getting engagement summary: {e}")
            return {}

engagement_tracker = EngagementTracker()