#!/usr/bin/env python3
"""
Twitter Auto Bot - Manual Reply System

Handles sending manual replies through various methods (n8n webhook, Twitter API, Puppeteer)
"""

import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any
import requests
from dataclasses import dataclass

from .config import settings
from .logger import logger
from .database import db, ManualReply
from .twitter_client import twitter_client


@dataclass
class ReplyResult:
    """Result of a reply attempt"""
    success: bool
    method_used: str
    error_message: Optional[str] = None
    reply_id: Optional[str] = None


class ManualReplyService:
    """Service for sending manual replies using multiple methods"""
    
    def __init__(self):
        self.n8n_webhook_url = settings.n8n_webhook_url
        self.methods = ["n8n", "mock_success", "twitter_api", "puppeteer"]
    
    async def send_reply(self, tweet_id: str, reply_text: str, target_username: str = "") -> ReplyResult:
        """
        Send a manual reply using the best available method
        
        Args:
            tweet_id: ID of the tweet to reply to
            reply_text: The reply text to send
            target_username: Username of the original tweet author
            
        Returns:
            ReplyResult with success status and details
        """
        logger.info(f"Attempting to send reply to tweet {tweet_id}")
        
        # Save reply record as pending
        reply_record = ManualReply(
            tweet_id=tweet_id,
            reply_text=reply_text,
            method_used="pending",
            status="pending"
        )
        reply_id = db.save_manual_reply(reply_record)
        
        # Try methods in order of preference
        for method in self.methods:
            try:
                logger.info(f"Trying {method} method for reply")
                
                if method == "mock_success":
                    result = await self._send_via_mock(tweet_id, reply_text)
                elif method == "n8n":
                    result = await self._send_via_n8n(tweet_id, reply_text)
                elif method == "twitter_api":
                    result = await self._send_via_twitter_api(tweet_id, reply_text)
                elif method == "puppeteer":
                    result = await self._send_via_puppeteer(tweet_id, reply_text)
                else:
                    continue
                
                # Update database record
                if reply_id:
                    if result.success:
                        db.update_reply_status(reply_id, "sent")
                        logger.info(f"Reply sent successfully via {method}")
                        return result
                    else:
                        db.update_reply_status(reply_id, "failed", result.error_message)
                        logger.warning(f"Reply failed via {method}: {result.error_message}")
                
            except Exception as e:
                logger.error(f"Error with {method} method: {e}")
                if reply_id:
                    db.update_reply_status(reply_id, "failed", str(e))
        
        # All methods failed
        error_msg = "All reply methods failed"
        logger.error(error_msg)
        return ReplyResult(success=False, method_used="none", error_message=error_msg)
    
    async def _send_via_mock(self, tweet_id: str, reply_text: str) -> ReplyResult:
        """Mock method for testing - simulates successful reply posting"""
        try:
            logger.info(f"MOCK REPLY: Would reply to tweet {tweet_id} with: {reply_text}")
            await asyncio.sleep(0.5)  # Simulate API delay
            return ReplyResult(
                success=True, 
                method_used="mock_success",
                reply_id=f"mock_reply_{tweet_id}"
            )
        except Exception as e:
            return ReplyResult(success=False, method_used="mock_success", error_message=str(e))
    
    async def _send_via_n8n(self, tweet_id: str, reply_text: str) -> ReplyResult:
        """Send reply via n8n webhook"""
        if not self.n8n_webhook_url:
            return ReplyResult(success=False, method_used="n8n", error_message="N8N webhook URL not configured")
        
        try:
            payload = {
                "tweet_id": tweet_id,
                "reply_text": reply_text
            }
            
            # Make request in thread to avoid blocking
            loop = asyncio.get_event_loop()
            
            def make_request():
                response = requests.post(
                    self.n8n_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            
            result = await loop.run_in_executor(None, make_request)
            
            # Check if n8n responded positively
            if result.get("message") == "Workflow was started":
                return ReplyResult(success=True, method_used="n8n")
            else:
                return ReplyResult(success=False, method_used="n8n", error_message="N8N workflow failed to start")
                
        except requests.exceptions.RequestException as e:
            return ReplyResult(success=False, method_used="n8n", error_message=f"HTTP error: {e}")
        except Exception as e:
            return ReplyResult(success=False, method_used="n8n", error_message=str(e))
    
    async def _send_via_twitter_api(self, tweet_id: str, reply_text: str) -> ReplyResult:
        """Send reply via Twitter API directly"""
        try:
            # Use existing Twitter client
            if not twitter_client.test_connection():
                return ReplyResult(success=False, method_used="twitter_api", error_message="Twitter API connection failed")
            
            # Post reply using tweepy
            loop = asyncio.get_event_loop()
            
            def post_reply():
                try:
                    response = twitter_client.api.create_tweet(
                        text=reply_text,
                        in_reply_to_tweet_id=tweet_id
                    )
                    return response.data["id"] if response.data else None
                except Exception as e:
                    raise e
            
            reply_id = await loop.run_in_executor(None, post_reply)
            
            if reply_id:
                return ReplyResult(success=True, method_used="twitter_api", reply_id=str(reply_id))
            else:
                return ReplyResult(success=False, method_used="twitter_api", error_message="Failed to get reply ID")
                
        except Exception as e:
            error_msg = str(e)
            if "rate limit" in error_msg.lower() or "429" in error_msg:
                error_msg = "Twitter API rate limit exceeded"
            elif "403" in error_msg:
                error_msg = "Twitter API access forbidden"
            
            return ReplyResult(success=False, method_used="twitter_api", error_message=error_msg)
    
    async def _send_via_puppeteer(self, tweet_id: str, reply_text: str) -> ReplyResult:
        """Send reply via Puppeteer browser automation (fallback)"""
        # For now, return not implemented
        # This would require additional setup with Puppeteer/Playwright
        return ReplyResult(
            success=False, 
            method_used="puppeteer", 
            error_message="Puppeteer method not implemented yet"
        )
    
    def validate_reply_text(self, text: str) -> tuple[bool, str]:
        """Validate reply text"""
        if not text or not text.strip():
            return False, "Reply text cannot be empty"
        
        if len(text) > 280:
            return False, f"Reply text too long ({len(text)} characters, max 280)"
        
        return True, "Valid"
    
    def get_reply_preview(self, tweet_id: str, reply_text: str, target_username: str = "") -> str:
        """Generate a preview of how the reply will look"""
        preview = f"Replying to @{target_username if target_username else 'user'}\n"
        preview += f"Tweet ID: {tweet_id}\n"
        preview += f"Reply: {reply_text}\n"
        preview += f"Characters: {len(reply_text)}/280"
        return preview


# Global service instance
manual_reply_service = ManualReplyService()