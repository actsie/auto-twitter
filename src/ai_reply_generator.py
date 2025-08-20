#!/usr/bin/env python3
"""
Twitter Auto Bot - AI Reply Generator

Generates intelligent reply suggestions using OpenAI GPT
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from openai import OpenAI

from .config import settings
from .logger import logger
from .rapidapi_client import ScrapedTweet


@dataclass
class ReplyOptions:
    """Configuration for reply generation"""
    reply_style: str = "engaging_casual"  # engaging_casual, informative_professional, supportive_friendly
    custom_tone: str = ""  # Custom tone/voice instructions (e.g., "witty and sarcastic", "technical expert")
    length: str = "medium"      # short, medium, long
    include_emoji: bool = True
    include_hashtags: bool = False
    max_replies: int = 5


@dataclass
class GeneratedReply:
    """Represents an AI-generated reply suggestion"""
    id: str
    text: str
    reply_style: str
    custom_tone: str
    character_count: int
    confidence_score: float
    reasoning: str
    suggested_improvements: List[str]


class AIReplyGenerator:
    """AI-powered reply generator using OpenAI GPT"""
    
    def __init__(self):
        self.api_key = settings.openai_api_key
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=self.api_key)
        self.model = "o4-mini"  # Fast reasoning model with enhanced contextual understanding
    
    async def generate_replies(self, tweet: ScrapedTweet, options: ReplyOptions = None, content_context=None) -> List[GeneratedReply]:
        """
        Generate multiple reply suggestions for a tweet
        
        Args:
            tweet: ScrapedTweet object containing tweet data
            options: ReplyOptions for customizing generation
            
        Returns:
            List of GeneratedReply objects
        """
        if options is None:
            options = ReplyOptions()
        
        logger.info(f"Generating {options.max_replies} AI replies for tweet {tweet.tweet_id}")
        
        try:
            # Create prompts for different reply styles
            prompts = self._create_diverse_prompts(tweet, options, content_context)
            
            # Generate replies using OpenAI
            replies = []
            for i, prompt in enumerate(prompts[:options.max_replies]):
                try:
                    reply = await self._generate_single_reply(prompt, tweet, options, i)
                    if reply:
                        replies.append(reply)
                except Exception as e:
                    logger.warning(f"Failed to generate reply {i+1}: {e}")
                    continue
            
            logger.info(f"Successfully generated {len(replies)} replies")
            return replies
            
        except Exception as e:
            logger.error(f"Error generating AI replies: {e}")
            return []
    
    def _create_diverse_prompts(self, tweet: ScrapedTweet, options: ReplyOptions, content_context=None) -> List[str]:
        """Create diverse prompts for different reply styles"""
        
        # Build content context information
        content_info = ""
        if content_context:
            content_info = f"""

Content Analysis:
- Relevance Score: {content_context.relevance_score}%
- Categories: {', '.join(content_context.categories)}
- Content Type: {content_context.content_type}
- Value-Add Potential: {content_context.value_add_potential}%
- AI Analysis: {content_context.reasoning}
"""

        base_context = f"""
Original Tweet:
Author: @{tweet.author_username} ({tweet.author_display_name})
Text: "{tweet.text}"
Engagement: {tweet.like_count} likes, {tweet.retweet_count} retweets, {tweet.reply_count} replies
Hashtags: {', '.join(tweet.hashtags) if tweet.hashtags else 'None'}
{content_info}"""
        
        prompts = []
        
        # Determine tone instructions based on reply_style and custom_tone
        tone_instructions = self._get_tone_instructions(options)
        
        # Prompt 1: Thoughtful engagement (enhanced with content context)
        context_guidance = ""
        if content_context and content_context.categories:
            context_guidance = f"""
- This tweet is about: {', '.join(content_context.categories)}
- Focus your reply on technical insights related to these topics
- Share practical knowledge or experience that others would find valuable
"""
        
        prompts.append(f"""
{base_context}

Generate a thoughtful, engaging reply that adds value to the conversation. The reply should:
- Be genuine and authentic
- Add meaningful insight or perspective specific to AI, tech tools, or development
- Encourage further discussion{context_guidance}
- Stay within 280 characters
{tone_instructions}
- {'Include relevant emojis' if options.include_emoji else 'No emojis'}
- {'Include relevant hashtags' if options.include_hashtags else 'No hashtags'}

Reply:""")
        
        # Prompt 2: Question-based engagement
        prompts.append(f"""
{base_context}

Generate a reply that asks a thoughtful question to drive engagement. The reply should:
- Ask an interesting question related to the topic
- Show genuine curiosity
- Encourage the author to respond
- Be conversational and friendly
- Stay within 280 characters
{tone_instructions}

Reply:""")
        
        # Prompt 3: Supportive response
        prompts.append(f"""
{base_context}

Generate a supportive, positive reply that:
- Shows appreciation for the content
- Offers encouragement or agreement
- Shares a brief related experience if relevant
- Maintains a positive tone
- Stay within 280 characters
{tone_instructions}

Reply:""")
        
        # Prompt 4: Informative addition
        prompts.append(f"""
{base_context}

Generate an informative reply that:
- Adds useful information or context
- Shares relevant insights or facts
- Provides additional resources if appropriate
- Maintains professional tone
- Stay within 280 characters
{tone_instructions}

Reply:""")
        
        # Prompt 5: Creative/witty response
        prompts.append(f"""
{base_context}

Generate a creative, engaging reply that:
- Shows personality and creativity
- Uses appropriate humor if suitable
- Makes a memorable impression
- Stays relevant to the topic
- Stay within 280 characters
{tone_instructions}

Reply:""")
        
        return prompts
    
    def _get_tone_instructions(self, options: ReplyOptions) -> str:
        """Generate tone instructions based on reply_style and custom_tone"""
        
        # If custom_only mode and custom tone provided, use ONLY custom tone
        if options.reply_style == "custom_only":
            if options.custom_tone and options.custom_tone.strip():
                return f"- Tone: {options.custom_tone.strip()}"
            else:
                # Fallback if custom_only but no custom tone provided
                return "- Tone: Engaging and conversational"
        
        # Define preset style instructions
        style_instructions = {
            "engaging_casual": "- Tone: Engaging, casual, and conversational - like chatting with a friend",
            "informative_professional": "- Tone: Informative, professional, and helpful - focus on sharing valuable insights",
            "supportive_friendly": "- Tone: Supportive, friendly, and encouraging - be positive and uplifting"
        }
        
        # Get base instruction from preset
        base_instruction = style_instructions.get(options.reply_style, style_instructions["engaging_casual"])
        
        # Add custom tone if provided (preset + custom combination)
        if options.custom_tone and options.custom_tone.strip():
            return f"{base_instruction}\n- Custom voice/personality: {options.custom_tone.strip()}"
        
        return base_instruction
    
    async def _generate_single_reply(self, prompt: str, tweet: ScrapedTweet, options: ReplyOptions, index: int) -> Optional[GeneratedReply]:
        """Generate a single reply using OpenAI"""
        
        try:
            # Use async execution to avoid blocking
            loop = asyncio.get_event_loop()
            
            def make_openai_request():
                # Create system message based on reply style and custom tone
                tone_description = self._get_tone_instructions(options).replace("- Tone: ", "").replace("- Custom voice/personality: ", " with a ")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": f"You are an expert social media manager who creates engaging, authentic Twitter replies. Generate replies that are {tone_description}. Always stay within Twitter's 280 character limit. Keep responses concise and under 150 tokens."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )
                return response.choices[0].message.content.strip()
            
            reply_text = await loop.run_in_executor(None, make_openai_request)
            
            # Clean up the reply
            reply_text = self._clean_reply_text(reply_text)
            
            # Calculate confidence score based on various factors
            confidence_score = self._calculate_confidence_score(reply_text, tweet, options)
            
            # Generate reasoning and suggestions
            reasoning = self._generate_reasoning(reply_text, tweet, index)
            suggestions = self._generate_suggestions(reply_text, tweet)
            
            return GeneratedReply(
                id=f"reply_{tweet.tweet_id}_{index}",
                text=reply_text,
                reply_style=options.reply_style,
                custom_tone=options.custom_tone,
                character_count=len(reply_text),
                confidence_score=confidence_score,
                reasoning=reasoning,
                suggested_improvements=suggestions
            )
            
        except Exception as e:
            logger.error(f"Error generating single reply: {e}")
            return None
    
    def _clean_reply_text(self, text: str) -> str:
        """Clean and format reply text"""
        # Remove quotes if they wrap the entire response
        text = text.strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
        
        # Remove "Reply:" prefix if present
        if text.lower().startswith("reply:"):
            text = text[6:].strip()
        
        # Ensure it's within character limit
        if len(text) > 280:
            text = text[:277] + "..."
        
        return text
    
    def _calculate_confidence_score(self, reply_text: str, tweet: ScrapedTweet, options: ReplyOptions) -> float:
        """Calculate confidence score for the reply (0.0 to 1.0)"""
        score = 0.8  # Base score
        
        # Length scoring
        if 50 <= len(reply_text) <= 200:
            score += 0.1
        elif len(reply_text) < 20:
            score -= 0.2
        
        # Engagement potential
        if "?" in reply_text:  # Questions drive engagement
            score += 0.1
        
        if any(word in reply_text.lower() for word in ["great", "interesting", "thanks", "love"]):
            score += 0.05
        
        # Relevance (basic keyword matching)
        tweet_words = set(tweet.text.lower().split())
        reply_words = set(reply_text.lower().split())
        overlap = len(tweet_words.intersection(reply_words))
        if overlap > 0:
            score += min(0.1, overlap * 0.02)
        
        return min(1.0, max(0.0, score))
    
    def _generate_reasoning(self, reply_text: str, tweet: ScrapedTweet, index: int) -> str:
        """Generate reasoning for why this reply was suggested"""
        styles = [
            "Encourages thoughtful discussion",
            "Asks engaging question to drive interaction", 
            "Provides supportive and positive response",
            "Adds valuable information and context",
            "Uses creative approach to stand out"
        ]
        
        base_reasoning = styles[index] if index < len(styles) else "Provides engaging response"
        
        if "?" in reply_text:
            base_reasoning += " and includes question to encourage replies"
        
        if len(reply_text) <= 180:
            base_reasoning += ", keeping it concise for easy reading"
        
        return base_reasoning
    
    def _generate_suggestions(self, reply_text: str, tweet: ScrapedTweet) -> List[str]:
        """Generate suggestions for improving the reply"""
        suggestions = []
        
        if len(reply_text) > 200:
            suggestions.append("Consider shortening for better readability")
        
        if "?" not in reply_text and len(reply_text) < 150:
            suggestions.append("Could add a question to encourage engagement")
        
        if not any(char in reply_text for char in "!.?"):
            suggestions.append("Add punctuation for better clarity")
        
        if len(reply_text) < 50:
            suggestions.append("Could expand with more detail or context")
        
        return suggestions
    
    async def regenerate_reply(self, original_reply: GeneratedReply, tweet: ScrapedTweet, feedback: str = "") -> GeneratedReply:
        """Regenerate a specific reply with feedback"""
        
        prompt = f"""
Original tweet: "{tweet.text}"
Previous reply: "{original_reply.text}"
Feedback: {feedback if feedback else "Make it more engaging"}

Generate an improved version of the reply that addresses the feedback while maintaining relevance to the original tweet.
Stay within 280 characters.

Improved reply:"""
        
        try:
            new_reply = await self._generate_single_reply(prompt, tweet, ReplyOptions(), 0)
            if new_reply:
                new_reply.id = f"regenerated_{original_reply.id}"
                return new_reply
            else:
                return original_reply
        except Exception as e:
            logger.error(f"Error regenerating reply: {e}")
            return original_reply
    
    async def test_generation(self) -> bool:
        """Test AI reply generation"""
        try:
            logger.info("Testing AI reply generation...")
            
            # Create a mock tweet for testing
            from .rapidapi_client import ScrapedTweet
            test_tweet = ScrapedTweet(
                tweet_id="test_123",
                url="https://x.com/test/status/123",
                text="Just launched our new AI-powered analytics platform! Excited to see how it helps businesses make data-driven decisions. #AI #Analytics #Innovation",
                author_username="test_user",
                author_display_name="Test User",
                author_profile_image="",
                created_at="2025-08-18T10:00:00Z",
                retweet_count=5,
                reply_count=2,
                like_count=15,
                quote_count=1,
                view_count=100,
                bookmark_count=3,
                is_retweet=False,
                is_quote=False,
                media_urls=[],
                hashtags=["AI", "Analytics", "Innovation"],
                mentions=[]
            )
            
            replies = await self.generate_replies(test_tweet, ReplyOptions(max_replies=2))
            
            success = len(replies) > 0
            
            if success:
                logger.info(f"AI reply generation test successful - generated {len(replies)} replies")
                for i, reply in enumerate(replies):
                    logger.info(f"Reply {i+1}: {reply.text}")
            else:
                logger.error("AI reply generation test failed - no replies generated")
            
            return success
            
        except Exception as e:
            logger.error(f"AI reply generation test failed: {e}")
            return False


# Global generator instance
ai_reply_generator = AIReplyGenerator()