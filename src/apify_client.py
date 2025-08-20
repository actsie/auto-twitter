#!/usr/bin/env python3
"""
Twitter Auto Bot - Apify Client

Handles Twitter list scraping using the Apify API
"""

import asyncio
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
import requests
from dataclasses import dataclass
import re
from dateutil import parser as date_parser

from .config import settings
from .logger import logger


@dataclass
class Tweet:
    """Represents a scraped tweet"""
    tweet_id: str
    url: str
    twitter_url: str
    text: str
    author_username: str
    author_display_name: str
    created_at: str
    retweet_count: int
    reply_count: int
    like_count: int
    quote_count: int
    bookmark_count: int
    is_retweet: bool
    is_quote: bool


class ApifyClient:
    """Client for interacting with Apify API to scrape Twitter lists"""
    
    def __init__(self):
        self.api_token = settings.apify_api_token
        self.user_id = settings.apify_user_id
        self.base_url = "https://api.apify.com/v2"
        
        if not self.api_token:
            raise ValueError("APIFY_API_TOKEN environment variable is required")
    
    def _validate_list_url(self, list_url: str) -> bool:
        """Validate Twitter list URL format"""
        if not list_url:
            return False
        
        # Twitter list URL patterns
        patterns = [
            r'^https?://(x\.com|twitter\.com)/i/lists/\d+',
            r'^https?://(x\.com|twitter\.com)/[^/]+/lists/[^/]+',
        ]
        
        for pattern in patterns:
            if re.match(pattern, list_url):
                return True
        
        return False
    
    async def scrape_twitter_list(self, list_url: str, max_items: int = 20) -> List[Tweet]:
        """
        Scrape tweets from a Twitter list URL using Apify
        
        Args:
            list_url: Twitter list URL (e.g., https://x.com/i/lists/1957324919269929248)
            max_items: Maximum number of tweets to scrape
            
        Returns:
            List of Tweet objects
        """
        logger.info(f"Starting Apify scrape for list: {list_url}")
        
        # Validate input
        if not self._validate_list_url(list_url):
            raise ValueError(f"Invalid Twitter list URL format: {list_url}")
        
        if max_items <= 0 or max_items > 1000:
            raise ValueError(f"max_items must be between 1 and 1000, got {max_items}")
        
        try:
            # Prepare the request payload
            payload = {
                "includeSearchTerms": False,
                "maxItems": max_items,
                "onlyImage": False,
                "onlyQuote": False,
                "onlyTwitterBlue": False,
                "onlyVerifiedUsers": False,
                "onlyVideo": False,
                "startUrls": [list_url]
            }
            
            # Make the API call
            response = await self._make_api_request(payload)
            
            # Parse response into Tweet objects
            tweets = self._parse_tweets(response)
            
            logger.info(f"Successfully scraped {len(tweets)} tweets from list")
            return tweets
            
        except Exception as e:
            logger.error(f"Error scraping Twitter list: {e}")
            raise
    
    async def _make_api_request(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Make the actual API request to Apify"""
        
        # Try a different approach - use a generic Twitter scraper that should work with your token
        actor_name = "apify/tweet-scraper"  # This is a basic Apify-owned actor that should be accessible
        url = f"{self.base_url}/acts/{actor_name}/run-sync-get-dataset-items"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_token}"
        }
        
        params = {
            "token": self.api_token
        }
        
        logger.info("Making Apify API request...")
        
        # Use requests in a thread to avoid blocking
        loop = asyncio.get_event_loop()
        
        def make_request():
            try:
                logger.info(f"Making request to: {url}")
                logger.info(f"Payload: {json.dumps(payload, indent=2)}")
                
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    params=params,
                    timeout=300  # 5 minute timeout
                )
                
                logger.info(f"Response status: {response.status_code}")
                logger.info(f"Response headers: {dict(response.headers)}")
                
                if response.status_code != 200:
                    logger.error(f"API returned status {response.status_code}: {response.text}")
                
                response.raise_for_status()
                result = response.json()
                logger.info(f"Response data type: {type(result)}, length: {len(result) if isinstance(result, (list, dict)) else 'N/A'}")
                
                return result
            except requests.exceptions.RequestException as e:
                logger.error(f"Apify API request failed: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"Error response: {e.response.text}")
                raise
        
        try:
            result = await loop.run_in_executor(None, make_request)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.error(f"Apify API call failed: {e}")
            raise
    
    def _parse_tweets(self, raw_tweets: List[Dict[str, Any]]) -> List[Tweet]:
        """Parse raw Apify response into Tweet objects"""
        tweets = []
        
        for raw_tweet in raw_tweets:
            try:
                # Skip retweets for now to focus on original content
                if raw_tweet.get("isRetweet", False):
                    continue
                
                # Extract author information safely
                author_username = self._extract_username_from_url(raw_tweet.get("url", ""))
                author_display_name = ""
                
                # Handle different author field formats
                author_data = raw_tweet.get("author", {})
                if isinstance(author_data, dict):
                    author_display_name = author_data.get("name", "") or author_data.get("displayName", "")
                elif isinstance(author_data, str):
                    author_display_name = author_data
                
                # Parse date safely
                created_at_str = raw_tweet.get("createdAt", raw_tweet.get("created_at", ""))
                
                # Extract tweet data with safe defaults and validation
                tweet = Tweet(
                    tweet_id=str(raw_tweet.get("id", "")),
                    url=raw_tweet.get("url", ""),
                    twitter_url=raw_tweet.get("twitterUrl", raw_tweet.get("url", "")),
                    text=raw_tweet.get("text", "").strip(),
                    author_username=author_username,
                    author_display_name=author_display_name,
                    created_at=created_at_str,  # Keep as string for now
                    retweet_count=int(raw_tweet.get("retweetCount", 0)),
                    reply_count=int(raw_tweet.get("replyCount", 0)),
                    like_count=int(raw_tweet.get("likeCount", 0)),
                    quote_count=int(raw_tweet.get("quoteCount", 0)),
                    bookmark_count=int(raw_tweet.get("bookmarkCount", 0)),
                    is_retweet=bool(raw_tweet.get("isRetweet", False)),
                    is_quote=bool(raw_tweet.get("isQuote", False))
                )
                
                # Only add tweets with valid data
                if tweet.tweet_id and tweet.text:
                    tweets.append(tweet)
                    
            except Exception as e:
                logger.warning(f"Error parsing tweet: {e}")
                continue
        
        return tweets
    
    def _parse_tweet_date(self, date_str: str) -> datetime:
        """Parse tweet date with multiple format support"""
        if not date_str:
            return datetime.now()
        
        try:
            # Try common Twitter date formats
            formats = [
                "%a %b %d %H:%M:%S %z %Y",  # "Mon Aug 18 06:23:01 +0000 2025"
                "%Y-%m-%dT%H:%M:%S.%fZ",    # "2025-08-18T06:23:01.000Z"
                "%Y-%m-%dT%H:%M:%SZ",       # "2025-08-18T06:23:01Z"
                "%Y-%m-%d %H:%M:%S",        # "2025-08-18 06:23:01"
                "%Y-%m-%d",                 # "2025-08-18"
            ]
            
            # First try direct parsing with dateutil (most flexible)
            try:
                return date_parser.parse(date_str)
            except:
                pass
            
            # Try manual formats
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except:
                    continue
            
            # If all else fails, try to extract ISO format
            iso_match = re.search(r'\d{4}-\d{2}-\d{2}', date_str)
            if iso_match:
                return datetime.strptime(iso_match.group(), "%Y-%m-%d")
            
            logger.warning(f"Could not parse date: {date_str}, using current time")
            return datetime.now()
            
        except Exception as e:
            logger.error(f"Error parsing date '{date_str}': {e}")
            return datetime.now()
    
    def _extract_username_from_url(self, url: str) -> str:
        """Extract username from Twitter URL"""
        try:
            # URL format: https://x.com/username/status/123456
            parts = url.split("/")
            if len(parts) >= 4 and ("x.com" in url or "twitter.com" in url):
                return parts[3]  # The username part
        except:
            pass
        return ""
    
    async def test_connection(self) -> bool:
        """Test the Apify API connection"""
        try:
            logger.info("Testing Apify API connection...")
            
            # Simple API test - just check if we can make a request
            url = f"{self.base_url}/key-value-stores"
            headers = {"Authorization": f"Bearer {self.api_token}"}
            
            loop = asyncio.get_event_loop()
            
            def test_request():
                response = requests.get(url, headers=headers, timeout=30)
                return response.status_code == 200
            
            success = await loop.run_in_executor(None, test_request)
            
            if success:
                logger.info("Apify API connection successful")
            else:
                logger.error("Apify API connection failed")
                
            return success
            
        except Exception as e:
            logger.error(f"Apify API test failed: {e}")
            return False


# Global client instance
apify_client = ApifyClient()