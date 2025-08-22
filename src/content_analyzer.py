#!/usr/bin/env python3
"""
Twitter Auto Bot - AI Content Analyzer

Intelligently analyzes and filters tweets for relevance to AI, no-code, tools, and technical content
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from openai import OpenAI

from .config import settings
from .logger import logger
from .rapidapi_client import ScrapedTweet


@dataclass
class ContentAnalysis:
    """Results of AI content analysis for a tweet"""
    tweet_id: str
    relevance_score: float  # 0-100% relevance to target topics
    categories: List[str]   # e.g., ["AI News", "Tools", "LLM"]
    is_relevant: bool       # True if passes relevance threshold
    value_add_potential: float  # 0-100% potential for adding value
    reasoning: str          # Why this tweet was scored this way
    content_type: str       # News, Tutorial, Tool Review, Discussion, etc.
    skip_reason: Optional[str]  # If filtered out, why?


class ContentAnalyzer:
    """AI-powered content analyzer for intelligent tweet curation"""
    
    def __init__(self, relevance_threshold: float = 20.0):
        self.api_key = settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        self.client = OpenAI(api_key=self.api_key)
        self.model = "gpt-4o-mini"
        self.relevance_threshold = relevance_threshold
        
        # Define target categories for relevance scoring
        self.target_categories = [
            "AI News", "Machine Learning", "LLM", "GPT", "OpenAI",
            "No-Code Tools", "Automation", "API Tools", "Developer Tools",
            "Tech News", "Startup Tools", "Productivity", "AI Research",
            "Data Science", "Programming", "Software Development"
        ]
    
    async def analyze_tweets(self, tweets: List[ScrapedTweet]) -> List[ContentAnalysis]:
        """
        Analyze multiple tweets for content relevance
        
        Args:
            tweets: List of ScrapedTweet objects to analyze
            
        Returns:
            List of ContentAnalysis results
        """
        logger.info(f"Analyzing {len(tweets)} tweets for content relevance")
        
        analyses = []
        for i, tweet in enumerate(tweets):
            try:
                logger.info(f"Analyzing tweet {i+1}/{len(tweets)}: {tweet.tweet_id}")
                analysis = await self.analyze_single_tweet(tweet)
                analyses.append(analysis)
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Failed to analyze tweet {tweet.tweet_id}: {e}")
                # Create default analysis for failed tweets
                analyses.append(ContentAnalysis(
                    tweet_id=tweet.tweet_id,
                    relevance_score=0.0,
                    categories=[],
                    is_relevant=False,
                    value_add_potential=0.0,
                    reasoning="Analysis failed due to error",
                    content_type="Unknown",
                    skip_reason=f"Analysis error: {str(e)}"
                ))
        
        relevant_count = sum(1 for a in analyses if a.is_relevant)
        logger.info(f"Content analysis complete: {relevant_count}/{len(analyses)} tweets deemed relevant")
        
        return analyses
    
    async def analyze_single_tweet(self, tweet: ScrapedTweet) -> ContentAnalysis:
        """
        Analyze a single tweet for content relevance
        
        Args:
            tweet: ScrapedTweet object to analyze
            
        Returns:
            ContentAnalysis result
        """
        
        # Quick filters for obviously irrelevant content
        if self._quick_filter_check(tweet):
            return ContentAnalysis(
                tweet_id=tweet.tweet_id,
                relevance_score=0.0,
                categories=[],
                is_relevant=False,
                value_add_potential=0.0,
                reasoning="Filtered out by quick check",
                content_type="Filtered",
                skip_reason="Quick filter: personal/non-tech content"
            )
        
        # Use AI to analyze content
        try:
            analysis_prompt = self._create_analysis_prompt(tweet)
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": analysis_prompt}],
                    temperature=0.3,
                    max_tokens=300
                )
            )
            
            result_text = response.choices[0].message.content.strip()
            analysis = self._parse_analysis_result(tweet.tweet_id, result_text)
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error in AI analysis for tweet {tweet.tweet_id}: {e}")
            return ContentAnalysis(
                tweet_id=tweet.tweet_id,
                relevance_score=0.0,
                categories=[],
                is_relevant=False,
                value_add_potential=0.0,
                reasoning="AI analysis failed",
                content_type="Error",
                skip_reason=f"AI analysis error: {str(e)}"
            )
    
    def _quick_filter_check(self, tweet: ScrapedTweet) -> bool:
        """
        Quick filter to catch obviously irrelevant content
        
        Returns:
            True if should be filtered out (irrelevant)
        """
        text_lower = tweet.text.lower()
        
        # Comprehensive blacklist for obviously irrelevant content
        irrelevant_keywords = [
            # Nature/Travel/Lifestyle
            'sunset', 'sunrise', 'lake', 'beach', 'vacation', 'holiday', 'travel',
            'beautiful', 'gorgeous', 'stunning', 'breathtaking', 'amazing view',
            'nature', 'landscape', 'scenery', 'mountains', 'ocean', 'forest',
            'weather', 'sunny', 'cloudy', 'rainy', 'snowy', 'windy',
            
            # Personal Life
            'family', 'kids', 'children', 'baby', 'wedding', 'anniversary',
            'birthday', 'graduation', 'date night', 'dinner', 'lunch', 'breakfast',
            'cooking', 'recipe', 'food', 'restaurant', 'coffee', 'wine', 'beer',
            'workout', 'gym', 'exercise', 'running', 'yoga', 'meditation',
            
            # Entertainment/Sports
            'movie', 'film', 'tv show', 'netflix', 'youtube', 'podcast',
            'music', 'concert', 'album', 'song', 'artist', 'band',
            'game', 'gaming', 'xbox', 'playstation', 'nintendo', 'twitch',
            'sports', 'football', 'basketball', 'baseball', 'soccer', 'tennis',
            'olympics', 'championship', 'tournament', 'match', 'score',
            
            # Shopping/Fashion
            'shopping', 'sale', 'discount', 'fashion', 'style', 'outfit',
            'clothes', 'shoes', 'jewelry', 'makeup', 'beauty', 'skincare',
            
            # Social/Political (unless tech-related)
            'politics', 'election', 'vote', 'government', 'president', 'congress',
            'republican', 'democrat', 'liberal', 'conservative',
            
            # Generic social media
            'follow me', 'follow back', 'like and share', 'retweet if',
            'good morning', 'good night', 'gm ', 'gn ', 'how are you',
            'just woke up', 'going to bed', 'miss you', 'love you',
            'thinking of', 'prayers for', 'rip ', 'rest in peace'
        ]
        
        # Check for blacklisted keywords
        if any(keyword in text_lower for keyword in irrelevant_keywords):
            return True
        
        # Filter out retweets of random content unless they contain tech keywords
        tech_keywords = [
            'ai', 'ml', 'llm', 'gpt', 'claude', 'openai', 'anthropic',
            'tool', 'api', 'code', 'tech', 'data', 'automation', 'software',
            'algorithm', 'model', 'neural', 'machine learning', 'deep learning',
            'python', 'javascript', 'programming', 'developer', 'engineering',
            'startup', 'saas', 'platform', 'framework', 'library', 'database',
            'cloud', 'aws', 'azure', 'google cloud', 'kubernetes', 'docker',
            'blockchain', 'crypto', 'web3', 'nft', 'defi', 'smart contract',
            'no-code', 'low-code', 'automation', 'workflow', 'integration',
            'productivity', 'crm', 'analytics', 'dashboard', 'metrics'
        ]
        
        if tweet.is_retweet and not any(keyword in text_lower for keyword in tech_keywords):
            return True
        
        # Filter out very short tweets that are likely not substantial
        if len(tweet.text.strip()) < 30:  # Increased from 20 to 30
            return True
        
        # Filter out tweets that are just links without context
        words = tweet.text.split()
        if len(words) < 5 and any(word.startswith(('http', 'www.')) for word in words):
            return True
        
        # Filter out tweets that are mostly hashtags
        hashtag_ratio = len([word for word in words if word.startswith('#')]) / len(words) if words else 0
        if hashtag_ratio > 0.4:  # More than 40% hashtags
            return True
        
        return False
    
    def _create_analysis_prompt(self, tweet: ScrapedTweet) -> str:
        """Create AI prompt for content analysis"""
        
        return f"""
You are an EXTREMELY STRICT AI content curator for a technical Twitter account focused ONLY on AI, no-code tools, developer tools, and programming content.

Your job is to REJECT 90% of tweets and only approve content that is DIRECTLY relevant to technical professionals.

TWEET TO ANALYZE:
Author: @{tweet.author_username} ({tweet.author_display_name})
Text: {tweet.text}
Hashtags: {', '.join(tweet.hashtags) if tweet.hashtags else 'None'}
Engagement: {tweet.like_count} likes, {tweet.retweet_count} retweets, {tweet.reply_count} replies

ONLY APPROVE TWEETS ABOUT:
- AI/ML research, news, tools, tutorials
- LLM developments (GPT, Claude, Llama, etc.)
- Programming languages, frameworks, libraries
- Developer tools, APIs, SDKs
- No-code/low-code platforms and workflows
- Software engineering practices
- Tech startup tools and SaaS platforms
- Data science, analytics, databases
- Cloud computing, DevOps, infrastructure
- Automation, productivity tools for developers

IMMEDIATELY REJECT (Score 0-20):
- Personal life, family, travel, food, entertainment
- Nature photos, sunsets, landscapes, weather
- Sports, movies, music, gaming (unless dev-related)
- Politics, social issues (unless tech policy)
- Shopping, fashion, lifestyle content
- Generic motivational quotes
- Simple greetings or social pleasantries
- Pure marketing without technical substance

SCORING GUIDELINES:
- 90-100: Revolutionary AI/tech breakthrough, must-know developer tool
- 80-89: Important technical news, useful programming tutorial
- 70-79: Relevant but not urgent technical content
- 60-69: Tangentially tech-related but questionable value
- 0-59: Not relevant to technical audience

BE EXTREMELY STRICT. When in doubt, REJECT the tweet.

RESPOND IN THIS EXACT JSON FORMAT:
{{
    "relevance_score": 15,
    "categories": [],
    "value_add_potential": 10,
    "content_type": "Personal",
    "reasoning": "This is about a sunset at Lake George - completely irrelevant to AI/tech professionals. Pure lifestyle content with zero technical value."
}}

Remember: Your audience is busy developers and AI professionals. Only show them content that saves time or teaches something valuable.
"""
    
    def _parse_analysis_result(self, tweet_id: str, result_text: str) -> ContentAnalysis:
        """Parse AI analysis result into ContentAnalysis object"""
        
        try:
            # Try to extract JSON from the response
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = result_text[json_start:json_end]
                result = json.loads(json_str)
                
                relevance_score = float(result.get('relevance_score', 0))
                categories = result.get('categories', [])
                value_add_potential = float(result.get('value_add_potential', 0))
                content_type = result.get('content_type', 'Unknown')
                reasoning = result.get('reasoning', 'No reasoning provided')
                
                # Determine if relevant based on threshold
                is_relevant = relevance_score >= self.relevance_threshold
                skip_reason = None if is_relevant else f"Below relevance threshold ({relevance_score}% < {self.relevance_threshold}%)"
                
                return ContentAnalysis(
                    tweet_id=tweet_id,
                    relevance_score=relevance_score,
                    categories=categories,
                    is_relevant=is_relevant,
                    value_add_potential=value_add_potential,
                    reasoning=reasoning,
                    content_type=content_type,
                    skip_reason=skip_reason
                )
            else:
                raise ValueError("No valid JSON found in response")
                
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse AI analysis result: {e}")
            logger.debug(f"Raw result: {result_text}")
            
            # Return default low-relevance analysis
            return ContentAnalysis(
                tweet_id=tweet_id,
                relevance_score=0.0,
                categories=[],
                is_relevant=False,
                value_add_potential=0.0,
                reasoning="Failed to parse AI analysis",
                content_type="Unknown",
                skip_reason="Analysis parsing failed"
            )
    
    def filter_relevant_tweets(self, tweets: List[ScrapedTweet], analyses: List[ContentAnalysis]) -> List[ScrapedTweet]:
        """
        Filter tweets to only include relevant ones based on analysis
        
        Args:
            tweets: Original list of tweets
            analyses: Corresponding ContentAnalysis results
            
        Returns:
            Filtered list of relevant tweets
        """
        relevant_tweets = []
        
        for tweet, analysis in zip(tweets, analyses):
            if analysis.is_relevant:
                relevant_tweets.append(tweet)
                logger.info(f"✅ Tweet {tweet.tweet_id} passed filter: {analysis.relevance_score}% relevant, categories: {analysis.categories}")
            else:
                logger.info(f"❌ Tweet {tweet.tweet_id} filtered out: {analysis.skip_reason}")
        
        return relevant_tweets
    
    def get_filtering_stats(self, analyses: List[ContentAnalysis]) -> Dict[str, Any]:
        """Get statistics about the filtering results"""
        
        total = len(analyses)
        relevant = sum(1 for a in analyses if a.is_relevant)
        filtered_out = total - relevant
        
        # Category breakdown
        category_counts = {}
        for analysis in analyses:
            if analysis.is_relevant:
                for category in analysis.categories:
                    category_counts[category] = category_counts.get(category, 0) + 1
        
        # Average scores
        avg_relevance = sum(a.relevance_score for a in analyses) / total if total > 0 else 0
        avg_value_add = sum(a.value_add_potential for a in analyses if a.is_relevant) / relevant if relevant > 0 else 0
        
        return {
            "total_tweets": total,
            "relevant_tweets": relevant,
            "filtered_out": filtered_out,
            "relevance_rate": (relevant / total * 100) if total > 0 else 0,
            "average_relevance_score": round(avg_relevance, 1),
            "average_value_add_potential": round(avg_value_add, 1),
            "category_breakdown": category_counts,
            "threshold_used": self.relevance_threshold
        }


# Global instance
content_analyzer = ContentAnalyzer()