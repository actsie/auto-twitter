import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

class TwitterBotLogger:
    def __init__(self, log_level: str = "INFO"):
        self.logger = logging.getLogger("TwitterBot")
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Ensure logs directory exists
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # File handler for all logs (rotating)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "twitter_bot.log"),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(file_handler)
        
        # File handler for errors only
        error_handler = RotatingFileHandler(
            os.path.join(log_dir, "twitter_bot_errors.log"),
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(error_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        self.logger.addHandler(console_handler)
        
        # Activity log for successful operations
        activity_handler = RotatingFileHandler(
            os.path.join(log_dir, "twitter_bot_activity.log"),
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        activity_handler.setLevel(logging.INFO)
        activity_handler.addFilter(self._activity_filter)
        activity_handler.setFormatter(simple_formatter)
        self.logger.addHandler(activity_handler)
    
    def _activity_filter(self, record):
        """Filter for activity log - only successful operations"""
        activity_keywords = [
            "successfully", "completed", "posted", "saved", "updated",
            "initialized", "connected", "processed"
        ]
        return any(keyword in record.getMessage().lower() for keyword in activity_keywords)
    
    def info(self, message: str, extra: Optional[dict] = None):
        self.logger.info(message, extra=extra)
    
    def error(self, message: str, exception: Optional[Exception] = None, extra: Optional[dict] = None):
        if exception:
            self.logger.error(f"{message}: {str(exception)}", exc_info=True, extra=extra)
        else:
            self.logger.error(message, extra=extra)
    
    def warning(self, message: str, extra: Optional[dict] = None):
        self.logger.warning(message, extra=extra)
    
    def debug(self, message: str, extra: Optional[dict] = None):
        self.logger.debug(message, extra=extra)
    
    def log_tweet_processed(self, tweet_id: str, author: str, response_type: str, success: bool):
        """Log tweet processing results"""
        status = "successfully processed" if success else "failed to process"
        self.info(f"Tweet {tweet_id} from @{author} ({response_type}) {status}")
    
    def log_engagement_update(self, tweet_id: str, metrics: dict, success: bool):
        """Log engagement metric updates"""
        if success:
            self.info(f"Updated engagement for tweet {tweet_id}: {metrics}")
        else:
            self.error(f"Failed to update engagement for tweet {tweet_id}")
    
    def log_polling_cycle(self, tweets_found: int, tweets_processed: int, errors: int):
        """Log polling cycle results"""
        self.info(f"Polling cycle completed: {tweets_found} tweets found, {tweets_processed} processed, {errors} errors")
    
    def log_api_error(self, api_name: str, error: Exception, context: str = ""):
        """Log API-related errors"""
        context_str = f" ({context})" if context else ""
        self.error(f"{api_name} API error{context_str}", exception=error)
    
    def log_database_error(self, operation: str, error: Exception, context: str = ""):
        """Log database-related errors"""
        context_str = f" ({context})" if context else ""
        self.error(f"Database {operation} error{context_str}", exception=error)
    
    def log_startup(self):
        """Log application startup"""
        self.info("=" * 60)
        self.info("Twitter Bot Starting Up")
        self.info(f"Timestamp: {datetime.now()}")
        self.info("=" * 60)
    
    def log_shutdown(self):
        """Log application shutdown"""
        self.info("=" * 60)
        self.info("Twitter Bot Shutting Down")
        self.info(f"Timestamp: {datetime.now()}")
        self.info("=" * 60)

# Global logger instance
logger = TwitterBotLogger()