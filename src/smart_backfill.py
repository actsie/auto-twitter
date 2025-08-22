#!/usr/bin/env python3
"""
Smart Backfill Orchestrator for V2 Bulletproof Filter
Provides production-ready backfill with guardrails and telemetry
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Set, Optional
from dataclasses import dataclass
from itertools import cycle

from .config import settings
from .logger import logger
from .rapidapi_client import ScrapedTweet
from .content_analyzer_v2 import bulletproof_analyzer


@dataclass
class BackfillResult:
    """Complete backfill result with telemetry"""
    approved_tweets: List[ScrapedTweet]
    stop_reason: str  # "target_met" | "max_total_fetch" | "low_approval_rate" | "max_attempts"
    total_analyzed: int
    attempts_made: int
    final_approval_rate: float
    lists_used: List[str]
    window_minutes_final: int


@dataclass
class AttemptLog:
    """Single attempt telemetry"""
    attempt: int
    fetched: int
    approved: int
    cum_fetched: int
    cum_approved: int
    approval_rate: float
    window_minutes: int
    list_used: str


class SmartBackfillOrchestrator:
    """Production-ready backfill orchestrator with comprehensive guardrails"""
    
    def __init__(self):
        # Load config
        self.max_attempts = settings.backfill_max_attempts
        self.max_multiplier = settings.backfill_max_multiplier
        self.start_window_min = settings.backfill_start_window_min
        self.max_window_min = settings.backfill_max_window_min
        self.min_approval_rate = settings.backfill_min_approval_rate
        self.batch_base = settings.backfill_batch_base
        
        # Telemetry
        self.attempt_logs: List[AttemptLog] = []
        
        logger.info(f"SmartBackfillOrchestrator initialized: max_attempts={self.max_attempts}, "
                   f"max_multiplier={self.max_multiplier}x, min_approval_rate={self.min_approval_rate}")

    def _calculate_batch_size(self, target_count: int, approved_count: int, total_analyzed: int, attempt: int) -> int:
        """Calculate smart batch size based on success rate"""
        if attempt == 1:
            # Start conservative but sufficient
            return max(self.batch_base, target_count * 2)
        
        # Calculate success rate from previous attempts
        success_rate = approved_count / total_analyzed if total_analyzed > 0 else 0.1
        needed_tweets = target_count - approved_count
        
        if success_rate > 0:
            # Estimate batch size with 1.5x buffer for variance
            estimated_batch = int(needed_tweets / success_rate * 1.5)
        else:
            # No approvals yet, try 3x multiplier
            estimated_batch = needed_tweets * 3
            
        # Apply bounds
        return max(self.batch_base, min(estimated_batch, target_count * 4))

    def _filter_by_age(self, tweets: List[ScrapedTweet], max_age_minutes: int) -> List[ScrapedTweet]:
        """Filter out tweets older than max_age_minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        
        filtered_tweets = []
        for tweet in tweets:
            try:
                # Parse tweet creation time (handle various formats)
                if isinstance(tweet.created_at, str):
                    # Try different datetime formats that Twitter might use
                    for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ', 
                               '%a %b %d %H:%M:%S %z %Y', '%Y-%m-%d %H:%M:%S']:
                        try:
                            tweet_time = datetime.strptime(tweet.created_at.replace('+0000', ''), fmt.replace(' %z', ''))
                            break
                        except ValueError:
                            continue
                    else:
                        # If no format matches, assume recent (don't filter out)
                        logger.debug(f"Could not parse tweet timestamp: {tweet.created_at}")
                        filtered_tweets.append(tweet)
                        continue
                elif isinstance(tweet.created_at, datetime):
                    tweet_time = tweet.created_at
                else:
                    # Unknown format, assume recent
                    filtered_tweets.append(tweet)
                    continue
                
                # Check if tweet is within age limit
                if tweet_time >= cutoff_time:
                    filtered_tweets.append(tweet)
                    
            except Exception as e:
                # If there's any error parsing, include the tweet (fail open)
                logger.debug(f"Error parsing tweet {tweet.tweet_id} timestamp: {e}")
                filtered_tweets.append(tweet)
                
        return filtered_tweets

    def _enforce_existing_caps(self, tweets: List[ScrapedTweet]) -> List[ScrapedTweet]:
        """Apply existing rate limit caps from bulletproof analyzer"""
        capped_tweets = []
        
        for tweet in tweets:
            # Use existing rate limiting logic
            is_rate_limited, rate_reason = bulletproof_analyzer._check_rate_limits(tweet)
            if not is_rate_limited:
                capped_tweets.append(tweet)
            else:
                logger.info(f"⚡ Rate limit applied: {tweet.tweet_id} blocked ({rate_reason})")
        
        return capped_tweets

    def _log_attempt(self, attempt: int, fetched: int, approved: int, cum_fetched: int, 
                    cum_approved: int, window_minutes: int, list_used: str):
        """Log attempt telemetry for monitoring and tuning"""
        approval_rate = (cum_approved / cum_fetched * 100) if cum_fetched > 0 else 0.0
        
        attempt_log = AttemptLog(
            attempt=attempt,
            fetched=fetched,
            approved=approved,
            cum_fetched=cum_fetched,
            cum_approved=cum_approved,
            approval_rate=approval_rate,
            window_minutes=window_minutes,
            list_used=list_used
        )
        
        self.attempt_logs.append(attempt_log)
        
        # Compact log line for monitoring
        logger.info(f"📊 Backfill attempt {attempt} | fetched {fetched} | approved {approved} | "
                   f"cum_fetched {cum_fetched} | cum_approved {cum_approved} | "
                   f"approval_rate {approval_rate:.1f}% | window {window_minutes}m | list {list_used}")

    async def find_relevant_tweets(self, list_id: str, target_count: int, 
                                  rapidapi_client, source_type: str = "list", 
                                  search_query: str = "", search_type: str = "Top") -> BackfillResult:
        """
        Find target_count relevant tweets using intelligent backfill with production guardrails
        
        Args:
            list_id: Twitter list ID (used for list and hybrid modes)
            target_count: Number of relevant tweets to find
            rapidapi_client: RapidAPI client instance
            source_type: "list", "search", or "hybrid" (default: "list")
            search_query: Search query for search and hybrid modes
            search_type: Search type for search API ("Top", "Latest", etc.)
        """
        source_desc = f"{source_type}"
        if source_type == "search":
            source_desc += f" query='{search_query}'"
        elif source_type == "hybrid":
            source_desc += f" list={list_id} + query='{search_query}'"
        else:
            source_desc += f" list={list_id}"
        
        logger.info(f"🎯 Starting smart backfill: target={target_count}, source={source_desc}")
        
        # Initialize tracking
        seen_ids: Set[str] = set()
        approved_tweets: List[ScrapedTweet] = []
        window_minutes = self.start_window_min
        
        # Track sources used for telemetry
        if source_type == "search":
            lists_used = [f"search:{search_query[:50]}"]
        elif source_type == "hybrid":
            lists_used = [f"hybrid:{list_id}+search:{search_query[:50]}"]
        else:
            lists_used = [list_id]
        
        # Main backfill loop
        for attempt in range(1, self.max_attempts + 1):
            # Calculate smart batch size
            batch_size = self._calculate_batch_size(
                target_count, len(approved_tweets), len(seen_ids), attempt
            )
            
            logger.info(f"🔄 Attempt {attempt}/{self.max_attempts}: fetching {batch_size} tweets "
                       f"(window: {window_minutes}m, need {target_count - len(approved_tweets)} more)")
            
            try:
                # Fetch tweets based on source type with hybrid priority (lists first)
                tweets = []
                
                if source_type == "list":
                    # List mode: fetch from list only
                    tweets = await rapidapi_client.scrape_twitter_list(list_id, batch_size)
                    if not tweets:
                        tweets = rapidapi_client._generate_mock_list_tweets(list_id, batch_size)
                        
                elif source_type == "search":
                    # Search mode: fetch from search only
                    if not search_query:
                        logger.error("Search query is required for search mode")
                        tweets = []
                    else:
                        tweets = await rapidapi_client.search_tweets(search_query, batch_size, search_type)
                        
                elif source_type == "hybrid":
                    # Hybrid mode: Trust-first strategy - lists first, then search fill
                    list_portion = max(1, batch_size // 2)  # At least half from trusted list
                    search_portion = batch_size - list_portion
                    
                    logger.info(f"🔀 Hybrid fetch: {list_portion} from list, {search_portion} from search")
                    
                    # Fetch from trusted list first
                    list_tweets = await rapidapi_client.scrape_twitter_list(list_id, list_portion)
                    if not list_tweets:
                        list_tweets = rapidapi_client._generate_mock_list_tweets(list_id, list_portion)
                    
                    # Fill remaining with search results
                    search_tweets = []
                    if search_query and search_portion > 0:
                        search_tweets = await rapidapi_client.search_tweets(search_query, search_portion, search_type)
                    
                    # Combine: list results first (trusted), then search results (discovery)
                    tweets = list_tweets + search_tweets
                    
                    logger.info(f"🔀 Hybrid result: {len(list_tweets)} from list + {len(search_tweets)} from search = {len(tweets)} total")
                
            except Exception as e:
                logger.error(f"Error fetching tweets in attempt {attempt}: {e}")
                tweets = []
            
            # Filter out already seen tweets
            new_tweets = [tweet for tweet in tweets if tweet.tweet_id not in seen_ids]
            seen_ids.update(tweet.tweet_id for tweet in new_tweets)
            
            # Apply age cutoff (prevent stale tweets when windows expand)
            fresh_tweets = self._filter_by_age(new_tweets, self.max_window_min)
            age_filtered_count = len(new_tweets) - len(fresh_tweets)
            if age_filtered_count > 0:
                logger.info(f"🕒 Age filter: removed {age_filtered_count} tweets older than {self.max_window_min}m")
            
            if not fresh_tweets:
                logger.warning(f"No fresh tweets found in attempt {attempt}")
                self._log_attempt(attempt, 0, 0, len(seen_ids), len(approved_tweets), window_minutes, list_id)
                continue
            
            # Apply bulletproof filtering (preserves all existing quality controls)
            logger.info(f"🔍 Analyzing {len(fresh_tweets)} fresh tweets with bulletproof filter")
            filtering_decisions = await bulletproof_analyzer.analyze_tweets(fresh_tweets)
            
            # Extract approved tweets
            approved_ids = {d.tweet_id for d in filtering_decisions if d.final == 'approved'}
            attempt_approved = [tweet for tweet in fresh_tweets if tweet.tweet_id in approved_ids]
            
            # Apply rate limit caps using existing logic
            capped_approved = self._enforce_existing_caps(attempt_approved)
            rate_limited_count = len(attempt_approved) - len(capped_approved)
            if rate_limited_count > 0:
                logger.info(f"⚡ Rate limiting: blocked {rate_limited_count} tweets")
            
            # Add to approved list
            approved_tweets.extend(capped_approved)
            
            # Log this attempt
            source_used = lists_used[0] if lists_used else "unknown"
            self._log_attempt(attempt, len(fresh_tweets), len(capped_approved), 
                            len(seen_ids), len(approved_tweets), window_minutes, source_used)
            
            # Check stop conditions
            if len(approved_tweets) >= target_count:
                logger.info(f"🎉 Target met! Found {len(approved_tweets)} approved tweets")
                return BackfillResult(
                    approved_tweets=approved_tweets[:target_count],
                    stop_reason="target_met",
                    total_analyzed=len(seen_ids),
                    attempts_made=attempt,
                    final_approval_rate=(len(approved_tweets) / len(seen_ids) * 100) if seen_ids else 0.0,
                    lists_used=lists_used,
                    window_minutes_final=window_minutes
                )
            
            if len(seen_ids) >= target_count * self.max_multiplier:
                logger.warning(f"🛑 Max total fetch limit reached: {len(seen_ids)} >= {target_count * self.max_multiplier}")
                return BackfillResult(
                    approved_tweets=approved_tweets,
                    stop_reason="max_total_fetch",
                    total_analyzed=len(seen_ids),
                    attempts_made=attempt,
                    final_approval_rate=(len(approved_tweets) / len(seen_ids) * 100) if seen_ids else 0.0,
                    lists_used=lists_used,
                    window_minutes_final=window_minutes
                )
            
            # Check approval rate (only if we have enough data)
            if len(seen_ids) > 50:
                current_approval_rate = len(approved_tweets) / len(seen_ids)
                if current_approval_rate < self.min_approval_rate:
                    logger.warning(f"🛑 Low approval rate: {current_approval_rate:.1%} < {self.min_approval_rate:.1%}")
                    return BackfillResult(
                        approved_tweets=approved_tweets,
                        stop_reason="low_approval_rate", 
                        total_analyzed=len(seen_ids),
                        attempts_made=attempt,
                        final_approval_rate=current_approval_rate * 100,
                        lists_used=lists_used,
                        window_minutes_final=window_minutes
                    )
            
            # Expand time window for next attempt
            window_minutes = min(self.max_window_min, window_minutes * 2)
            
            # Small delay between attempts to be respectful
            if attempt < self.max_attempts:
                await asyncio.sleep(0.5)
        
        # Max attempts reached
        logger.warning(f"🛑 Max attempts reached: {self.max_attempts}")
        return BackfillResult(
            approved_tweets=approved_tweets,
            stop_reason="max_attempts",
            total_analyzed=len(seen_ids),
            attempts_made=self.max_attempts,
            final_approval_rate=(len(approved_tweets) / len(seen_ids) * 100) if seen_ids else 0.0,
            lists_used=lists_used,
            window_minutes_final=window_minutes
        )

    def get_telemetry_summary(self) -> dict:
        """Get comprehensive telemetry for monitoring"""
        if not self.attempt_logs:
            return {}
            
        return {
            "attempts_made": len(self.attempt_logs),
            "total_fetched": self.attempt_logs[-1].cum_fetched,
            "total_approved": self.attempt_logs[-1].cum_approved,
            "final_approval_rate": self.attempt_logs[-1].approval_rate,
            "attempt_details": [
                {
                    "attempt": log.attempt,
                    "fetched": log.fetched,
                    "approved": log.approved,
                    "window_minutes": log.window_minutes
                }
                for log in self.attempt_logs
            ]
        }


# Global instance
smart_backfill = SmartBackfillOrchestrator()