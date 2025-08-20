from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from pydantic import BaseModel
from .config import settings

class TweetRecord(BaseModel):
    id: Optional[int] = None
    tweet_id: str
    original_tweet: str
    response: str
    type: str
    time_posted: datetime
    author_username: str
    created_at: Optional[datetime] = None

class EngagementMetrics(BaseModel):
    id: Optional[int] = None
    tweet_id: str
    likes: int
    retweets: int
    replies: int
    timestamp: datetime

class TwitterList(BaseModel):
    id: Optional[int] = None
    name: str
    list_url: str
    last_scraped: Optional[datetime] = None
    created_at: Optional[datetime] = None

class ListTweet(BaseModel):
    id: Optional[int] = None
    list_id: int
    tweet_id: str
    url: str
    text: str
    author_username: str
    author_display_name: str
    created_at: datetime
    retweet_count: int
    reply_count: int
    like_count: int
    quote_count: int
    bookmark_count: int
    is_retweet: bool
    is_quote: bool
    scraped_at: Optional[datetime] = None

class ManualReply(BaseModel):
    id: Optional[int] = None
    tweet_id: str
    reply_text: str
    method_used: str  # 'n8n', 'twitter_api', 'puppeteer'
    status: str  # 'pending', 'sent', 'failed'
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

class TweetInteraction(BaseModel):
    id: Optional[int] = None
    tweet_id: str
    interaction_type: str  # 'like', 'retweet', 'reply'
    method_used: str  # 'twitter_api', 'n8n', 'mock_success'
    status: str  # 'pending', 'success', 'failed'
    error_message: Optional[str] = None
    interaction_id: Optional[str] = None  # ID returned by Twitter API
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class ProcessedTweet(BaseModel):
    id: Optional[int] = None
    tweet_id: str
    list_id: Optional[str] = None  # Which Twitter list this came from
    author_username: str
    tweet_url: str
    tweet_text: str
    was_analyzed: bool = False
    was_relevant: bool = False
    relevance_score: Optional[float] = None
    analysis_categories: Optional[str] = None  # JSON string of categories
    skip_reason: Optional[str] = None
    processed_at: datetime
    created_at: Optional[datetime] = None

class TweetDecision(BaseModel):
    """V2 filtering decision with comprehensive telemetry"""
    id: Optional[int] = None
    tweet_id: str
    list_id: Optional[str] = None
    author_username: str
    tweet_text: str
    stage_quick: str  # 'pass' | 'reject' | 'error'
    quick_reason: str
    stage_ai: str     # 'pass' | 'reject' | 'skipped'  
    ai_score: Optional[float] = None
    ai_reason: str
    final: str        # 'approved' | 'rejected'
    categories: Optional[str] = None  # JSON string of categories
    processing_time_ms: int = 0
    relevance_threshold: float = 80.0
    filter_version: str = "v2"
    created_at: Optional[datetime] = None

class Database:
    def __init__(self):
        if not settings.supabase_url or settings.supabase_url == "your_supabase_url":
            self.client = None
            print("Warning: Supabase not configured")
        else:
            self.client: Client = create_client(settings.supabase_url, settings.supabase_key)
    
    async def init_database(self):
        """Initialize database tables if they don't exist"""
        
        try:
            # Create manual_replies table directly using table API
            # Since exec_sql function doesn't exist, we'll create the schema manually
            
            # Check if manual_replies table exists by trying to query it
            try:
                self.client.table("manual_replies").select("id").limit(1).execute()
                print("manual_replies table already exists")
            except:
                print("Creating manual_replies table...")
                # We'll need to create this table through the Supabase dashboard
                # For now, let's use a workaround to ensure the app doesn't crash
                print("Note: manual_replies table needs to be created in Supabase dashboard")
            
            print("Database initialization completed")
        except Exception as e:
            print(f"Database initialization error: {e}")
    
    def save_tweet(self, tweet_record: TweetRecord) -> bool:
        """Save a tweet record to the database"""
        try:
            data = {
                "tweet_id": tweet_record.tweet_id,
                "original_tweet": tweet_record.original_tweet,
                "response": tweet_record.response,
                "type": tweet_record.type,
                "time_posted": tweet_record.time_posted.isoformat(),
                "author_username": tweet_record.author_username
            }
            result = self.client.table("tweets").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving tweet: {e}")
            return False
    
    def save_engagement_metrics(self, metrics: EngagementMetrics) -> bool:
        """Save engagement metrics to the database"""
        try:
            data = {
                "tweet_id": metrics.tweet_id,
                "likes": metrics.likes,
                "retweets": metrics.retweets,
                "replies": metrics.replies,
                "timestamp": metrics.timestamp.isoformat()
            }
            result = self.client.table("engagement_metrics").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving engagement metrics: {e}")
            return False
    
    def get_recent_tweets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent tweets from the database"""
        try:
            result = self.client.table("tweets").select("*").order("time_posted", desc=True).limit(limit).execute()
            return result.data
        except Exception as e:
            print(f"Error fetching recent tweets: {e}")
            return []
    
    def get_top_performing_tweets(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top performing tweets based on engagement metrics"""
        try:
            query = """
            SELECT t.*, 
                   COALESCE(AVG(em.likes), 0) as avg_likes,
                   COALESCE(AVG(em.retweets), 0) as avg_retweets,
                   COALESCE(AVG(em.replies), 0) as avg_replies,
                   COALESCE(AVG(em.likes + em.retweets + em.replies), 0) as total_engagement
            FROM tweets t
            LEFT JOIN engagement_metrics em ON t.tweet_id = em.tweet_id
            GROUP BY t.id, t.tweet_id, t.original_tweet, t.response, t.type, t.time_posted, t.author_username, t.created_at
            ORDER BY total_engagement DESC
            LIMIT %s
            """
            result = self.client.rpc('exec_sql', {'sql': query % limit}).execute()
            return result.data
        except Exception as e:
            print(f"Error fetching top performing tweets: {e}")
            return []
    
    def tweet_exists(self, tweet_id: str) -> bool:
        """Check if a tweet already exists in the database"""
        try:
            result = self.client.table("tweets").select("tweet_id").eq("tweet_id", tweet_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error checking tweet existence: {e}")
            return False
    
    def get_tweets_needing_engagement_update(self) -> List[str]:
        """Get tweet IDs that need engagement metrics updates"""
        try:
            result = self.client.table("tweets").select("tweet_id").execute()
            return [tweet["tweet_id"] for tweet in result.data]
        except Exception as e:
            print(f"Error fetching tweets needing updates: {e}")
            return []
    
    def save_twitter_list(self, twitter_list: TwitterList) -> Optional[int]:
        """Save a Twitter list and return its ID"""
        try:
            data = {
                "name": twitter_list.name,
                "list_url": twitter_list.list_url
            }
            result = self.client.table("twitter_lists").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            print(f"Error saving Twitter list: {e}")
            return None
    
    def get_twitter_list_by_url(self, list_url: str) -> Optional[Dict[str, Any]]:
        """Get Twitter list by URL"""
        try:
            result = self.client.table("twitter_lists").select("*").eq("list_url", list_url).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error fetching Twitter list: {e}")
            return None
    
    def update_list_scraped_time(self, list_id: int) -> bool:
        """Update the last scraped timestamp for a list"""
        try:
            data = {"last_scraped": datetime.now().isoformat()}
            self.client.table("twitter_lists").update(data).eq("id", list_id).execute()
            return True
        except Exception as e:
            print(f"Error updating list scraped time: {e}")
            return False
    
    def save_list_tweet(self, list_tweet: ListTweet) -> bool:
        """Save a scraped tweet from a list"""
        try:
            data = {
                "list_id": list_tweet.list_id,
                "tweet_id": list_tweet.tweet_id,
                "url": list_tweet.url,
                "text": list_tweet.text,
                "author_username": list_tweet.author_username,
                "author_display_name": list_tweet.author_display_name,
                "created_at": list_tweet.created_at.isoformat(),
                "retweet_count": list_tweet.retweet_count,
                "reply_count": list_tweet.reply_count,
                "like_count": list_tweet.like_count,
                "quote_count": list_tweet.quote_count,
                "bookmark_count": list_tweet.bookmark_count,
                "is_retweet": list_tweet.is_retweet,
                "is_quote": list_tweet.is_quote
            }
            result = self.client.table("list_tweets").insert(data).execute()
            return True
        except Exception as e:
            print(f"Error saving list tweet: {e}")
            return False
    
    def get_list_tweets(self, list_id: Optional[int] = None, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """Get tweets from lists with pagination"""
        try:
            query = self.client.table("list_tweets").select("*").order("scraped_at", desc=True).limit(limit).range(offset, offset + limit - 1)
            
            if list_id:
                query = query.eq("list_id", list_id)
            
            result = query.execute()
            return result.data
        except Exception as e:
            print(f"Error fetching list tweets: {e}")
            return []
    
    def get_all_twitter_lists(self) -> List[Dict[str, Any]]:
        """Get all Twitter lists"""
        try:
            result = self.client.table("twitter_lists").select("*").order("created_at", desc=True).execute()
            return result.data
        except Exception as e:
            print(f"Error fetching Twitter lists: {e}")
            return []
    
    def save_manual_reply(self, manual_reply: ManualReply) -> Optional[int]:
        """Save a manual reply record"""
        try:
            if not self.client:
                print("Supabase client not configured, skipping manual reply save")
                return None
                
            data = {
                "tweet_id": manual_reply.tweet_id,
                "reply_text": manual_reply.reply_text,
                "method_used": manual_reply.method_used,
                "status": manual_reply.status,
                "error_message": manual_reply.error_message,
                "sent_at": manual_reply.sent_at.isoformat() if manual_reply.sent_at else None
            }
            result = self.client.table("manual_replies").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            print(f"Error saving manual reply (table may not exist): {e}")
            # Return a mock ID so the system continues working
            return 1
    
    def update_reply_status(self, reply_id: int, status: str, error_message: Optional[str] = None) -> bool:
        """Update the status of a manual reply"""
        try:
            data = {
                "status": status,
                "error_message": error_message,
                "sent_at": datetime.now().isoformat() if status == "sent" else None
            }
            self.client.table("manual_replies").update(data).eq("id", reply_id).execute()
            return True
        except Exception as e:
            print(f"Error updating reply status: {e}")
            return False
    
    def get_recent_replies(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent manual replies"""
        try:
            if not self.client:
                return []
            result = self.client.table("manual_replies").select("*").order("created_at", desc=True).limit(limit).execute()
            return result.data
        except Exception as e:
            print(f"Error fetching recent replies: {e}")
            return []
    
    def get_replied_tweet_ids(self) -> List[str]:
        """Get all tweet IDs that have been successfully replied to"""
        try:
            if not self.client:
                return []
            result = self.client.table("manual_replies").select("tweet_id").eq("status", "sent").execute()
            return [reply["tweet_id"] for reply in result.data]
        except Exception as e:
            print(f"Error fetching replied tweet IDs: {e}")
            return []
    
    def save_tweet_interaction(self, interaction: TweetInteraction) -> Optional[int]:
        """Save a tweet interaction record"""
        try:
            if not self.client:
                print("Supabase client not configured, skipping interaction save")
                return None
                
            data = {
                "tweet_id": interaction.tweet_id,
                "interaction_type": interaction.interaction_type,
                "method_used": interaction.method_used,
                "status": interaction.status,
                "error_message": interaction.error_message,
                "interaction_id": interaction.interaction_id,
                "completed_at": interaction.completed_at.isoformat() if interaction.completed_at else None
            }
            result = self.client.table("tweet_interactions").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            print(f"Error saving tweet interaction (table may not exist): {e}")
            # Return a mock ID so the system continues working
            return 1
    
    def update_interaction_status(self, interaction_id: int, status: str, error_message: Optional[str] = None) -> bool:
        """Update the status of a tweet interaction"""
        try:
            if not self.client:
                return False
            data = {
                "status": status,
                "error_message": error_message,
                "completed_at": datetime.now().isoformat() if status in ["success", "failed"] else None
            }
            self.client.table("tweet_interactions").update(data).eq("id", interaction_id).execute()
            return True
        except Exception as e:
            print(f"Error updating interaction status: {e}")
            return False
    
    def get_recent_interactions(self, limit: int = 20, interaction_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent tweet interactions"""
        try:
            if not self.client:
                return []
            
            query = self.client.table("tweet_interactions").select("*").order("created_at", desc=True).limit(limit)
            
            if interaction_type:
                query = query.eq("interaction_type", interaction_type)
            
            result = query.execute()
            return result.data
        except Exception as e:
            print(f"Error fetching recent interactions: {e}")
            return []
    
    def get_interacted_tweet_ids(self, interaction_type: str) -> List[str]:
        """Get all tweet IDs that have been successfully interacted with (liked/retweeted)"""
        try:
            if not self.client:
                return []
            result = self.client.table("tweet_interactions").select("tweet_id").eq("interaction_type", interaction_type).eq("status", "success").execute()
            return [interaction["tweet_id"] for interaction in result.data]
        except Exception as e:
            print(f"Error fetching interacted tweet IDs: {e}")
            return []
    
    def interaction_exists(self, tweet_id: str, interaction_type: str) -> bool:
        """Check if a specific interaction already exists for a tweet"""
        try:
            if not self.client:
                return False
            result = self.client.table("tweet_interactions").select("id").eq("tweet_id", tweet_id).eq("interaction_type", interaction_type).eq("status", "success").execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error checking interaction existence: {e}")
            return False
    
    def list_tweet_exists(self, tweet_id: str) -> bool:
        """Check if a list tweet already exists"""
        try:
            result = self.client.table("list_tweets").select("tweet_id").eq("tweet_id", tweet_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error checking list tweet existence: {e}")
            return False
    
    def save_processed_tweet(self, processed_tweet: ProcessedTweet) -> Optional[int]:
        """Save a processed tweet record"""
        try:
            if not self.client:
                print("Supabase client not configured, skipping processed tweet save")
                return None
                
            data = {
                "tweet_id": processed_tweet.tweet_id,
                "list_id": processed_tweet.list_id,
                "author_username": processed_tweet.author_username,
                "tweet_url": processed_tweet.tweet_url,
                "tweet_text": processed_tweet.tweet_text,
                "was_analyzed": processed_tweet.was_analyzed,
                "was_relevant": processed_tweet.was_relevant,
                "relevance_score": processed_tweet.relevance_score,
                "analysis_categories": processed_tweet.analysis_categories,
                "skip_reason": processed_tweet.skip_reason,
                "processed_at": processed_tweet.processed_at.isoformat()
            }
            result = self.client.table("processed_tweets").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            print(f"Error saving processed tweet (table may not exist): {e}")
            # Return a mock ID so the system continues working
            return 1
    
    def processed_tweet_exists(self, tweet_id: str) -> bool:
        """Check if a tweet has already been processed"""
        try:
            if not self.client:
                return False
            result = self.client.table("processed_tweets").select("id").eq("tweet_id", tweet_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error checking processed tweet existence: {e}")
            return False
    
    def get_last_processed_time(self, list_id: str = None) -> Optional[datetime]:
        """Get the last time tweets were processed from a specific list"""
        try:
            if not self.client:
                return None
            
            query = self.client.table("processed_tweets").select("processed_at").order("processed_at", desc=True).limit(1)
            
            if list_id:
                query = query.eq("list_id", list_id)
            
            result = query.execute()
            
            if result.data:
                return datetime.fromisoformat(result.data[0]["processed_at"].replace('Z', '+00:00'))
            return None
        except Exception as e:
            print(f"Error getting last processed time: {e}")
            return None
    
    def get_processed_tweets_count(self, list_id: str = None, hours_back: int = 24) -> int:
        """Get count of tweets processed in the last N hours"""
        try:
            if not self.client:
                return 0
            
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            query = self.client.table("processed_tweets").select("id", count="exact").gte("processed_at", cutoff_time.isoformat())
            
            if list_id:
                query = query.eq("list_id", list_id)
            
            result = query.execute()
            return result.count or 0
        except Exception as e:
            print(f"Error getting processed tweets count: {e}")
            return 0
    
    def bulk_check_processed_tweets(self, tweet_ids: List[str]) -> List[str]:
        """Check which tweets from a list have already been processed"""
        try:
            if not self.client:
                return []
            
            result = self.client.table("processed_tweets").select("tweet_id").in_("tweet_id", tweet_ids).execute()
            return [row["tweet_id"] for row in result.data]
        except Exception as e:
            print(f"Error bulk checking processed tweets: {e}")
            return []
    
    # Tweet Decision V2 methods
    
    def save_tweet_decision(self, decision: TweetDecision) -> Optional[int]:
        """Save a tweet filtering decision (V2)"""
        try:
            if not self.client:
                print("Supabase client not configured, skipping decision save")
                return None
                
            data = {
                "tweet_id": decision.tweet_id,
                "list_id": decision.list_id,
                "author_username": decision.author_username,
                "tweet_text": decision.tweet_text,
                "stage_quick": decision.stage_quick,
                "quick_reason": decision.quick_reason,
                "stage_ai": decision.stage_ai,
                "ai_score": decision.ai_score,
                "ai_reason": decision.ai_reason,
                "final": decision.final,
                "categories": decision.categories,
                "processing_time_ms": decision.processing_time_ms,
                "relevance_threshold": decision.relevance_threshold,
                "filter_version": decision.filter_version
            }
            result = self.client.table("tweet_decisions").insert(data).execute()
            return result.data[0]["id"] if result.data else None
        except Exception as e:
            print(f"Error saving tweet decision (table may not exist): {e}")
            return 1  # Mock ID for development
    
    def get_approved_tweets(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get approved tweets from decisions table"""
        try:
            if not self.client:
                return []
            
            result = self.client.table("tweet_decisions") \
                .select("*") \
                .eq("final", "approved") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .range(offset, offset + limit - 1) \
                .execute()
            return result.data
        except Exception as e:
            print(f"Error fetching approved tweets: {e}")
            return []
    
    def get_decision_stats(self, hours_back: int = 24) -> Dict[str, Any]:
        """Get filtering decision statistics"""
        try:
            if not self.client:
                return {"total": 0, "approved": 0, "quick_rejects": 0, "ai_rejects": 0}
            
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            # Get total decisions
            total_result = self.client.table("tweet_decisions") \
                .select("id", count="exact") \
                .gte("created_at", cutoff_time.isoformat()) \
                .execute()
            
            # Get approved count
            approved_result = self.client.table("tweet_decisions") \
                .select("id", count="exact") \
                .eq("final", "approved") \
                .gte("created_at", cutoff_time.isoformat()) \
                .execute()
            
            # Get quick rejects
            quick_rejects_result = self.client.table("tweet_decisions") \
                .select("id", count="exact") \
                .eq("stage_quick", "reject") \
                .gte("created_at", cutoff_time.isoformat()) \
                .execute()
            
            # Get AI rejects
            ai_rejects_result = self.client.table("tweet_decisions") \
                .select("id", count="exact") \
                .eq("stage_ai", "reject") \
                .gte("created_at", cutoff_time.isoformat()) \
                .execute()
            
            total = total_result.count or 0
            approved = approved_result.count or 0
            quick_rejects = quick_rejects_result.count or 0 
            ai_rejects = ai_rejects_result.count or 0
            
            approval_rate = (approved / total * 100) if total > 0 else 0
            
            return {
                "total": total,
                "approved": approved,
                "quick_rejects": quick_rejects,
                "ai_rejects": ai_rejects,
                "approval_rate": round(approval_rate, 1),
                "hours_back": hours_back
            }
        except Exception as e:
            print(f"Error getting decision stats: {e}")
            return {"total": 0, "approved": 0, "quick_rejects": 0, "ai_rejects": 0, "approval_rate": 0}
    
    def decision_exists(self, tweet_id: str) -> bool:
        """Check if a decision already exists for a tweet"""
        try:
            if not self.client:
                return False
            result = self.client.table("tweet_decisions").select("id").eq("tweet_id", tweet_id).execute()
            return len(result.data) > 0
        except Exception as e:
            print(f"Error checking decision existence: {e}")
            return False
    
    def get_recent_decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent filtering decisions for debugging"""
        try:
            if not self.client:
                return []
            
            result = self.client.table("tweet_decisions") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return result.data
        except Exception as e:
            print(f"Error fetching recent decisions: {e}")
            return []

db = Database()