import pytest
import asyncio
import sys
import os

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from src.config import settings
from src.database import Database
from src.response_generator import ResponseGenerator

class TestConfig:
    def test_settings_exist(self):
        """Test that settings are properly loaded"""
        assert hasattr(settings, 'poll_interval_minutes')
        assert hasattr(settings, 'target_accounts')
        assert isinstance(settings.poll_interval_minutes, int)
        assert isinstance(settings.target_accounts, list)

class TestDatabase:
    @pytest.mark.asyncio
    async def test_database_initialization(self):
        """Test database can be initialized"""
        db = Database()
        assert db is not None
        assert hasattr(db, 'client')

class TestResponseGenerator:
    def test_response_generator_initialization(self):
        """Test response generator can be initialized"""
        generator = ResponseGenerator()
        assert generator is not None
        assert hasattr(generator, 'default_examples')
        assert len(generator.default_examples) > 0
    
    def test_response_appropriateness_check(self):
        """Test response appropriateness validation"""
        generator = ResponseGenerator()
        
        # Test appropriate response
        appropriate_response = "Great point! This is really interesting to think about."
        original_tweet = "AI is changing everything we know about technology."
        assert generator.is_response_appropriate(appropriate_response, original_tweet)
        
        # Test inappropriate response (too short)
        short_response = "Yes"
        assert not generator.is_response_appropriate(short_response, original_tweet)
        
        # Test inappropriate response (AI marker)
        ai_response = "As an AI, I cannot provide that information."
        assert not generator.is_response_appropriate(ai_response, original_tweet)

class TestIntegration:
    def test_imports_work(self):
        """Test that all main modules can be imported"""
        try:
            from src.twitter_client import TwitterClient
            from src.tweet_poller import TweetPoller
            from src.tweet_processor import TweetProcessor
            from src.engagement_tracker import EngagementTracker
            from src.scheduler import TwitterBotScheduler
            from src.logger import TwitterBotLogger
            assert True
        except ImportError as e:
            pytest.fail(f"Import failed: {e}")

if __name__ == "__main__":
    pytest.main([__file__])