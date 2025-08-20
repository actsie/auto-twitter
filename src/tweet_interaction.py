#!/usr/bin/env python3
"""
Twitter Auto Bot - Tweet Interaction Service

Handles likes, retweets, and replies for tweets through various methods
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from .config import settings
from .logger import logger
from .twitter_client import twitter_client
from .manual_reply import manual_reply_service


class InteractionType(Enum):
    LIKE = "like"
    RETWEET = "retweet"
    REPLY = "reply"


class InteractionStatus(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class InteractionResult:
    """Result of a tweet interaction attempt"""
    success: bool
    interaction_type: InteractionType
    method_used: str
    error_message: Optional[str] = None
    interaction_id: Optional[str] = None


@dataclass
class BulkInteractionResult:
    """Result of bulk interaction operations"""
    total_requested: int
    successful_count: int
    failed_count: int
    results: List[InteractionResult]
    errors: List[str]


class TweetInteractionService:
    """Service for handling all tweet interactions (like, retweet, reply)"""
    
    def __init__(self):
        self.methods = ["twitter_api", "mock_success"]
        self.rate_limits = {
            "like": {"requests_per_15min": 300, "current_count": 0, "reset_time": None},
            "retweet": {"requests_per_15min": 300, "current_count": 0, "reset_time": None},
            "reply": {"requests_per_15min": 300, "current_count": 0, "reset_time": None}
        }
        self.last_request_times = {"like": None, "retweet": None, "reply": None}
    
    def _check_rate_limit(self, interaction_type: str) -> bool:
        """Check if we're within rate limits for the interaction type"""
        current_time = time.time()
        rate_limit_info = self.rate_limits.get(interaction_type)
        
        if not rate_limit_info:
            return True
        
        # Reset counter if 15 minutes have passed
        if rate_limit_info["reset_time"] and current_time >= rate_limit_info["reset_time"]:
            rate_limit_info["current_count"] = 0
            rate_limit_info["reset_time"] = None
        
        # Check if we're at the limit
        if rate_limit_info["current_count"] >= rate_limit_info["requests_per_15min"]:
            return False
        
        return True
    
    def _update_rate_limit(self, interaction_type: str):
        """Update rate limit counter after a successful request"""
        current_time = time.time()
        rate_limit_info = self.rate_limits.get(interaction_type)
        
        if not rate_limit_info:
            return
        
        # Set reset time if this is the first request in the window
        if rate_limit_info["reset_time"] is None:
            rate_limit_info["reset_time"] = current_time + 900  # 15 minutes
        
        rate_limit_info["current_count"] += 1
        self.last_request_times[interaction_type] = current_time
    
    def _get_rate_limit_wait_time(self, interaction_type: str) -> Optional[int]:
        """Get seconds to wait before the rate limit resets"""
        rate_limit_info = self.rate_limits.get(interaction_type)
        
        if not rate_limit_info or not rate_limit_info["reset_time"]:
            return None
        
        current_time = time.time()
        wait_time = int(rate_limit_info["reset_time"] - current_time)
        
        return max(0, wait_time)
    
    async def _apply_request_spacing(self, interaction_type: str):
        """Apply intelligent spacing between requests to avoid hitting rate limits"""
        last_request = self.last_request_times.get(interaction_type)
        
        if last_request:
            time_since_last = time.time() - last_request
            
            # Minimum 1 second between requests, but be more conservative if approaching limits
            rate_limit_info = self.rate_limits.get(interaction_type, {})
            current_count = rate_limit_info.get("current_count", 0)
            max_requests = rate_limit_info.get("requests_per_15min", 300)
            
            # Calculate dynamic delay based on usage
            usage_ratio = current_count / max_requests
            
            if usage_ratio > 0.8:  # Over 80% usage
                min_delay = 3  # 3 seconds between requests
            elif usage_ratio > 0.6:  # Over 60% usage
                min_delay = 2  # 2 seconds between requests
            else:
                min_delay = 1  # 1 second between requests
            
            if time_since_last < min_delay:
                delay = min_delay - time_since_last
                logger.info(f"Rate limiting: waiting {delay:.1f} seconds before {interaction_type}")
                await asyncio.sleep(delay)
    
    async def like_tweet(self, tweet_id: str, tweet_url: str = "") -> InteractionResult:
        """
        Like a tweet using available methods
        
        Args:
            tweet_id: ID of the tweet to like
            tweet_url: URL of the tweet (optional)
            
        Returns:
            InteractionResult with success status and details
        """
        logger.info(f"Attempting to like tweet {tweet_id}")
        
        # Check rate limits
        if not self._check_rate_limit("like"):
            wait_time = self._get_rate_limit_wait_time("like")
            error_msg = f"Rate limit exceeded for likes. Try again in {wait_time} seconds"
            logger.warning(error_msg)
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.LIKE,
                method_used="rate_limited",
                error_message=error_msg
            )
        
        # Apply intelligent request spacing
        await self._apply_request_spacing("like")
        
        # Try methods in order of preference
        for method in self.methods:
            try:
                logger.info(f"Trying {method} method for liking tweet")
                
                if method == "twitter_api":
                    result = await self._like_via_twitter_api(tweet_id)
                elif method == "mock_success":
                    result = await self._like_via_mock(tweet_id)
                else:
                    continue
                
                if result.success:
                    # Update rate limit counter
                    self._update_rate_limit("like")
                    logger.info(f"Tweet liked successfully via {method}")
                    return result
                else:
                    logger.warning(f"Like failed via {method}: {result.error_message}")
                
            except Exception as e:
                logger.error(f"Error with {method} method for liking: {e}")
                continue
        
        # All methods failed
        error_msg = "All like methods failed"
        logger.error(error_msg)
        return InteractionResult(
            success=False,
            interaction_type=InteractionType.LIKE,
            method_used="none",
            error_message=error_msg
        )
    
    async def retweet_tweet(self, tweet_id: str, tweet_url: str = "") -> InteractionResult:
        """
        Retweet a tweet using available methods
        
        Args:
            tweet_id: ID of the tweet to retweet
            tweet_url: URL of the tweet (optional)
            
        Returns:
            InteractionResult with success status and details
        """
        logger.info(f"Attempting to retweet tweet {tweet_id}")
        
        # Check rate limits
        if not self._check_rate_limit("retweet"):
            wait_time = self._get_rate_limit_wait_time("retweet")
            error_msg = f"Rate limit exceeded for retweets. Try again in {wait_time} seconds"
            logger.warning(error_msg)
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.RETWEET,
                method_used="rate_limited",
                error_message=error_msg
            )
        
        # Apply intelligent request spacing
        await self._apply_request_spacing("retweet")
        
        # Try methods in order of preference
        for method in self.methods:
            try:
                logger.info(f"Trying {method} method for retweeting tweet")
                
                if method == "twitter_api":
                    result = await self._retweet_via_twitter_api(tweet_id)
                elif method == "mock_success":
                    result = await self._retweet_via_mock(tweet_id)
                else:
                    continue
                
                if result.success:
                    # Update rate limit counter
                    self._update_rate_limit("retweet")
                    logger.info(f"Tweet retweeted successfully via {method}")
                    return result
                else:
                    logger.warning(f"Retweet failed via {method}: {result.error_message}")
                
            except Exception as e:
                logger.error(f"Error with {method} method for retweeting: {e}")
                continue
        
        # All methods failed
        error_msg = "All retweet methods failed"
        logger.error(error_msg)
        return InteractionResult(
            success=False,
            interaction_type=InteractionType.RETWEET,
            method_used="none",
            error_message=error_msg
        )
    
    async def reply_to_tweet(self, tweet_id: str, reply_text: str, target_username: str = "") -> InteractionResult:
        """
        Reply to a tweet using existing manual reply service
        
        Args:
            tweet_id: ID of the tweet to reply to
            reply_text: The reply text
            target_username: Username of the original tweet author
            
        Returns:
            InteractionResult with success status and details
        """
        logger.info(f"Attempting to reply to tweet {tweet_id}")
        
        try:
            # Use existing manual reply service
            reply_result = await manual_reply_service.send_reply(tweet_id, reply_text, target_username)
            
            return InteractionResult(
                success=reply_result.success,
                interaction_type=InteractionType.REPLY,
                method_used=reply_result.method_used,
                error_message=reply_result.error_message,
                interaction_id=reply_result.reply_id
            )
        except Exception as e:
            logger.error(f"Error replying to tweet: {e}")
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.REPLY,
                method_used="none",
                error_message=str(e)
            )
    
    async def bulk_like_tweets(self, tweet_ids: List[str]) -> BulkInteractionResult:
        """
        Like multiple tweets with rate limiting
        
        Args:
            tweet_ids: List of tweet IDs to like
            
        Returns:
            BulkInteractionResult with summary of operations
        """
        logger.info(f"Starting bulk like operation for {len(tweet_ids)} tweets")
        
        results = []
        errors = []
        successful_count = 0
        
        for i, tweet_id in enumerate(tweet_ids):
            try:
                # Add delay between requests to respect rate limits
                if i > 0:
                    await asyncio.sleep(1)  # 1 second delay between likes
                
                result = await self.like_tweet(tweet_id)
                results.append(result)
                
                if result.success:
                    successful_count += 1
                else:
                    errors.append(f"Tweet {tweet_id}: {result.error_message}")
                
            except Exception as e:
                error_msg = f"Tweet {tweet_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Error in bulk like for tweet {tweet_id}: {e}")
        
        failed_count = len(tweet_ids) - successful_count
        
        logger.info(f"Bulk like completed: {successful_count} successful, {failed_count} failed")
        
        return BulkInteractionResult(
            total_requested=len(tweet_ids),
            successful_count=successful_count,
            failed_count=failed_count,
            results=results,
            errors=errors
        )
    
    async def bulk_retweet_tweets(self, tweet_ids: List[str]) -> BulkInteractionResult:
        """
        Retweet multiple tweets with rate limiting
        
        Args:
            tweet_ids: List of tweet IDs to retweet
            
        Returns:
            BulkInteractionResult with summary of operations
        """
        logger.info(f"Starting bulk retweet operation for {len(tweet_ids)} tweets")
        
        results = []
        errors = []
        successful_count = 0
        
        for i, tweet_id in enumerate(tweet_ids):
            try:
                # Add delay between requests to respect rate limits
                if i > 0:
                    await asyncio.sleep(2)  # 2 second delay between retweets (stricter limit)
                
                result = await self.retweet_tweet(tweet_id)
                results.append(result)
                
                if result.success:
                    successful_count += 1
                else:
                    errors.append(f"Tweet {tweet_id}: {result.error_message}")
                
            except Exception as e:
                error_msg = f"Tweet {tweet_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Error in bulk retweet for tweet {tweet_id}: {e}")
        
        failed_count = len(tweet_ids) - successful_count
        
        logger.info(f"Bulk retweet completed: {successful_count} successful, {failed_count} failed")
        
        return BulkInteractionResult(
            total_requested=len(tweet_ids),
            successful_count=successful_count,
            failed_count=failed_count,
            results=results,
            errors=errors
        )
    
    async def _like_via_twitter_api(self, tweet_id: str) -> InteractionResult:
        """Like tweet via Twitter API directly"""
        try:
            # Check if Twitter client is available
            if not twitter_client.test_connection():
                return InteractionResult(
                    success=False,
                    interaction_type=InteractionType.LIKE,
                    method_used="twitter_api",
                    error_message="Twitter API connection failed"
                )
            
            # Like tweet using tweepy
            loop = asyncio.get_event_loop()
            
            def like_tweet():
                try:
                    response = twitter_client.api.like(tweet_id)
                    return response.data if response.data else None
                except Exception as e:
                    raise e
            
            response_data = await loop.run_in_executor(None, like_tweet)
            
            if response_data:
                return InteractionResult(
                    success=True,
                    interaction_type=InteractionType.LIKE,
                    method_used="twitter_api",
                    interaction_id=str(response_data.get("id", tweet_id))
                )
            else:
                return InteractionResult(
                    success=False,
                    interaction_type=InteractionType.LIKE,
                    method_used="twitter_api",
                    error_message="Failed to get response from Twitter API"
                )
                
        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                error_msg = "Twitter API rate limit exceeded for likes"
            elif "403" in error_msg:
                error_msg = "Twitter API access forbidden (already liked or permission issue)"
            elif "404" in error_msg:
                error_msg = "Tweet not found or deleted"
            
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.LIKE,
                method_used="twitter_api",
                error_message=error_msg
            )
    
    async def _retweet_via_twitter_api(self, tweet_id: str) -> InteractionResult:
        """Retweet tweet via Twitter API directly"""
        try:
            # Check if Twitter client is available
            if not twitter_client.test_connection():
                return InteractionResult(
                    success=False,
                    interaction_type=InteractionType.RETWEET,
                    method_used="twitter_api",
                    error_message="Twitter API connection failed"
                )
            
            # Retweet using tweepy
            loop = asyncio.get_event_loop()
            
            def retweet_tweet():
                try:
                    response = twitter_client.api.retweet(tweet_id)
                    return response.data if response.data else None
                except Exception as e:
                    raise e
            
            response_data = await loop.run_in_executor(None, retweet_tweet)
            
            if response_data:
                return InteractionResult(
                    success=True,
                    interaction_type=InteractionType.RETWEET,
                    method_used="twitter_api",
                    interaction_id=str(response_data.get("id", tweet_id))
                )
            else:
                return InteractionResult(
                    success=False,
                    interaction_type=InteractionType.RETWEET,
                    method_used="twitter_api",
                    error_message="Failed to get response from Twitter API"
                )
                
        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                error_msg = "Twitter API rate limit exceeded for retweets"
            elif "403" in error_msg:
                error_msg = "Twitter API access forbidden (already retweeted or permission issue)"
            elif "404" in error_msg:
                error_msg = "Tweet not found or deleted"
            
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.RETWEET,
                method_used="twitter_api",
                error_message=error_msg
            )
    
    async def _like_via_mock(self, tweet_id: str) -> InteractionResult:
        """Mock method for testing - simulates successful like"""
        try:
            logger.info(f"MOCK LIKE: Would like tweet {tweet_id}")
            await asyncio.sleep(0.5)  # Simulate API delay
            return InteractionResult(
                success=True,
                interaction_type=InteractionType.LIKE,
                method_used="mock_success",
                interaction_id=f"mock_like_{tweet_id}"
            )
        except Exception as e:
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.LIKE,
                method_used="mock_success",
                error_message=str(e)
            )
    
    async def _retweet_via_mock(self, tweet_id: str) -> InteractionResult:
        """Mock method for testing - simulates successful retweet"""
        try:
            logger.info(f"MOCK RETWEET: Would retweet tweet {tweet_id}")
            await asyncio.sleep(0.5)  # Simulate API delay
            return InteractionResult(
                success=True,
                interaction_type=InteractionType.RETWEET,
                method_used="mock_success",
                interaction_id=f"mock_retweet_{tweet_id}"
            )
        except Exception as e:
            return InteractionResult(
                success=False,
                interaction_type=InteractionType.RETWEET,
                method_used="mock_success",
                error_message=str(e)
            )
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get current rate limit status for all interaction types"""
        current_time = time.time()
        status = {}
        
        for interaction_type, limits in self.rate_limits.items():
            # Check if window has expired
            if limits["reset_time"] and current_time >= limits["reset_time"]:
                limits["current_count"] = 0
                limits["reset_time"] = None
            
            remaining = limits["requests_per_15min"] - limits["current_count"]
            
            status[interaction_type] = {
                "total_limit": limits["requests_per_15min"],
                "used": limits["current_count"],
                "remaining": remaining,
                "reset_time": limits["reset_time"],
                "reset_in_seconds": int(limits["reset_time"] - current_time) if limits["reset_time"] else None,
                "percentage_used": round((limits["current_count"] / limits["requests_per_15min"]) * 100, 1)
            }
        
        return status


# Global service instance
tweet_interaction_service = TweetInteractionService()