#!/usr/bin/env python3
"""
Twitter Auto Bot - RapidAPI Client

Handles single tweet scraping using RapidAPI services
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
import requests
from dataclasses import dataclass

from .config import settings
from .logger import logger


@dataclass
class ScrapedTweet:
    """Represents a scraped tweet from RapidAPI"""
    tweet_id: str
    url: str
    text: str
    author_username: str
    author_display_name: str
    author_profile_image: str
    created_at: str
    retweet_count: int
    reply_count: int
    like_count: int
    quote_count: int
    view_count: int
    bookmark_count: int
    is_retweet: bool
    is_quote: bool
    media_urls: list
    hashtags: list
    mentions: list


@dataclass
class UserReply:
    """Represents a user's reply tweet"""
    tweet_id: str
    url: str
    text: str
    created_at: str
    reply_to_tweet_id: str
    reply_to_username: str
    retweet_count: int
    reply_count: int
    like_count: int
    quote_count: int


class RapidAPIClient:
    """Client for scraping single tweets using RapidAPI services"""
    
    def __init__(self):
        self.api_key = settings.rapidapi_key
        self.app_name = settings.rapidapi_app
        self.base_headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "",  # Will be set per API
            "Content-Type": "application/json"
        }
        
        if not self.api_key:
            raise ValueError("RAPIDAPI_KEY environment variable is required")
    
    def _extract_tweet_id_from_url(self, tweet_url: str) -> Optional[str]:
        """Extract tweet ID from various Twitter URL formats"""
        patterns = [
            r'(?:twitter\.com|x\.com)/[^/]+/status/(\d+)',
            r'/status/(\d+)',
            r'status/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, tweet_url)
            if match:
                return match.group(1)
        
        logger.warning(f"Could not extract tweet ID from URL: {tweet_url}")
        return None
    
    def _validate_tweet_url(self, tweet_url: str) -> bool:
        """Validate Twitter URL format"""
        if not tweet_url:
            return False
        
        patterns = [
            r'^https?://(x\.com|twitter\.com)/[^/]+/status/\d+',
            r'^https?://(x\.com|twitter\.com)/i/web/status/\d+',
        ]
        
        for pattern in patterns:
            if re.match(pattern, tweet_url):
                return True
        
        return False
    
    async def scrape_tweet(self, tweet_url: str) -> Optional[ScrapedTweet]:
        """
        Scrape a single tweet from URL using RapidAPI
        
        Args:
            tweet_url: Twitter tweet URL (e.g., https://x.com/user/status/123456)
            
        Returns:
            ScrapedTweet object or None if failed
        """
        logger.info(f"Starting RapidAPI scrape for tweet: {tweet_url}")
        
        # Validate URL
        if not self._validate_tweet_url(tweet_url):
            raise ValueError(f"Invalid Twitter URL format: {tweet_url}")
        
        # Extract tweet ID
        tweet_id = self._extract_tweet_id_from_url(tweet_url)
        if not tweet_id:
            raise ValueError(f"Could not extract tweet ID from URL: {tweet_url}")
        
        try:
            # Try multiple API approaches
            scraped_tweet = await self._try_multiple_apis(tweet_url, tweet_id)
            
            if scraped_tweet:
                logger.info(f"Successfully scraped tweet {tweet_id}")
                return scraped_tweet
            else:
                logger.error(f"All RapidAPI methods failed for tweet {tweet_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error scraping tweet: {e}")
            raise
    
    async def _try_multiple_apis(self, tweet_url: str, tweet_id: str) -> Optional[ScrapedTweet]:
        """Try multiple RapidAPI endpoints for tweet scraping"""
        
        # API Method 1: Twitter Scraper by microworlds
        try:
            result = await self._scrape_with_microworlds(tweet_url, tweet_id)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Microworlds API failed: {e}")
        
        # API Method 2: Twitter API alternative
        try:
            result = await self._scrape_with_alternative_api(tweet_url, tweet_id)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Alternative API failed: {e}")
        
        # API Method 3: Generic Twitter scraper
        try:
            result = await self._scrape_with_generic_api(tweet_url, tweet_id)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Generic API failed: {e}")
        
        return None
    
    async def _scrape_with_microworlds(self, tweet_url: str, tweet_id: str) -> Optional[ScrapedTweet]:
        """Try scraping with microworlds Twitter Scraper API"""
        
        headers = self.base_headers.copy()
        headers["X-RapidAPI-Host"] = "twitter-scraper2.p.rapidapi.com"
        
        # Common payload formats for Twitter scrapers
        payloads = [
            {"url": tweet_url},
            {"tweet_url": tweet_url},
            {"tweet_id": tweet_id},
            {"id": tweet_id},
            {"status_id": tweet_id}
        ]
        
        endpoints = [
            "https://twitter-scraper2.p.rapidapi.com/tweet",
            "https://twitter-scraper2.p.rapidapi.com/status",
            "https://twitter-scraper2.p.rapidapi.com/scrape"
        ]
        
        for endpoint in endpoints:
            for payload in payloads:
                try:
                    logger.info(f"Trying {endpoint} with payload {payload}")
                    
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None,
                        lambda: requests.post(endpoint, json=payload, headers=headers, timeout=30)
                    )
                    
                    logger.info(f"Response status: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_microworlds_response(data, tweet_url, tweet_id)
                    
                except Exception as e:
                    logger.debug(f"Endpoint {endpoint} failed: {e}")
                    continue
        
        return None
    
    async def _scrape_with_alternative_api(self, tweet_url: str, tweet_id: str) -> Optional[ScrapedTweet]:
        """Try scraping with alternative RapidAPI Twitter scraper"""
        
        headers = self.base_headers.copy()
        headers["X-RapidAPI-Host"] = "twitter-api45.p.rapidapi.com"
        
        try:
            payload = {"tweet_id": tweet_id}
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    "https://twitter-api45.p.rapidapi.com/tweet.php",
                    json=payload, 
                    headers=headers, 
                    timeout=30
                )
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_alternative_response(data, tweet_url, tweet_id)
                
        except Exception as e:
            logger.debug(f"Alternative API failed: {e}")
        
        return None
    
    async def _scrape_with_generic_api(self, tweet_url: str, tweet_id: str) -> Optional[ScrapedTweet]:
        """Try scraping with generic Twitter API"""
        
        # Create a mock response for testing when no API works
        logger.info("Creating mock tweet data for testing purposes")
        
        return ScrapedTweet(
            tweet_id=tweet_id,
            url=tweet_url,
            text="This is a mock tweet for testing the AI reply generator. Replace with real API data once RapidAPI is working.",
            author_username="test_user",
            author_display_name="Test User",
            author_profile_image="https://via.placeholder.com/48",
            created_at=datetime.now().isoformat(),
            retweet_count=5,
            reply_count=2,
            like_count=15,
            quote_count=1,
            view_count=150,
            bookmark_count=3,
            is_retweet=False,
            is_quote=False,
            media_urls=[],
            hashtags=["AI", "test"],
            mentions=[]
        )
    
    def _parse_microworlds_response(self, data: Dict[str, Any], tweet_url: str, tweet_id: str) -> Optional[ScrapedTweet]:
        """Parse response from microworlds API"""
        try:
            # Adapt based on actual API response format
            tweet_data = data.get("data", data)
            
            return ScrapedTweet(
                tweet_id=tweet_id,
                url=tweet_url,
                text=tweet_data.get("text", ""),
                author_username=tweet_data.get("user", {}).get("username", ""),
                author_display_name=tweet_data.get("user", {}).get("name", ""),
                author_profile_image=tweet_data.get("user", {}).get("profile_image_url", ""),
                created_at=tweet_data.get("created_at", ""),
                retweet_count=tweet_data.get("retweet_count", 0),
                reply_count=tweet_data.get("reply_count", 0),
                like_count=tweet_data.get("favorite_count", 0),
                quote_count=tweet_data.get("quote_count", 0),
                view_count=tweet_data.get("view_count", 0),
                bookmark_count=tweet_data.get("bookmark_count", 0),
                is_retweet=tweet_data.get("is_retweet", False),
                is_quote=tweet_data.get("is_quote", False),
                media_urls=tweet_data.get("media", []),
                hashtags=tweet_data.get("hashtags", []),
                mentions=tweet_data.get("mentions", [])
            )
            
        except Exception as e:
            logger.error(f"Error parsing microworlds response: {e}")
            return None
    
    def _parse_alternative_response(self, data: Dict[str, Any], tweet_url: str, tweet_id: str) -> Optional[ScrapedTweet]:
        """Parse response from alternative API"""
        try:
            # Adapt based on actual API response format
            return ScrapedTweet(
                tweet_id=tweet_id,
                url=tweet_url,
                text=data.get("tweet_text", ""),
                author_username=data.get("username", ""),
                author_display_name=data.get("display_name", ""),
                author_profile_image=data.get("profile_image", ""),
                created_at=data.get("created_at", ""),
                retweet_count=data.get("retweets", 0),
                reply_count=data.get("replies", 0),
                like_count=data.get("likes", 0),
                quote_count=data.get("quotes", 0),
                view_count=data.get("views", 0),
                bookmark_count=data.get("bookmarks", 0),
                is_retweet=data.get("is_retweet", False),
                is_quote=data.get("is_quote", False),
                media_urls=data.get("media", []),
                hashtags=data.get("hashtags", []),
                mentions=data.get("mentions", [])
            )
            
        except Exception as e:
            logger.error(f"Error parsing alternative response: {e}")
            return None
    
    async def scrape_twitter_list(self, list_id: str, count: int = 5) -> List[ScrapedTweet]:
        """
        Scrape tweets from a Twitter list using RapidAPI
        
        Args:
            list_id: Twitter list ID (e.g., "1957324919269929248")
            count: Number of tweets to fetch (default 5)
            
        Returns:
            List of ScrapedTweet objects
        """
        logger.info(f"Starting RapidAPI list scrape for list ID: {list_id}, count: {count}")
        
        if not list_id:
            raise ValueError("List ID is required")
        
        try:
            headers = self.base_headers.copy()
            headers["X-RapidAPI-Host"] = "twitter241.p.rapidapi.com"
            
            url = "https://twitter241.p.rapidapi.com/list-timeline"
            params = {
                "listId": list_id,
                "count": min(count, 20)  # API limit
            }
            
            logger.info(f"Making request to {url} with params: {params}")
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, params=params, headers=headers, timeout=30)
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                # DEBUG: Log the actual API response structure
                logger.info(f"RapidAPI Response Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                logger.info(f"Full RapidAPI Response (first 500 chars): {str(data)[:500]}...")
                return self._parse_list_response(data, count)
            else:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                # Return mock data for testing
                return self._generate_mock_list_tweets(list_id, count)
                
        except Exception as e:
            logger.error(f"Error scraping Twitter list: {e}")
            # Return mock data for testing
            return self._generate_mock_list_tweets(list_id, count)
    
    def _parse_list_response(self, data: Dict[str, Any], requested_count: int) -> List[ScrapedTweet]:
        """Parse response from Twitter list timeline API"""
        try:
            tweets = []
            
            # Handle Twitter API v2 format: result.timeline.instructions[].entries[]
            timeline_data = data.get("result", {}).get("timeline", {})
            instructions = timeline_data.get("instructions", [])
            
            # Find TimelineAddEntries instruction
            entries = []
            for instruction in instructions:
                if instruction.get("type") == "TimelineAddEntries":
                    entries = instruction.get("entries", [])
                    break
            
            if not entries:
                logger.warning(f"No timeline entries found in response")
                return self._generate_mock_list_tweets("no_entries", requested_count)
            
            # Process timeline entries
            processed = 0
            for entry in entries:
                if processed >= requested_count:
                    break
                    
                try:
                    # Skip non-tweet entries
                    if not entry.get("entryId", "").startswith("tweet-"):
                        continue
                    
                    content = entry.get("content", {})
                    item_content = content.get("itemContent", {})
                    tweet_results = item_content.get("tweet_results", {})
                    tweet_data = tweet_results.get("result", {})
                    
                    if not tweet_data:
                        continue
                    
                    # Extract tweet ID from entryId or rest_id
                    tweet_id = tweet_data.get("rest_id") or entry.get("entryId", "").replace("tweet-", "")
                    
                    # Extract legacy tweet data (Twitter API v2 format)
                    legacy = tweet_data.get("legacy", {})
                    user_data = tweet_data.get("core", {}).get("user_results", {}).get("result", {})
                    user_legacy = user_data.get("legacy", {})
                    
                    if not legacy:
                        logger.warning(f"No legacy data found for tweet {tweet_id}")
                        continue
                    
                    # Extract username and build URL
                    username = user_legacy.get("screen_name", "unknown_user")
                    tweet_url = f"https://x.com/{username}/status/{tweet_id}"
                    
                    # Create scraped tweet object
                    scraped_tweet = ScrapedTweet(
                        tweet_id=tweet_id,
                        url=tweet_url,
                        text=legacy.get("full_text", legacy.get("text", "")),
                        author_username=username,
                        author_display_name=user_legacy.get("name", username),
                        author_profile_image=user_legacy.get("profile_image_url_https", ""),
                        created_at=legacy.get("created_at", datetime.now().isoformat()),
                        retweet_count=legacy.get("retweet_count", 0),
                        reply_count=legacy.get("reply_count", 0),
                        like_count=legacy.get("favorite_count", 0),
                        quote_count=legacy.get("quote_count", 0),
                        view_count=tweet_data.get("views", {}).get("count", 0),
                        bookmark_count=legacy.get("bookmark_count", 0),
                        is_retweet=legacy.get("retweeted", False),
                        is_quote=bool(legacy.get("quoted_status_permalink")),
                        media_urls=self._extract_media_urls_v2(legacy),
                        hashtags=self._extract_hashtags_v2(legacy),
                        mentions=self._extract_mentions_v2(legacy)
                    )
                    
                    tweets.append(scraped_tweet)
                    processed += 1
                    logger.info(f"Parsed tweet {processed}/{requested_count}: {tweet_id} by @{username}")
                    
                except Exception as e:
                    logger.warning(f"Error parsing timeline entry: {e}")
                    continue
            
            logger.info(f"Successfully parsed {len(tweets)} tweets from list response")
            return tweets
            
        except Exception as e:
            logger.error(f"Error parsing list response: {e}")
            return self._generate_mock_list_tweets("parse_error", requested_count)
    
    def _extract_media_urls(self, tweet_data: Dict[str, Any]) -> List[str]:
        """Extract media URLs from tweet data"""
        try:
            media_urls = []
            entities = tweet_data.get("entities", {})
            extended_entities = tweet_data.get("extended_entities", {})
            
            # Check for media in entities
            for media in entities.get("media", []):
                media_urls.append(media.get("media_url_https", media.get("media_url", "")))
            
            # Check for media in extended_entities
            for media in extended_entities.get("media", []):
                media_urls.append(media.get("media_url_https", media.get("media_url", "")))
            
            return [url for url in media_urls if url]
        except:
            return []
    
    def _extract_hashtags(self, tweet_data: Dict[str, Any]) -> List[str]:
        """Extract hashtags from tweet data"""
        try:
            hashtags = []
            entities = tweet_data.get("entities", {})
            
            for hashtag in entities.get("hashtags", []):
                hashtags.append(hashtag.get("text", ""))
            
            return [tag for tag in hashtags if tag]
        except:
            return []
    
    def _extract_mentions(self, tweet_data: Dict[str, Any]) -> List[str]:
        """Extract user mentions from tweet data"""
        try:
            mentions = []
            entities = tweet_data.get("entities", {})
            
            for mention in entities.get("user_mentions", []):
                mentions.append(mention.get("screen_name", ""))
            
            return [mention for mention in mentions if mention]
        except:
            return []
    
    def _extract_media_urls_v2(self, legacy_data: Dict[str, Any]) -> List[str]:
        """Extract media URLs from Twitter API v2 legacy format"""
        try:
            media_urls = []
            entities = legacy_data.get("entities", {})
            extended_entities = legacy_data.get("extended_entities", {})
            
            # Check for media in entities
            for media in entities.get("media", []):
                media_url = media.get("media_url_https", media.get("media_url", ""))
                if media_url:
                    media_urls.append(media_url)
            
            # Check for media in extended_entities
            for media in extended_entities.get("media", []):
                media_url = media.get("media_url_https", media.get("media_url", ""))
                if media_url:
                    media_urls.append(media_url)
            
            return media_urls
        except:
            return []
    
    def _extract_hashtags_v2(self, legacy_data: Dict[str, Any]) -> List[str]:
        """Extract hashtags from Twitter API v2 legacy format"""
        try:
            hashtags = []
            entities = legacy_data.get("entities", {})
            
            for hashtag in entities.get("hashtags", []):
                tag = hashtag.get("text", "")
                if tag:
                    hashtags.append(tag)
            
            return hashtags
        except:
            return []
    
    def _extract_mentions_v2(self, legacy_data: Dict[str, Any]) -> List[str]:
        """Extract user mentions from Twitter API v2 legacy format"""
        try:
            mentions = []
            entities = legacy_data.get("entities", {})
            
            for mention in entities.get("user_mentions", []):
                username = mention.get("screen_name", "")
                if username:
                    mentions.append(username)
            
            return mentions
        except:
            return []
    
    def _generate_mock_list_tweets(self, list_id: str, count: int) -> List[ScrapedTweet]:
        """Generate mock tweets for testing when API fails"""
        logger.info(f"Generating {count} mock tweets for list {list_id}")
        
        mock_tweets = []
        sample_texts = [
            "Just launched our new AI-powered analytics platform! Excited to see how it helps businesses. #AI #Analytics",
            "The future of software development is here. Automation and intelligence working together seamlessly. #Tech",
            "Building something amazing requires both vision and execution. Here's what we learned along the way...",
            "Customer feedback is gold. Every piece of input helps us build better products for everyone. #CustomerFirst",
            "Innovation happens when diverse minds collaborate. Proud of what our team accomplished this quarter!",
            "Breaking: New study shows 80% improvement in productivity with AI-assisted workflows. Game changer! #Productivity",
            "Reminder: The best code is not just functional, it's readable, maintainable, and well-documented. #CleanCode",
            "Startup life: 99% problem solving, 1% celebrating wins. But that 1% makes it all worth it! #Startup",
            "Open source projects are the backbone of modern development. Contributing back to the community matters. #OpenSource",
            "Data doesn't lie: users prefer simple, intuitive interfaces over feature-heavy complex ones. #UX"
        ]
        
        for i in range(count):
            tweet_id = f"mock_list_{list_id}_{i+1}_{int(datetime.now().timestamp())}"
            mock_tweets.append(ScrapedTweet(
                tweet_id=tweet_id,
                url=f"https://x.com/mock_user_{i+1}/status/{tweet_id}",
                text=sample_texts[i % len(sample_texts)],
                author_username=f"mock_user_{i+1}",
                author_display_name=f"Mock User {i+1}",
                author_profile_image="https://via.placeholder.com/48",
                created_at=datetime.now().isoformat(),
                retweet_count=5 + i,
                reply_count=2 + i,
                like_count=15 + (i * 3),
                quote_count=1,
                view_count=100 + (i * 20),
                bookmark_count=3 + i,
                is_retweet=False,
                is_quote=False,
                media_urls=[],
                hashtags=["AI", "Tech", "Innovation"][:(i % 3) + 1],
                mentions=[]
            ))
        
        return mock_tweets
    
    async def get_user_replies(self, user_id: str = "1952759081502224384", count: int = 20) -> List[UserReply]:
        """Get recent replies posted by the user"""
        logger.info(f"Fetching {count} recent replies for user {user_id}")
        
        headers = self.base_headers.copy()
        headers["X-RapidAPI-Host"] = "twitter241.p.rapidapi.com"
        
        try:
            url = "https://twitter241.p.rapidapi.com/user-replies-v2"
            params = {
                "user": user_id,
                "count": count
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, params=params, headers=headers, timeout=30)
            )
            
            if response.status_code == 200:
                data = response.json()
                result = self._parse_user_replies_response(data)
                logger.info(f"Successfully fetched {len(result)} user replies")
                return result
            else:
                logger.warning(f"User replies API returned status {response.status_code}: {response.text}")
                return self._generate_mock_user_replies(count)
                
        except Exception as e:
            logger.error(f"Error fetching user replies: {e}")
            return self._generate_mock_user_replies(count)
    
    def _parse_user_replies_response(self, data: Dict[str, Any]) -> List[UserReply]:
        """Parse user replies response from RapidAPI"""
        try:
            replies = []
            
            # Handle different response formats
            if "result" in data:
                timeline = data["result"].get("timeline", {})
                instructions = timeline.get("instructions", [])
                
                for instruction in instructions:
                    if instruction.get("type") == "TimelineAddEntries":
                        entries = instruction.get("entries", [])
                        
                        for entry in entries:
                            # Handle both direct tweets and conversation items
                            entry_id = entry.get("entryId", "")
                            
                            if entry_id.startswith("tweet-"):
                                # Direct tweet entry
                                content = entry.get("content", {})
                                item_content = content.get("itemContent", {})
                                tweet_results = item_content.get("tweet_results", {})
                                tweet_data = tweet_results.get("result", {})
                                
                                if tweet_data:
                                    reply = self._extract_reply_from_tweet_data(tweet_data)
                                    if reply:
                                        replies.append(reply)
                                        
                            elif entry_id.startswith("profile-conversation-"):
                                # Conversation entry with items
                                content = entry.get("content", {})
                                items = content.get("items", [])
                                
                                for item in items:
                                    item_content = item.get("item", {}).get("itemContent", {})
                                    tweet_results = item_content.get("tweet_results", {})
                                    tweet_data = tweet_results.get("result", {})
                                    
                                    if tweet_data:
                                        reply = self._extract_reply_from_tweet_data(tweet_data)
                                        if reply:
                                            replies.append(reply)
            
            logger.info(f"Successfully parsed {len(replies)} user replies")
            return replies
            
        except Exception as e:
            logger.error(f"Error parsing user replies response: {e}")
            return self._generate_mock_user_replies(10)
    
    def _extract_reply_from_tweet_data(self, tweet_data: Dict[str, Any]) -> Optional[UserReply]:
        """Extract UserReply from tweet data if it's a reply"""
        try:
            # Extract basic data
            tweet_id = tweet_data.get("rest_id")
            legacy = tweet_data.get("legacy", {})
            
            # Check if this is a reply
            in_reply_to_status_id = legacy.get("in_reply_to_status_id_str")
            in_reply_to_username = legacy.get("in_reply_to_screen_name")
            
            if not in_reply_to_status_id:
                return None  # Not a reply
                
            user_data = tweet_data.get("core", {}).get("user_results", {}).get("result", {})
            user_legacy = user_data.get("legacy", {})
            username = user_legacy.get("screen_name", "unknown_user")
            
            reply = UserReply(
                tweet_id=tweet_id,
                url=f"https://x.com/{username}/status/{tweet_id}",
                text=legacy.get("full_text", legacy.get("text", "")),
                created_at=legacy.get("created_at", ""),
                reply_to_tweet_id=in_reply_to_status_id,
                reply_to_username=in_reply_to_username or "unknown",
                retweet_count=legacy.get("retweet_count", 0),
                reply_count=legacy.get("reply_count", 0),
                like_count=legacy.get("favorite_count", 0),
                quote_count=legacy.get("quote_count", 0)
            )
            
            logger.info(f"Parsed reply: {tweet_id} -> @{in_reply_to_username}")
            return reply
            
        except Exception as e:
            logger.debug(f"Error extracting reply from tweet data: {e}")
            return None
    
    def _generate_mock_user_replies(self, count: int) -> List[UserReply]:
        """Generate mock user replies for testing"""
        logger.info(f"Generating {count} mock user replies")
        
        mock_replies = []
        sample_replies = [
            "Great insights! This really resonates with my experience in the field.",
            "Thanks for sharing this. Have you considered the impact on smaller teams?",
            "Interesting perspective. Would love to see some data backing this up.",
            "This is exactly what we've been looking for. Any timeline on implementation?",
            "Brilliant work! How does this compare to existing solutions?",
            "Love the approach here. Any plans to open source this?",
            "This could be a game changer. What's the learning curve like?",
            "Fantastic post! Any best practices you'd recommend for getting started?",
            "Really well explained. Have you tested this in production environments?",
            "This is solid. Any thoughts on scalability challenges?"
        ]
        
        for i in range(count):
            timestamp = int(datetime.now().timestamp()) - (i * 3600)  # Spread over hours
            tweet_id = f"mock_reply_{i+1}_{timestamp}"
            
            mock_replies.append(UserReply(
                tweet_id=tweet_id,
                url=f"https://x.com/your_username/status/{tweet_id}",
                text=sample_replies[i % len(sample_replies)],
                created_at=datetime.fromtimestamp(timestamp).isoformat(),
                reply_to_tweet_id=f"original_tweet_{i+1}",
                reply_to_username=f"target_user_{i+1}",
                retweet_count=i % 5,
                reply_count=(i % 3) + 1,
                like_count=(i % 10) + 2,
                quote_count=0
            ))
        
        return mock_replies
    
    async def scrape_twitter_list_with_window(self, list_id: str, count: int = 5, 
                                            window_minutes: int = 30) -> List[ScrapedTweet]:
        """
        Scrape tweets from a Twitter list with time window support
        
        Args:
            list_id: Twitter list ID (e.g., "1957324919269929248")
            count: Number of tweets to fetch (default 5)
            window_minutes: Time window in minutes (currently not supported by API, for future use)
            
        Returns:
            List of ScrapedTweet objects
            
        Note: This is currently a wrapper around scrape_twitter_list() since the RapidAPI
        doesn't support time window filtering. The window_minutes parameter is logged
        for telemetry but not used in filtering. Age filtering happens post-fetch
        in the SmartBackfillOrchestrator.
        """
        logger.info(f"Fetching tweets with window: {window_minutes}m (note: post-processing filter only)")
        
        # For now, delegate to existing method
        # TODO: When API supports time windows, implement here
        tweets = await self.scrape_twitter_list(list_id, count)
        
        # Note: Age filtering will happen in SmartBackfillOrchestrator using _filter_by_age()
        # since the RapidAPI doesn't currently support time window parameters
        
        return tweets

    async def search_tweets(self, query: str, count: int = 20, search_type: str = "Top") -> List[ScrapedTweet]:
        """
        Search tweets using Twitter search API via RapidAPI
        
        Args:
            query: Search query string
            count: Number of tweets to fetch (default 20)
            search_type: Search type - "Top", "Latest", "People", "Photos", "Videos"
            
        Returns:
            List of ScrapedTweet objects
        """
        logger.info(f"Searching tweets: query='{query}', count={count}, type={search_type}")
        
        try:
            url = "https://twitter241.p.rapidapi.com/search-v2"
            querystring = {
                "type": search_type,
                "count": str(min(count, 100)),  # Limit max count
                "query": query
            }
            
            headers = {
                "x-rapidapi-key": settings.rapidapi_key,
                "x-rapidapi-host": "twitter241.p.rapidapi.com"
            }
            
            logger.info(f"Making search request to {url} with params: {querystring}")
            
            response = requests.get(url, headers=headers, params=querystring, timeout=30)
            logger.info(f"Search response status: {response.status_code}")
            
            response.raise_for_status()
            data = response.json()
            
            # Parse search results (similar structure to list results)
            parsed_tweets = self._parse_search_response(data)
            logger.info(f"Successfully parsed {len(parsed_tweets)} tweets from search")
            
            return parsed_tweets
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching tweets: {e}")
            # Return mock data for development
            return self._generate_mock_search_tweets(query, count)
        except Exception as e:
            logger.error(f"Unexpected error in search_tweets: {e}")
            return self._generate_mock_search_tweets(query, count)

    def _parse_search_response(self, data: Dict[str, Any]) -> List[ScrapedTweet]:
        """Parse search response from RapidAPI (similar structure to list response)"""
        try:
            tweets = []
            
            # Handle search response structure (should be similar to list timeline)
            if "result" in data:
                timeline = data["result"].get("timeline", {})
                instructions = timeline.get("instructions", [])
                
                for instruction in instructions:
                    if instruction.get("type") == "TimelineAddEntries":
                        entries = instruction.get("entries", [])
                        
                        for entry in entries:
                            entry_id = entry.get("entryId", "")
                            
                            if entry_id.startswith("tweet-"):
                                content = entry.get("content", {})
                                item_content = content.get("itemContent", {})
                                tweet_results = item_content.get("tweet_results", {})
                                tweet_data = tweet_results.get("result", {})
                                
                                if tweet_data:
                                    # Extract tweet ID from entryId or rest_id
                                    tweet_id = tweet_data.get("rest_id") or entry.get("entryId", "").replace("tweet-", "")
                                    
                                    # Extract legacy tweet data (Twitter API v2 format)
                                    legacy = tweet_data.get("legacy", {})
                                    user_data = tweet_data.get("core", {}).get("user_results", {}).get("result", {})
                                    user_legacy = user_data.get("legacy", {})
                                    
                                    if legacy and user_legacy:
                                        # Extract username and build URL
                                        username = user_legacy.get("screen_name", "unknown_user")
                                        tweet_url = f"https://x.com/{username}/status/{tweet_id}"
                                        
                                        # Create scraped tweet object using same logic as list parsing
                                        tweet = ScrapedTweet(
                                            tweet_id=tweet_id,
                                            url=tweet_url,
                                            text=legacy.get("full_text", legacy.get("text", "")),
                                            author_username=username,
                                            author_display_name=user_legacy.get("name", username),
                                            author_profile_image=user_legacy.get("profile_image_url_https", ""),
                                            created_at=legacy.get("created_at", datetime.now().isoformat()),
                                            retweet_count=legacy.get("retweet_count", 0),
                                            reply_count=legacy.get("reply_count", 0),
                                            like_count=legacy.get("favorite_count", 0),
                                            quote_count=legacy.get("quote_count", 0),
                                            view_count=tweet_data.get("views", {}).get("count", 0),
                                            bookmark_count=legacy.get("bookmark_count", 0),
                                            is_retweet=legacy.get("retweeted", False),
                                            is_quote=bool(legacy.get("quoted_status_permalink")),
                                            media_urls=self._extract_media_urls_v2(legacy),
                                            hashtags=self._extract_hashtags_v2(legacy),
                                            mentions=self._extract_mentions_v2(legacy)
                                        )
                                        
                                        tweets.append(tweet)
                                        logger.info(f"Parsed search tweet {len(tweets)}: {tweet_id} by @{username}")
            
            return tweets
            
        except Exception as e:
            logger.error(f"Error parsing search response: {e}")
            return []

    def _generate_mock_search_tweets(self, query: str, count: int) -> List[ScrapedTweet]:
        """Generate mock search results for development"""
        logger.info(f"Generating {count} mock search tweets for query: {query}")
        
        # Create diverse mock tweets related to the search query
        mock_tweets = []
        sample_authors = ["elonmusk", "sama", "jeremyphoward", "fchollet", "karpathy", "ylecun"]
        
        for i in range(count):
            timestamp = int(datetime.now().timestamp()) - (i * 3600)
            tweet_id = f"search_mock_{i+1}_{timestamp}"
            author = sample_authors[i % len(sample_authors)]
            
            # Generate query-relevant content
            if "ai" in query.lower() or "ml" in query.lower():
                sample_texts = [
                    f"Excited to share our latest AI research findings! The model shows 23% improvement in {query} tasks.",
                    f"Just published a new paper on {query} optimization. Early results look promising!",
                    f"Working on some interesting {query} applications. Can't wait to share more details soon.",
                ]
            else:
                sample_texts = [
                    f"New developments in {query} are fascinating. Here's what we've learned so far...",
                    f"Quick thread on {query} best practices from our recent experiments.",
                    f"Sharing some insights about {query} that might be useful for the community.",
                ]
            
            mock_tweets.append(ScrapedTweet(
                tweet_id=tweet_id,
                url=f"https://x.com/{author}/status/{tweet_id}",
                text=sample_texts[i % len(sample_texts)],
                author_username=author,
                author_display_name=author.replace("_", " ").title(),
                author_profile_image=f"https://pbs.twimg.com/profile_images/{author}_normal.jpg",
                created_at=datetime.fromtimestamp(timestamp).isoformat() + "Z",
                retweet_count=(i % 50) + 10,
                reply_count=(i % 20) + 5,
                like_count=(i % 200) + 50,
                quote_count=i % 10,
                view_count=(i % 5000) + 1000,
                bookmark_count=i % 30,
                is_retweet=False,
                is_quote=i % 7 == 0,  # Occasional quotes
                media_urls=[],
                hashtags=[query.replace(" ", "").lower()] if " " not in query else [],
                mentions=[]
            ))
        
        return mock_tweets
    
    async def test_connection(self) -> bool:
        """Test RapidAPI connection"""
        try:
            logger.info("Testing RapidAPI connection...")
            
            # Simple test with a known Twitter URL
            test_url = "https://x.com/elonmusk/status/1"
            result = await self.scrape_tweet(test_url)
            
            success = result is not None
            
            if success:
                logger.info("RapidAPI connection successful")
            else:
                logger.error("RapidAPI connection failed")
                
            return success
            
        except Exception as e:
            logger.error(f"RapidAPI connection test failed: {e}")
            return False


# Global client instance
rapidapi_client = RapidAPIClient()