import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    def __init__(self):
        self.twitter_consumer_key: str = os.getenv("TWITTER_CONSUMER_KEY", "")
        self.twitter_consumer_secret: str = os.getenv("TWITTER_CONSUMER_SECRET", "")
        self.twitter_access_token: str = os.getenv("TWITTER_ACCESS_TOKEN", "")
        self.twitter_access_token_secret: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")
        self.twitter_bearer_token: str = os.getenv("TWITTER_BEARER_TOKEN", "")
        
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        
        self.supabase_url: str = os.getenv("SUPABASE_URL", "")
        self.supabase_key: str = os.getenv("SUPABASE_KEY", "")
        
        self.apify_api_token: str = os.getenv("APIFY_API_TOKEN", "")
        self.apify_user_id: str = os.getenv("APIFY_USER_ID", "")
        self.n8n_webhook_url: str = os.getenv("N8N_WEBHOOK_URL", "")
        
        self.rapidapi_key: str = os.getenv("RAPIDAPI_KEY", "")
        self.rapidapi_app: str = os.getenv("RAPIDAPI_APP", "")
        
        target_accounts_str = os.getenv("TARGET_ACCOUNTS", "")
        self.target_accounts: List[str] = [acc.strip() for acc in target_accounts_str.split(",") if acc.strip()]
        self.poll_interval_minutes: int = int(os.getenv("POLL_INTERVAL_MINUTES", "5"))
        self.engagement_check_hours: int = int(os.getenv("ENGAGEMENT_CHECK_HOURS", "2"))
        
        # Filtering V2 configuration
        self.feature_filter_v2: bool = os.getenv("FEATURE_FILTER_V2", "true").lower() == "true"
        self.approval_rate_target: float = float(os.getenv("APPROVAL_RATE_TARGET", "10.0"))
        self.max_approvals_per_hour: int = int(os.getenv("MAX_APPROVALS_PER_HOUR", "20"))
        self.max_per_author_6h: int = int(os.getenv("MAX_PER_AUTHOR_6H", "2"))
        self.relevance_threshold: float = float(os.getenv("RELEVANCE_THRESHOLD", "80.0"))
        self.enable_language_detection: bool = os.getenv("ENABLE_LANGUAGE_DETECTION", "false").lower() == "true"

settings = Settings()