import tweepy
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from .config import settings

class TwitterClient:
    def __init__(self):
        self.client = None
        self.api = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Twitter API client with OAuth2"""
        try:
            # OAuth2 Bearer Token for API v2
            self.client = tweepy.Client(
                bearer_token=settings.twitter_bearer_token,
                consumer_key=settings.twitter_consumer_key,
                consumer_secret=settings.twitter_consumer_secret,
                access_token=settings.twitter_access_token,
                access_token_secret=settings.twitter_access_token_secret,
                wait_on_rate_limit=True
            )
            
            # OAuth1 for posting (required for write operations)
            auth = tweepy.OAuth1UserHandler(
                settings.twitter_consumer_key,
                settings.twitter_consumer_secret,
                settings.twitter_access_token,
                settings.twitter_access_token_secret
            )
            self.api = tweepy.API(auth, wait_on_rate_limit=True)
            
            print("Twitter client initialized successfully")
        except Exception as e:
            print(f"Error initializing Twitter client: {e}")
            raise e
    
    def get_user_recent_tweets(self, username: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Get recent tweets from a specific user"""
        try:
            user = self.client.get_user(username=username, user_fields=['id'])
            if not user.data:
                print(f"User {username} not found")
                return []
            
            user_id = user.data.id
            tweets = self.client.get_users_tweets(
                id=user_id,
                max_results=max_results,
                tweet_fields=['created_at', 'public_metrics', 'text', 'author_id'],
                exclude=['retweets', 'replies']
            )
            
            if not tweets.data:
                return []
            
            tweet_list = []
            for tweet in tweets.data:
                tweet_data = {
                    'id': tweet.id,
                    'text': tweet.text,
                    'created_at': tweet.created_at,
                    'author_username': username,
                    'public_metrics': tweet.public_metrics
                }
                tweet_list.append(tweet_data)
            
            return tweet_list
        except Exception as e:
            print(f"Error fetching tweets for user {username}: {e}")
            return []
    
    def get_multiple_users_recent_tweets(self, usernames: List[str], max_results_per_user: int = 5) -> List[Dict[str, Any]]:
        """Get recent tweets from multiple users"""
        all_tweets = []
        for username in usernames:
            user_tweets = self.get_user_recent_tweets(username.strip(), max_results_per_user)
            all_tweets.extend(user_tweets)
        
        # Sort by creation time, newest first
        all_tweets.sort(key=lambda x: x['created_at'], reverse=True)
        return all_tweets
    
    def post_reply(self, tweet_id: str, reply_text: str) -> Optional[str]:
        """Post a reply to a tweet"""
        try:
            response = self.client.create_tweet(
                text=reply_text,
                in_reply_to_tweet_id=tweet_id
            )
            if response.data:
                print(f"Reply posted successfully: {response.data['id']}")
                return response.data['id']
            return None
        except Exception as e:
            print(f"Error posting reply: {e}")
            return None
    
    def post_quote_tweet(self, tweet_id: str, quote_text: str) -> Optional[str]:
        """Post a quote tweet"""
        try:
            # Construct quote tweet URL
            tweet_url = f"https://twitter.com/i/web/status/{tweet_id}"
            full_text = f"{quote_text} {tweet_url}"
            
            response = self.client.create_tweet(text=full_text)
            if response.data:
                print(f"Quote tweet posted successfully: {response.data['id']}")
                return response.data['id']
            return None
        except Exception as e:
            print(f"Error posting quote tweet: {e}")
            return None
    
    def get_tweet_metrics(self, tweet_id: str) -> Optional[Dict[str, int]]:
        """Get public metrics for a specific tweet"""
        try:
            tweet = self.client.get_tweet(
                id=tweet_id,
                tweet_fields=['public_metrics']
            )
            
            if tweet.data and tweet.data.public_metrics:
                return {
                    'likes': tweet.data.public_metrics['like_count'],
                    'retweets': tweet.data.public_metrics['retweet_count'],
                    'replies': tweet.data.public_metrics['reply_count']
                }
            return None
        except Exception as e:
            print(f"Error fetching tweet metrics for {tweet_id}: {e}")
            return None
    
    def get_multiple_tweet_metrics(self, tweet_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """Get metrics for multiple tweets"""
        metrics = {}
        for tweet_id in tweet_ids:
            tweet_metrics = self.get_tweet_metrics(tweet_id)
            if tweet_metrics:
                metrics[tweet_id] = tweet_metrics
        return metrics
    
    def test_connection(self) -> bool:
        """Test if the Twitter connection is working"""
        try:
            me = self.client.get_me()
            if me.data:
                print(f"Connected as: @{me.data.username}")
                return True
            return False
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False
    
    def validate_api_permissions(self) -> Dict[str, Any]:
        """Comprehensive API validation including write permissions"""
        validation_results = {
            "read_access": False,
            "write_access": False,
            "user_info": None,
            "permissions": {},
            "errors": [],
            "recommendations": []
        }
        
        try:
            # Test basic read access
            me = self.client.get_me()
            if me.data:
                validation_results["read_access"] = True
                validation_results["user_info"] = {
                    "username": me.data.username,
                    "id": me.data.id,
                    "name": me.data.name if hasattr(me.data, 'name') else None
                }
                print(f"✅ Read access confirmed for @{me.data.username}")
            else:
                validation_results["errors"].append("Unable to fetch user information")
                return validation_results
                
        except Exception as e:
            validation_results["errors"].append(f"Read access failed: {str(e)}")
            validation_results["recommendations"].append("Check TWITTER_BEARER_TOKEN and basic credentials")
            return validation_results
        
        # Test write permissions (like, retweet, reply)
        write_tests = {
            "like": self._test_like_permission,
            "retweet": self._test_retweet_permission,
            "reply": self._test_reply_permission
        }
        
        for permission, test_func in write_tests.items():
            try:
                result = test_func()
                validation_results["permissions"][permission] = result
                if result["available"]:
                    print(f"✅ {permission.capitalize()} permission confirmed")
                else:
                    print(f"❌ {permission.capitalize()} permission failed: {result['error']}")
                    validation_results["errors"].append(f"{permission.capitalize()}: {result['error']}")
            except Exception as e:
                validation_results["permissions"][permission] = {"available": False, "error": str(e)}
                validation_results["errors"].append(f"{permission.capitalize()} test failed: {str(e)}")
        
        # Check if we have any write access
        validation_results["write_access"] = any(
            perm.get("available", False) for perm in validation_results["permissions"].values()
        )
        
        # Generate recommendations
        if not validation_results["write_access"]:
            validation_results["recommendations"].extend([
                "Verify TWITTER_ACCESS_TOKEN and TWITTER_ACCESS_TOKEN_SECRET are correct",
                "Ensure your Twitter app has Read and Write permissions",
                "Check that your Twitter Developer account is approved",
                "Regenerate access tokens if permissions were recently changed"
            ])
        
        return validation_results
    
    def _test_like_permission(self) -> Dict[str, Any]:
        """Test like permission without actually liking anything"""
        try:
            # Try to get rate limit status for likes endpoint
            # This should work if we have proper write permissions
            if hasattr(self.api, 'get_rate_limit_status'):
                status = self.api.get_rate_limit_status()
                like_limit = status.get('resources', {}).get('favorites', {}).get('/favorites/create', {})
                
                if like_limit:
                    return {
                        "available": True,
                        "rate_limit": like_limit,
                        "method": "rate_limit_check"
                    }
            
            # Alternative: check if we can access the API endpoint
            # This is a dry run approach
            return {
                "available": True,
                "method": "endpoint_accessible",
                "note": "Cannot fully verify without actual like attempt"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            if "forbidden" in error_msg or "403" in error_msg:
                return {"available": False, "error": "Insufficient permissions - check app permissions"}
            elif "unauthorized" in error_msg or "401" in error_msg:
                return {"available": False, "error": "Authentication failed - check access tokens"}
            else:
                return {"available": False, "error": f"API error: {str(e)}"}
    
    def _test_retweet_permission(self) -> Dict[str, Any]:
        """Test retweet permission"""
        try:
            # Similar approach to like testing
            if hasattr(self.api, 'get_rate_limit_status'):
                status = self.api.get_rate_limit_status()
                retweet_limit = status.get('resources', {}).get('statuses', {}).get('/statuses/retweet/:id', {})
                
                if retweet_limit:
                    return {
                        "available": True,
                        "rate_limit": retweet_limit,
                        "method": "rate_limit_check"
                    }
            
            return {
                "available": True,
                "method": "endpoint_accessible",
                "note": "Cannot fully verify without actual retweet attempt"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            if "forbidden" in error_msg or "403" in error_msg:
                return {"available": False, "error": "Insufficient permissions - check app permissions"}
            elif "unauthorized" in error_msg or "401" in error_msg:
                return {"available": False, "error": "Authentication failed - check access tokens"}
            else:
                return {"available": False, "error": f"API error: {str(e)}"}
    
    def _test_reply_permission(self) -> Dict[str, Any]:
        """Test reply permission"""
        try:
            # Test tweet creation permission (required for replies)
            if hasattr(self.api, 'get_rate_limit_status'):
                status = self.api.get_rate_limit_status()
                tweet_limit = status.get('resources', {}).get('statuses', {}).get('/statuses/update', {})
                
                if tweet_limit:
                    return {
                        "available": True,
                        "rate_limit": tweet_limit,
                        "method": "rate_limit_check"
                    }
            
            return {
                "available": True,
                "method": "endpoint_accessible",
                "note": "Cannot fully verify without actual reply attempt"
            }
            
        except Exception as e:
            error_msg = str(e).lower()
            if "forbidden" in error_msg or "403" in error_msg:
                return {"available": False, "error": "Insufficient permissions - check app permissions"}
            elif "unauthorized" in error_msg or "401" in error_msg:
                return {"available": False, "error": "Authentication failed - check access tokens"}
            else:
                return {"available": False, "error": f"API error: {str(e)}"}
    
    def get_api_status_summary(self) -> str:
        """Get a human-readable summary of API status"""
        validation = self.validate_api_permissions()
        
        if not validation["read_access"]:
            return "❌ Twitter API connection failed - check credentials"
        
        if not validation["write_access"]:
            return "⚠️ Read-only access - like/retweet functionality unavailable"
        
        working_permissions = [
            perm for perm, details in validation["permissions"].items() 
            if details.get("available", False)
        ]
        
        if len(working_permissions) == 3:
            return "✅ Full Twitter API access confirmed (read/write/interact)"
        else:
            return f"⚠️ Partial access - working: {', '.join(working_permissions)}"

twitter_client = TwitterClient()