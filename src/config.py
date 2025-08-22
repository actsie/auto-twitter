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
        self.n8n_like_webhook_url: str = os.getenv("N8N_LIKE_WEBHOOK_URL", "")
        self.n8n_rt_webhook_url: str = os.getenv("N8N_RT_WEBHOOK_URL", "")
        self.n8n_qrt_webhook_url: str = os.getenv("N8N_QRT_WEBHOOK_URL", "")
        
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
        self.max_per_author_6h: int = int(os.getenv("MAX_PER_AUTHOR_6H", "4"))
        self.relevance_threshold: float = float(os.getenv("RELEVANCE_THRESHOLD", "20.0"))
        self.enable_language_detection: bool = os.getenv("ENABLE_LANGUAGE_DETECTION", "false").lower() == "true"
        
        # Smart Backfill configuration
        self.backfill_max_attempts: int = int(os.getenv("BACKFILL_MAX_ATTEMPTS", "5"))
        self.backfill_max_multiplier: int = int(os.getenv("BACKFILL_MAX_MULTIPLIER", "8"))
        self.backfill_start_window_min: int = int(os.getenv("BACKFILL_START_WINDOW_MIN", "30"))
        self.backfill_max_window_min: int = int(os.getenv("BACKFILL_MAX_WINDOW_MIN", "2880"))
        self.backfill_min_approval_rate: float = float(os.getenv("BACKFILL_MIN_APPROVAL_RATE", "0.01"))
        self.backfill_batch_base: int = int(os.getenv("BACKFILL_BATCH_BASE", "10"))
        
        # Search functionality configuration
        self.search_presets = {
            # Original tech/AI presets
            "ai_research": "\"GPT-4\" OR \"Claude\" OR \"LLM\" OR \"large language model\" (research OR paper OR breakthrough) -is:retweet lang:en",
            "dev_tools": "devtools OR \"developer tools\" OR \"coding assistant\" OR copilot OR cursor -is:retweet lang:en",
            "ml_tutorials": "\"machine learning\" OR \"deep learning\" (tutorial OR code OR example OR guide) -is:retweet lang:en", 
            "ai_agents": "\"AI agent\" OR \"agentic\" OR \"autonomous agent\" (framework OR tool OR platform) -is:retweet lang:en",
            "productivity": "\"no-code\" OR \"low-code\" OR automation OR workflow (tool OR platform OR saas) -is:retweet lang:en",
            "programming": "programming OR \"software development\" OR coding (python OR javascript OR react) -is:retweet lang:en",
            "startups": "startup OR \"early stage\" OR funding OR \"venture capital\" (AI OR ML OR tech) -is:retweet lang:en",
            "research_papers": "\"new paper\" OR \"research paper\" OR arxiv (AI OR ML OR \"machine learning\") -is:retweet lang:en",
            "open_source": "\"open source\" OR github OR \"pull request\" OR contributor (AI OR ML OR developer) -is:retweet lang:en",
            "tech_news": "\"tech news\" OR \"breaking news\" OR announcement (AI OR technology OR startup) -is:retweet lang:en",
            
            # Pawgrammer-focused: workflow pain & tool struggles
            "tool_struggles": "\"I still manually\" OR \"manually track\" OR \"manually send\" OR \"manually doing\" -filter:links -filter:retweets lang:en",
            "spreadsheet_pain": "spreadsheet OR \"google sheets\" OR \"excel\" (\"too complex\" OR \"out of hand\" OR \"not working\" OR \"getting crazy\") -filter:retweets lang:en",
            "adhd_productivity": "adhd (\"forgot to\" OR \"can't focus\" OR \"my system doesn't work\" OR \"keep losing track\") -filter:retweets lang:en",
            "claude_build_friction": "Claude (\"stuck\" OR \"not working\" OR \"trying to build\" OR \"terminal\" OR \"doesn't run\" OR \"error\") -filter:retweets lang:en",
            "custom_workflows": "\"custom workflow\" OR \"tracking system\" OR \"built a tool\" OR \"made a system\" -filter:retweets lang:en",
            "indie_builders": "\"built this to\" OR \"made a small tool\" OR \"automate my\" OR \"created a script\" -filter:retweets lang:en",
            "workflow_pain": "\"i hate doing\" OR \"wish i had a tool\" OR \"frustrated with\" OR \"spent all day\" -filter:retweets lang:en",
            "process_complaints": "\"why is\" (\"still so bad\" OR \"so difficult\" OR \"not working\") OR \"wish there was\" -filter:retweets lang:en"
        }
        
        # Mass Discovery configuration
        self.discovery_lists = [
            "1957324919269929248",  # Main AI/Tech list
            "1278784207641284609",  # Secondary list if available
            # Add more list IDs here as needed
        ]
        self.discovery_batch_size = 100  # Large batches for mass discovery
        self.discovery_max_per_source = 200  # Max tweets per source
        self.discovery_parallel_sources = 5  # Process N sources simultaneously

settings = Settings()