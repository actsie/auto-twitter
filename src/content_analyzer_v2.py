#!/usr/bin/env python3
"""
Twitter Auto Bot - Bulletproof Content Analyzer V2

Implements paranoid-mode filtering with comprehensive logging, rate limiting,
and fail-safe defaults to ensure only high-quality tech content passes through.
"""

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse
import logging
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from .config import settings
from .logger import logger
from .rapidapi_client import ScrapedTweet

# Global counters for telemetry
class FilteringMetrics:
    def __init__(self):
        self.total_processed = 0
        self.quick_rejects = 0
        self.ai_rejects = 0 
        self.approvals = 0
        self.parse_errors = 0
        self.timeouts = 0
        self.per_author_blocks = 0
        self.hourly_blocks = 0
        self.last_reset = time.time()
        
    def reset_hourly(self):
        """Reset hourly counters"""
        now = time.time()
        if now - self.last_reset > 3600:  # 1 hour
            self.last_reset = now
            return True
        return False
    
    def get_approval_rate(self) -> float:
        """Get current approval rate as percentage"""
        if self.total_processed == 0:
            return 0.0
        return (self.approvals / self.total_processed) * 100

metrics = FilteringMetrics()

# Pydantic schema for AI response validation
class AIFilterResponse(BaseModel):
    relevance: float = Field(ge=0, le=100, description="Relevance score 0-100")
    approved: bool = Field(description="Whether tweet is approved")
    categories: List[str] = Field(description="Content categories")
    reason: str = Field(max_length=80, description="Short explanation")

@dataclass
class FilterDecision:
    """Complete filtering decision with telemetry"""
    tweet_id: str
    stage_quick: str  # 'pass' | 'reject'
    quick_reason: str
    stage_ai: str     # 'pass' | 'reject' | 'skipped'
    ai_score: Optional[float]
    ai_reason: str
    final: str        # 'approved' | 'rejected'
    categories: List[str]
    processing_time_ms: int
    created_at: datetime

class BulletproofContentAnalyzer:
    """Production-ready content analyzer with fail-safe defaults"""
    
    def __init__(self):
        self.api_key = settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"
        
        # Filtering configuration 
        self.relevance_threshold = settings.relevance_threshold
        self.max_approvals_per_hour = settings.max_approvals_per_hour
        self.max_per_author_6h = settings.max_per_author_6h
        
        # Rate limiting tracking
        self.hourly_approvals = 0
        self.last_hour_reset = time.time()
        self.author_approvals = {}  # author -> [timestamps]
        
        # Compile regex patterns for performance
        self.url_re = re.compile(r'https?://\S+')
        self.mention_re = re.compile(r'@\w+')
        self.hashtag_re = re.compile(r'#\w+')
        self.emoji_re = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000027BF\U0001f900-\U0001f9ff\U0001f600-\U0001f64f]')
        
        # Comprehensive blacklist with word boundaries (refined for fewer false positives)
        blacklist_keywords = [
            # Nature/Travel/Lifestyle (specific phrases)
            'sunset', 'sunrise', 'beach vacation', 'holiday trip', 'travel blog',
            'gorgeous view', 'stunning sunset', 'breathtaking landscape',
            'nature photography', 'scenic route', 'mountain hiking', 'ocean waves',
            'sunny weather', 'rainy day mood', 'snowy morning', 'windy afternoon',
            
            # Personal Life (specific contexts)
            'family dinner', 'kids birthday', 'baby photos', 'wedding day',
            'anniversary celebration', 'graduation party', 'date night outfit',
            'cooking dinner', 'favorite recipe', 'restaurant review', 'morning coffee',
            'wine tasting', 'beer garden', 'workout routine', 'gym session',
            'yoga class', 'meditation time',
            
            # Entertainment/Sports (non-tech contexts)
            'movie night', 'netflix binge', 'youtube video', 'music concert',
            'favorite song', 'new album', 'gaming session', 'xbox game',
            'playstation exclusive', 'sports game', 'football match', 
            'basketball season', 'tennis tournament',
            
            # Shopping/Fashion  
            'shopping spree', 'fashion week', 'outfit of the day', 'new shoes',
            'makeup tutorial', 'skincare routine',
            
            # Generic social media (exact phrases)
            'follow me', 'follow back', 'like and share', 'retweet if',
            'good morning everyone', 'good night twitter', 'how are you',
            'just woke up', 'going to bed', 'miss you all', 'love you guys',
            'thinking of you', 'prayers for', 'rest in peace'
        ]
        
        self.blacklist_re = re.compile(
            r'\b(' + '|'.join(map(re.escape, blacklist_keywords)) + r')\b', 
            re.IGNORECASE
        )
        
        # Tech hints for positive filtering
        tech_keywords = [
            'ai', 'ml', 'llm', 'gpt', 'claude', 'openai', 'anthropic', 'model',
            'prompt', 'agent', 'copilot', 'cursor', 'sdk', 'api', 'cli', 'repo',
            'pull request', 'pr', 'a/b test', 'ab test', 'no-code', 'low-code',
            'dev', 'developer', 'framework', 'library', 'fastapi', 'supabase',
            'tweepy', 'vector', 'embedding', 'inference', 'tool', 'code', 'tech',
            'data', 'automation', 'software', 'algorithm', 'neural', 'machine learning',
            'deep learning', 'python', 'javascript', 'programming', 'engineering',
            'startup', 'saas', 'platform', 'database', 'cloud', 'aws', 'azure',
            'google cloud', 'kubernetes', 'docker', 'blockchain', 'crypto', 'web3',
            'productivity', 'crm', 'analytics', 'dashboard', 'metrics', 'devtools'
        ]
        
        self.tech_hints_re = re.compile(
            r'\b(' + '|'.join(map(re.escape, tech_keywords)) + r')\b',
            re.IGNORECASE
        )
        
        logger.info(f"BulletproofContentAnalyzer initialized: threshold={self.relevance_threshold}%, feature_filter_v2={settings.feature_filter_v2}")

    def normalize_text(self, text: str) -> str:
        """
        Normalize text following exact pipeline:
        strip URLs → mentions → emojis → collapse whitespace → lower
        """
        if not text:
            return ""
        
        # Step 1: Strip URLs
        text = self.url_re.sub("", text)
        
        # Step 2: Strip mentions  
        text = self.mention_re.sub("", text)
        
        # Step 3: Strip emojis
        text = self.emoji_re.sub("", text)
        
        # Step 4: Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Step 5: Lower case and strip
        return text.lower().strip()

    def compute_hashtag_ratio(self, raw_text: str) -> float:
        """Compute hashtag ratio on RAW text before normalization"""
        if not raw_text:
            return 0.0
            
        total_tokens = len(raw_text.split()) or 1
        hashtags = len(self.hashtag_re.findall(raw_text))
        return hashtags / total_tokens

    def is_retweet(self, raw_text: str) -> bool:
        """Detect retweets with proper whitespace/case handling"""
        return raw_text.strip().lower().startswith("rt ")

    def is_quote_tweet(self, tweet: ScrapedTweet) -> bool:
        """Detect quote tweets (basic implementation)"""
        # This is a simplified check - in real implementation you'd check Twitter API entities
        return "QT" in tweet.text or any("twitter.com" in url for url in tweet.media_urls or [])

    def has_tech_hints(self, normalized_text: str) -> bool:
        """Check if normalized text contains tech keywords"""
        return bool(self.tech_hints_re.search(normalized_text))

    def quick_filter(self, tweet: ScrapedTweet) -> Tuple[bool, str]:
        """
        Quick filter with reject-by-default logic
        Returns: (should_reject, reason)
        """
        raw_text = tweet.text or ""
        
        # Basic length check
        if len(raw_text.strip()) < 30:
            return True, "short"
        
        # Compute hashtag ratio on raw text
        hashtag_ratio = self.compute_hashtag_ratio(raw_text)
        if hashtag_ratio > 0.4:
            return True, "hashtag_spam"
        
        # Normalize text
        normalized = self.normalize_text(raw_text)
        if len(normalized) < 15:  # Even after normalization, must have substance
            return True, "no_substance"
        
        # Check blacklist
        if self.blacklist_re.search(normalized):
            return True, "blacklist_keyword"
        
        # Check for tech hints
        has_tech = self.has_tech_hints(normalized)
        
        # Retweet handling
        if self.is_retweet(raw_text) and not has_tech:
            return True, "retweet_no_tech"
        
        # Quote tweet handling
        if self.is_quote_tweet(tweet):
            # For quotes, we'd need to analyze both outer and quoted text
            # Simplified: require tech hints in the outer text
            if not has_tech:
                return True, "quote_no_tech"
        
        # Reject if no tech hints at all
        if not has_tech:
            return True, "no_tech_hints"
        
        return False, ""

    def _check_rate_limits(self, tweet: ScrapedTweet) -> Tuple[bool, str]:
        """Check if tweet would exceed rate limits"""
        now = time.time()
        
        # Reset hourly counter if needed
        if now - self.last_hour_reset > 3600:
            self.hourly_approvals = 0
            self.last_hour_reset = now
            
        # Check hourly limit
        if self.hourly_approvals >= self.max_approvals_per_hour:
            return True, "hourly_limit"
        
        # Check per-author limit (last 6 hours)
        author = tweet.author_username.lower()
        six_hours_ago = now - (6 * 3600)
        
        # Clean old timestamps
        if author in self.author_approvals:
            self.author_approvals[author] = [
                ts for ts in self.author_approvals[author] if ts > six_hours_ago
            ]
            
            # Check limit
            if len(self.author_approvals[author]) >= self.max_per_author_6h:
                return True, "per_author_limit"
        
        return False, ""

    async def ai_filter(self, tweet: ScrapedTweet) -> Tuple[bool, float, List[str], str]:
        """
        AI filter in paranoid mode with JSON schema validation
        Returns: (approved, relevance_score, categories, reason)
        """
        try:
            # Create strict analysis prompt
            prompt = f"""You are an EXTREMELY STRICT technical content curator.

APPROVE RATE: <10% of all tweets. Reject anything questionable.

TWEET:
Author: @{tweet.author_username}
Text: {tweet.text}
Likes: {tweet.like_count}, RTs: {tweet.retweet_count}

ONLY APPROVE if tweet is:
- Substantial AI/ML research, tools, tutorials with concrete examples
- Specific programming techniques, frameworks, code samples
- Developer tools with actual functionality described
- Technical deep-dives with implementation details
- No-code platforms with real workflow examples

IMMEDIATELY REJECT:
- Generic hype ("AI will change everything")
- Vague announcements without substance
- Personal opinions without technical details
- Lifestyle, entertainment, non-tech content
- Simple links without explanation

Be EXTREMELY strict. When uncertain, REJECT.

Respond ONLY with valid JSON:
{{
  "relevance": 0-100,
  "approved": true/false, 
  "categories": ["AI News","Programming","DevTools","Research","Other"],
  "reason": "specific reason in ≤80 chars"
}}"""

            # Make AI API call with JSON mode
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    top_p=None,  # Avoid surprises
                    max_tokens=200
                )
            )
            
            raw_content = response.choices[0].message.content.strip()
            
            # Parse and validate with Pydantic
            try:
                data = json.loads(raw_content)
                validated = AIFilterResponse(**data)
                
                # Extract values with type safety
                relevance = max(0.0, min(100.0, float(validated.relevance)))
                approved = bool(validated.approved)
                categories = validated.categories or []
                reason = validated.reason or "no reason"
                
                # Code-enforced threshold (don't trust model)
                threshold_passed = relevance >= self.relevance_threshold
                final_approved = approved and threshold_passed
                
                if not final_approved and approved:
                    reason = f"below_threshold({relevance}%<{self.relevance_threshold}%)"
                
                return final_approved, relevance, categories, reason
                
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"AI response validation failed for {tweet.tweet_id}: {e}")
                logger.debug(f"Raw AI response: {raw_content}")
                metrics.parse_errors += 1
                return False, 0.0, [], f"parse_error:{e.__class__.__name__}"
                
        except asyncio.TimeoutError:
            logger.warning(f"AI filter timeout for tweet {tweet.tweet_id}")
            metrics.timeouts += 1
            return False, 0.0, [], "timeout"
            
        except Exception as e:
            logger.error(f"AI filter error for tweet {tweet.tweet_id}: {e}")
            return False, 0.0, [], f"error:{e.__class__.__name__}"

    async def analyze_tweet(self, tweet: ScrapedTweet) -> FilterDecision:
        """
        Complete tweet analysis with comprehensive logging
        """
        start_time = time.time()
        metrics.total_processed += 1
        
        # Stage 1: Quick filter
        should_reject, quick_reason = self.quick_filter(tweet)
        
        if should_reject:
            metrics.quick_rejects += 1
            processing_time = int((time.time() - start_time) * 1000)
            
            decision = FilterDecision(
                tweet_id=tweet.tweet_id,
                stage_quick='reject',
                quick_reason=quick_reason,
                stage_ai='skipped',
                ai_score=None,
                ai_reason='',
                final='rejected',
                categories=[],
                processing_time_ms=processing_time,
                created_at=datetime.now()
            )
            
            logger.info(f"❌ {tweet.tweet_id} quick_reject:{quick_reason}")
            return decision
        
        # Stage 2: Rate limiting check
        rate_limited, rate_reason = self._check_rate_limits(tweet)
        if rate_limited:
            if rate_reason == "hourly_limit":
                metrics.hourly_blocks += 1
            else:
                metrics.per_author_blocks += 1
                
            processing_time = int((time.time() - start_time) * 1000)
            
            decision = FilterDecision(
                tweet_id=tweet.tweet_id,
                stage_quick='pass',
                quick_reason='',
                stage_ai='reject',
                ai_score=None,
                ai_reason=rate_reason,
                final='rejected',
                categories=[],
                processing_time_ms=processing_time,
                created_at=datetime.now()
            )
            
            logger.info(f"🚫 {tweet.tweet_id} rate_limit:{rate_reason}")
            return decision
        
        # Stage 3: AI analysis
        approved, ai_score, categories, ai_reason = await self.ai_filter(tweet)
        processing_time = int((time.time() - start_time) * 1000)
        
        if approved:
            metrics.approvals += 1
            self.hourly_approvals += 1
            
            # Track per-author approvals
            author = tweet.author_username.lower()
            if author not in self.author_approvals:
                self.author_approvals[author] = []
            self.author_approvals[author].append(time.time())
            
            logger.info(f"✅ {tweet.tweet_id} approved:{ai_score}% {categories}")
        else:
            metrics.ai_rejects += 1
            logger.info(f"❌ {tweet.tweet_id} ai_reject:{ai_score}% {ai_reason}")
        
        return FilterDecision(
            tweet_id=tweet.tweet_id,
            stage_quick='pass',
            quick_reason='',
            stage_ai='pass' if approved else 'reject',
            ai_score=ai_score,
            ai_reason=ai_reason,
            final='approved' if approved else 'rejected',
            categories=categories,
            processing_time_ms=processing_time,
            created_at=datetime.now()
        )

    async def analyze_tweets(self, tweets: List[ScrapedTweet]) -> List[FilterDecision]:
        """Analyze multiple tweets with comprehensive telemetry"""
        logger.info(f"🔍 Analyzing {len(tweets)} tweets with bulletproof filter V2")
        
        decisions = []
        for i, tweet in enumerate(tweets):
            try:
                decision = await self.analyze_tweet(tweet)
                decisions.append(decision)
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)
                
                # Log progress every 10 tweets
                if (i + 1) % 10 == 0:
                    approved_so_far = sum(1 for d in decisions if d.final == 'approved')
                    logger.info(f"Progress: {i+1}/{len(tweets)}, approved: {approved_so_far}")
                
            except Exception as e:
                logger.error(f"Error analyzing tweet {tweet.tweet_id}: {e}")
                # Create error decision
                decisions.append(FilterDecision(
                    tweet_id=tweet.tweet_id,
                    stage_quick='error',
                    quick_reason=str(e),
                    stage_ai='skipped',
                    ai_score=None,
                    ai_reason='',
                    final='rejected',
                    categories=[],
                    processing_time_ms=0,
                    created_at=datetime.now()
                ))
        
        # Final telemetry
        approved_count = sum(1 for d in decisions if d.final == 'approved')
        approval_rate = (approved_count / len(decisions)) * 100 if decisions else 0
        
        logger.info(f"🎯 Filtering complete: {approved_count}/{len(decisions)} approved ({approval_rate:.1f}%)")
        
        # Check for alerts
        self._check_telemetry_alerts(approval_rate)
        
        return decisions

    def _check_telemetry_alerts(self, approval_rate: float):
        """Check for approval rate drift and parse errors"""
        target_rate = settings.approval_rate_target
        
        # Alert on approval rate drift (only if enough samples)
        if metrics.total_processed >= 100:
            if approval_rate < 3.0:
                logger.warning(f"🚨 ALERT: Approval rate too low: {approval_rate:.1f}% (target: {target_rate}%)")
            elif approval_rate > 20.0:
                logger.warning(f"🚨 ALERT: Approval rate too high: {approval_rate:.1f}% (target: {target_rate}%)")
        
        # Alert on parse error rate
        if metrics.total_processed > 0:
            parse_error_rate = (metrics.parse_errors / metrics.total_processed) * 100
            if parse_error_rate > 5.0:
                logger.warning(f"🚨 ALERT: Parse error rate too high: {parse_error_rate:.1f}%")

    def get_filtering_stats(self) -> Dict[str, Any]:
        """Get comprehensive filtering statistics"""
        return {
            "total_processed": metrics.total_processed,
            "quick_rejects": metrics.quick_rejects,
            "ai_rejects": metrics.ai_rejects,
            "approvals": metrics.approvals,
            "parse_errors": metrics.parse_errors,
            "timeouts": metrics.timeouts,
            "per_author_blocks": metrics.per_author_blocks,
            "hourly_blocks": metrics.hourly_blocks,
            "approval_rate": metrics.get_approval_rate(),
            "threshold_used": self.relevance_threshold,
            "feature_enabled": settings.feature_filter_v2
        }

# Global instance
bulletproof_analyzer = BulletproofContentAnalyzer()