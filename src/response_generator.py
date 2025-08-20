import openai
from typing import Dict, Any, List, Optional
from .config import settings
from .database import db

class ResponseGenerator:
    def __init__(self):
        openai.api_key = settings.openai_api_key
        self.client = openai.OpenAI(api_key=settings.openai_api_key)
        
        # Default few-shot examples for tone guidance
        self.default_examples = [
            {
                "original": "Just shipped a new feature that automatically detects bugs in code. Game changer for developers!",
                "reply": "Love seeing tools that make developers' lives easier! The best features are the ones that solve real pain points. What inspired you to build this?",
                "quote": "This is exactly what the dev community needs! 🔥 Tools that catch issues before they become headaches are invaluable. Excited to see how this evolves! 👇"
            },
            {
                "original": "Working late again... sometimes I wonder if work-life balance is just a myth in tech",
                "reply": "Been there! Remember that sustainable productivity beats burnout every time. Your future self will thank you for setting boundaries. Take care of yourself! 💙",
                "quote": "Real talk about tech culture 💯 Work-life balance isn't a myth, but it definitely takes intentional effort to achieve. We need more conversations like this in our industry."
            },
            {
                "original": "AI is revolutionizing healthcare faster than we imagined. The possibilities are endless!",
                "reply": "The potential is incredible! What excites me most is how AI can help doctors focus on what they do best - caring for patients - while handling the routine tasks.",
                "quote": "The intersection of AI and healthcare is fascinating 🧠⚕️ We're witnessing history in the making. The key is ensuring these innovations truly serve patients and providers alike."
            }
        ]
    
    def get_few_shot_examples(self, response_type: str = "reply") -> List[Dict[str, str]]:
        """Get few-shot examples for prompting, including top-performing tweets"""
        examples = []
        
        # Get top-performing tweets from database
        try:
            top_tweets = db.get_top_performing_tweets(limit=3)
            for tweet in top_tweets:
                example = {
                    "original": tweet.get('original_tweet', ''),
                    response_type: tweet.get('response', '')
                }
                examples.append(example)
        except Exception as e:
            print(f"Error fetching top performing tweets: {e}")
        
        # Fill with default examples if we don't have enough
        for default_example in self.default_examples:
            if len(examples) >= 3:
                break
            example = {
                "original": default_example["original"],
                response_type: default_example.get(response_type, default_example["reply"])
            }
            examples.append(example)
        
        return examples[:3]  # Return top 3 examples
    
    def generate_reply(self, tweet: Dict[str, Any]) -> Optional[str]:
        """Generate a reply to a tweet"""
        examples = self.get_few_shot_examples("reply")
        
        examples_text = ""
        for i, example in enumerate(examples, 1):
            examples_text += f"\nExample {i}:\n"
            examples_text += f"Original tweet: \"{example['original']}\"\n"
            examples_text += f"Reply: \"{example['reply']}\"\n"
        
        system_prompt = """You are a thoughtful, engaging Twitter user who writes authentic replies that add value to conversations. Your responses should be:

- Casual and human, never robotic or corporate
- Emotionally aware and empathetic when appropriate
- Clever or insightful, but not trying too hard
- Encouraging genuine conversation
- Brief (under 280 characters)
- Free of hashtags and excessive emojis

Focus on adding value through genuine questions, insights, or supportive comments. Avoid generic responses like "Great post!" or "Thanks for sharing!"
"""
        
        user_prompt = f"""Based on these examples of good replies:{examples_text}

Now write a reply to this tweet:
"{tweet['text']}"

Remember: Be casual, human, and add real value to the conversation. Keep it under 280 characters."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.7
            )
            
            reply_text = response.choices[0].message.content.strip()
            
            # Remove quotes if the model added them
            if reply_text.startswith('"') and reply_text.endswith('"'):
                reply_text = reply_text[1:-1]
            
            # Ensure it's not too long
            if len(reply_text) > 280:
                reply_text = reply_text[:277] + "..."
            
            return reply_text
        
        except Exception as e:
            print(f"Error generating reply: {e}")
            return None
    
    def generate_quote_tweet(self, tweet: Dict[str, Any]) -> Optional[str]:
        """Generate a quote tweet comment"""
        examples = self.get_few_shot_examples("quote")
        
        examples_text = ""
        for i, example in enumerate(examples, 1):
            examples_text += f"\nExample {i}:\n"
            examples_text += f"Original tweet: \"{example['original']}\"\n"
            examples_text += f"Quote comment: \"{example['quote']}\"\n"
        
        system_prompt = """You are creating quote tweet comments that add perspective, insight, or commentary to the original tweet. Your quote comments should be:

- Thoughtful and add a unique angle or perspective
- Casual and conversational, not formal
- Engaging enough to encourage discussion
- Brief (under 200 characters to leave room for the quoted tweet)
- Include an emoji only if it genuinely adds value
- Avoid just restating what the original tweet said

Quote tweets are great for sharing your take on someone else's content while giving them credit.
"""
        
        user_prompt = f"""Based on these examples of good quote tweet comments:{examples_text}

Now write a quote tweet comment for this tweet:
"{tweet['text']}"

Remember: Add your unique perspective or insight. Keep it under 200 characters to leave room for the quoted tweet."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=80,
                temperature=0.7
            )
            
            quote_text = response.choices[0].message.content.strip()
            
            # Remove quotes if the model added them
            if quote_text.startswith('"') and quote_text.endswith('"'):
                quote_text = quote_text[1:-1]
            
            # Ensure it's not too long (leave room for quoted tweet URL)
            if len(quote_text) > 200:
                quote_text = quote_text[:197] + "..."
            
            return quote_text
        
        except Exception as e:
            print(f"Error generating quote tweet: {e}")
            return None
    
    def generate_response(self, tweet: Dict[str, Any], response_type: str) -> Optional[str]:
        """Generate a response based on the specified type"""
        if response_type == "reply":
            return self.generate_reply(tweet)
        elif response_type == "quote_rt":
            return self.generate_quote_tweet(tweet)
        else:
            print(f"Unknown response type: {response_type}")
            return None
    
    def is_response_appropriate(self, response: str, original_tweet: str) -> bool:
        """Check if the generated response is appropriate"""
        if not response or len(response.strip()) < 10:
            return False
        
        # Check for inappropriate content markers
        inappropriate_markers = [
            "I cannot", "I can't", "I'm not able", "I don't", "Sorry",
            "As an AI", "I'm an AI", "I apologize", "I should not"
        ]
        
        response_lower = response.lower()
        if any(marker.lower() in response_lower for marker in inappropriate_markers):
            return False
        
        # Check if response is too similar to original
        original_words = set(original_tweet.lower().split())
        response_words = set(response.lower().split())
        
        if len(original_words) > 0:
            similarity = len(original_words.intersection(response_words)) / len(original_words)
            if similarity > 0.7:  # Too similar
                return False
        
        return True

response_generator = ResponseGenerator()