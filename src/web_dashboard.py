#!/usr/bin/env python3
"""
Twitter Auto Bot - Web Dashboard

Simple web interface for monitoring and controlling the Twitter bot.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import sys
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Add src to Python path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from .scheduler import scheduler
from .config import settings
from .database import db, TwitterList, ListTweet, ProcessedTweet
from .logger import logger
from .apify_client import apify_client
from .manual_reply import manual_reply_service
from .rapidapi_client import rapidapi_client
from .ai_reply_generator import ai_reply_generator, ReplyOptions
from .content_analyzer import content_analyzer
from .reply_comparison import reply_comparator
from .tweet_interaction import tweet_interaction_service

app = FastAPI(title="Twitter Bot Dashboard", description="Monitor and control your Twitter automation bot")

# Setup templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Global state
dashboard_state = {
    "last_update": datetime.now(),
    "activity_log": [],
    "is_running": False,
    "current_operation": None,
    "rate_limit_status": None,
    "last_poll_result": None
}

# Thread pool for background operations
thread_pool = ThreadPoolExecutor(max_workers=2)

def add_to_activity_log(message: str, level: str = "info"):
    """Add a message to the activity log"""
    dashboard_state["activity_log"].insert(0, {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "level": level
    })
    # Keep only last 50 entries
    dashboard_state["activity_log"] = dashboard_state["activity_log"][:50]

def format_rate_limit_message(seconds_remaining: int) -> str:
    """Format rate limit message in plain English"""
    if seconds_remaining <= 0:
        return "Rate limit has expired, ready to continue"
    
    minutes = seconds_remaining // 60
    if minutes > 0:
        return f"Rate limited - waiting {minutes} minutes before retrying"
    else:
        return f"Rate limited - waiting {seconds_remaining} seconds before retrying"

def run_polling_task():
    """Background task for polling tweets with rate limit handling"""
    import asyncio
    import tweepy
    
    async def poll_with_timeout():
        try:
            # Initialize if needed
            if not await scheduler.initialize():
                raise Exception("Failed to initialize scheduler")
            
            add_to_activity_log("Checking for new tweets...", "info")
            
            # Custom tweet polling with rate limit detection
            from .tweet_poller import poller
            
            try:
                new_tweets = await poller.poll_and_process()
                
                if len(new_tweets) == 0:
                    add_to_activity_log("No new tweets found", "info")
                    dashboard_state["last_poll_result"] = "No new tweets found"
                else:
                    add_to_activity_log(f"Found {len(new_tweets)} new tweets to process", "success")
                    dashboard_state["last_poll_result"] = f"{len(new_tweets)} tweets found and processed"
                
                add_to_activity_log("Tweet polling completed successfully", "success")
                
            except tweepy.TooManyRequests as e:
                # Handle rate limiting
                reset_time = getattr(e, 'reset_time', None)
                if reset_time:
                    wait_seconds = int(reset_time - time.time())
                    dashboard_state["rate_limit_status"] = {
                        "wait_seconds": wait_seconds,
                        "reset_time": reset_time,
                        "message": format_rate_limit_message(wait_seconds)
                    }
                    add_to_activity_log(f"Rate limit hit - waiting {wait_seconds//60} minutes", "error")
                else:
                    add_to_activity_log("Rate limit hit - unknown wait time", "error")
                    
            except Exception as e:
                if "rate limit" in str(e).lower() or "429" in str(e):
                    # Generic rate limit detection
                    dashboard_state["rate_limit_status"] = {
                        "wait_seconds": 900,  # Default 15 minutes
                        "reset_time": time.time() + 900,
                        "message": "Rate limited - waiting 15 minutes before retry"
                    }
                    add_to_activity_log("Rate limit detected - waiting 15 minutes", "error")
                else:
                    raise e
                    
        except Exception as e:
            error_msg = f"Error during tweet polling: {str(e)}"
            add_to_activity_log(error_msg, "error")
            dashboard_state["last_poll_result"] = f"Error: {str(e)}"
        finally:
            dashboard_state["current_operation"] = None
    
    # Run the async function
    try:
        asyncio.run(poll_with_timeout())
    except Exception as e:
        add_to_activity_log(f"Background polling error: {str(e)}", "error")
        dashboard_state["current_operation"] = None

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/status")
async def get_status():
    """Get current bot status"""
    try:
        # Get scheduler stats
        stats = scheduler.get_stats()
        
        # Get recent tweets from database
        recent_tweets_query = """
        SELECT COUNT(*) as total_tweets,
               COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as today_tweets
        FROM tweets
        """
        
        # Format status in plain English
        status_message = "Bot is idle"
        
        # Check for current operations
        if dashboard_state["current_operation"]:
            status_message = f"Currently {dashboard_state['current_operation']}"
        
        # Check for rate limit status
        elif dashboard_state["rate_limit_status"]:
            rate_limit = dashboard_state["rate_limit_status"]
            current_wait = int(rate_limit["reset_time"] - time.time())
            if current_wait > 0:
                status_message = format_rate_limit_message(current_wait)
            else:
                # Rate limit expired, clear it
                dashboard_state["rate_limit_status"] = None
                status_message = "Ready to check tweets"
        
        # Check last poll result
        elif dashboard_state["last_poll_result"]:
            status_message = dashboard_state["last_poll_result"]
        
        # Fallback to last poll time
        elif stats.get('last_poll_time'):
            last_poll = stats['last_poll_time']
            if isinstance(last_poll, str):
                last_poll = datetime.fromisoformat(last_poll.replace('Z', '+00:00'))
            time_since = (datetime.now() - last_poll.replace(tzinfo=None)).total_seconds()
            if time_since < 300:  # 5 minutes
                status_message = "Recently checked for new tweets"
            elif time_since < 3600:  # 1 hour
                status_message = f"Last checked {int(time_since/60)} minutes ago"
            else:
                status_message = f"Last checked {int(time_since/3600)} hours ago"
        
        return {
            "status": "online",
            "status_message": status_message,
            "stats": stats,
            "config": {
                "target_accounts": settings.target_accounts,
                "poll_interval": settings.poll_interval_minutes,
                "engagement_check_hours": settings.engagement_check_hours
            },
            "activity_log": dashboard_state["activity_log"],
            "last_update": dashboard_state["last_update"].isoformat(),
            "current_operation": dashboard_state["current_operation"],
            "rate_limit_status": dashboard_state["rate_limit_status"],
            "last_poll_result": dashboard_state["last_poll_result"]
        }
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return {"status": "error", "message": str(e)}

@app.post("/api/trigger/poll")
async def trigger_poll(background_tasks: BackgroundTasks):
    """Manually trigger a tweet polling cycle"""
    try:
        # Check if already running
        if dashboard_state["current_operation"] == "polling":
            return {"success": False, "message": "Polling already in progress"}
        
        add_to_activity_log("Manual tweet polling triggered", "info")
        dashboard_state["current_operation"] = "polling"
        dashboard_state["rate_limit_status"] = None
        
        # Run polling in background
        background_tasks.add_task(run_polling_task)
        
        return {"success": True, "message": "Tweet polling started"}
        
    except Exception as e:
        error_msg = f"Error starting tweet polling: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        dashboard_state["current_operation"] = None
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/trigger/engagement")
async def trigger_engagement(background_tasks: BackgroundTasks):
    """Manually trigger engagement metrics update"""
    try:
        # Check if already running
        if dashboard_state["current_operation"] == "engagement":
            return {"success": False, "message": "Engagement update already in progress"}
        
        add_to_activity_log("Manual engagement update triggered", "info")
        dashboard_state["current_operation"] = "engagement"
        
        # Run engagement update in background (this is usually fast)
        background_tasks.add_task(run_engagement_task)
        
        return {"success": True, "message": "Engagement update started"}
        
    except Exception as e:
        error_msg = f"Error starting engagement update: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        dashboard_state["current_operation"] = None
        raise HTTPException(status_code=500, detail=error_msg)

def run_engagement_task():
    """Background task for updating engagement metrics"""
    import asyncio
    
    async def update_engagement():
        try:
            # Initialize if needed
            if not await scheduler.initialize():
                raise Exception("Failed to initialize scheduler")
            
            add_to_activity_log("Updating engagement metrics...", "info")
            
            # Run engagement update
            await scheduler.run_engagement_update_cycle()
            
            add_to_activity_log("Engagement metrics updated successfully", "success")
            
        except Exception as e:
            error_msg = f"Error updating engagement metrics: {str(e)}"
            add_to_activity_log(error_msg, "error")
        finally:
            dashboard_state["current_operation"] = None
    
    # Run the async function
    try:
        asyncio.run(update_engagement())
    except Exception as e:
        add_to_activity_log(f"Background engagement error: {str(e)}", "error")
        dashboard_state["current_operation"] = None

@app.post("/api/trigger/test")
async def trigger_test():
    """Test all API connections"""
    try:
        add_to_activity_log("Testing API connections...", "info")
        
        # Test connections (similar to main.py test_connections)
        from .twitter_client import twitter_client
        
        if not twitter_client.test_connection():
            raise Exception("Twitter API connection failed")
        
        await db.init_database()
        
        if not settings.openai_api_key:
            raise Exception("OpenAI API key not configured")
        
        add_to_activity_log("All API connections successful", "success")
        return {"success": True, "message": "All connections successful"}
        
    except Exception as e:
        error_msg = f"Connection test failed: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/stats")
async def get_detailed_stats():
    """Get detailed statistics"""
    try:
        stats = scheduler.get_stats()
        
        # Get database stats
        db_stats = {}
        try:
            # This would need to be implemented based on your database structure
            db_stats = {"total_tweets": 0, "total_responses": 0}
        except:
            pass
        
        return {
            "scheduler_stats": stats,
            "database_stats": db_stats,
            "config": {
                "target_accounts": settings.target_accounts,
                "poll_interval_minutes": settings.poll_interval_minutes,
                "engagement_check_hours": settings.engagement_check_hours
            }
        }
    except Exception as e:
        logger.error(f"Error getting detailed stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/lists/import")
async def import_twitter_list(request: Request):
    """Import and scrape a Twitter list"""
    try:
        body = await request.json()
        list_url = body.get("list_url", "").strip()
        list_name = body.get("name", "").strip()
        max_items = body.get("max_items", 20)
        
        if not list_url:
            raise HTTPException(status_code=400, detail="List URL is required")
        
        if not list_name:
            # Extract name from URL or use default
            list_name = f"List {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        add_to_activity_log(f"Starting import of Twitter list: {list_url}", "info")
        
        # Check if list already exists
        existing_list = db.get_twitter_list_by_url(list_url)
        if existing_list:
            list_id = existing_list["id"]
            add_to_activity_log("List already exists, updating tweets", "info")
        else:
            # Create new list record
            twitter_list = TwitterList(name=list_name, list_url=list_url)
            list_id = db.save_twitter_list(twitter_list)
            if not list_id:
                raise HTTPException(status_code=500, detail="Failed to save Twitter list")
            add_to_activity_log("Created new Twitter list record", "success")
        
        # Scrape tweets
        tweets = await apify_client.scrape_twitter_list(list_url, max_items)
        
        # Save tweets to database with better error handling
        saved_count = 0
        failed_count = 0
        
        for i, tweet in enumerate(tweets):
            try:
                if not db.list_tweet_exists(tweet.tweet_id):
                    list_tweet = ListTweet(
                        list_id=list_id,
                        tweet_id=tweet.tweet_id,
                        url=tweet.url,
                        text=tweet.text,
                        author_username=tweet.author_username,
                        author_display_name=tweet.author_display_name,
                        created_at=apify_client._parse_tweet_date(tweet.created_at),
                        retweet_count=tweet.retweet_count,
                        reply_count=tweet.reply_count,
                        like_count=tweet.like_count,
                        quote_count=tweet.quote_count,
                        bookmark_count=tweet.bookmark_count,
                        is_retweet=tweet.is_retweet,
                        is_quote=tweet.is_quote
                    )
                    
                    if db.save_list_tweet(list_tweet):
                        saved_count += 1
                        logger.info(f"Saved tweet {i+1}/{len(tweets)}: {tweet.tweet_id}")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to save tweet {i+1}/{len(tweets)}: {tweet.tweet_id}")
                else:
                    logger.info(f"Tweet {i+1}/{len(tweets)} already exists: {tweet.tweet_id}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing tweet {i+1}/{len(tweets)} ({tweet.tweet_id}): {e}")
                continue
        
        if failed_count > 0:
            add_to_activity_log(f"Warning: {failed_count} tweets failed to save", "error")
        
        # Update last scraped time
        db.update_list_scraped_time(list_id)
        
        add_to_activity_log(f"Successfully imported {saved_count} new tweets from list", "success")
        
        return {
            "success": True,
            "message": f"Successfully imported {saved_count} tweets",
            "list_id": list_id,
            "total_tweets": len(tweets),
            "new_tweets": saved_count
        }
        
    except Exception as e:
        error_msg = f"Error importing Twitter list: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/lists")
async def get_twitter_lists():
    """Get all Twitter lists"""
    try:
        lists = db.get_all_twitter_lists()
        return {"lists": lists}
    except Exception as e:
        logger.error(f"Error fetching Twitter lists: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/lists/{list_id}/tweets")
async def get_list_tweets(list_id: int, limit: int = 20, offset: int = 0):
    """Get tweets from a specific list"""
    try:
        tweets = db.get_list_tweets(list_id, limit, offset)
        return {"tweets": tweets, "count": len(tweets)}
    except Exception as e:
        logger.error(f"Error fetching list tweets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tweets")
async def get_all_list_tweets(limit: int = 20, offset: int = 0):
    """Get all tweets from all lists"""
    try:
        tweets = db.get_list_tweets(None, limit, offset)
        return {"tweets": tweets, "count": len(tweets)}
    except Exception as e:
        logger.error(f"Error fetching tweets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/replies/send")
async def send_manual_reply(request: Request):
    """Send a manual reply to a tweet"""
    try:
        body = await request.json()
        tweet_id = body.get("tweet_id", "").strip()
        reply_text = body.get("reply_text", "").strip()
        target_username = body.get("target_username", "").strip()
        
        if not tweet_id:
            raise HTTPException(status_code=400, detail="Tweet ID is required")
        
        if not reply_text:
            raise HTTPException(status_code=400, detail="Reply text is required")
        
        # Validate reply text
        is_valid, validation_message = manual_reply_service.validate_reply_text(reply_text)
        if not is_valid:
            raise HTTPException(status_code=400, detail=validation_message)
        
        add_to_activity_log(f"Sending manual reply to tweet {tweet_id}", "info")
        
        # Send the reply
        result = await manual_reply_service.send_reply(tweet_id, reply_text, target_username)
        
        if result.success:
            add_to_activity_log(f"Reply sent successfully via {result.method_used}", "success")
            return {
                "success": True,
                "message": f"Reply sent successfully via {result.method_used}",
                "method_used": result.method_used,
                "reply_id": result.reply_id
            }
        else:
            add_to_activity_log(f"Reply failed: {result.error_message}", "error")
            return {
                "success": False,
                "message": result.error_message,
                "method_used": result.method_used
            }
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error sending reply: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/replies/history")
async def get_reply_history(limit: int = 20):
    """Get recent manual replies"""
    try:
        replies = db.get_recent_replies(limit)
        return {"replies": replies, "count": len(replies)}
    except Exception as e:
        logger.error(f"Error fetching reply history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/replies/user-replies")
async def get_user_replies(count: int = 20):
    """Get recent user replies from Twitter via RapidAPI"""
    try:
        user_replies = await rapidapi_client.get_user_replies(count=count)
        
        # Convert to dict format for JSON response
        replies_data = []
        for reply in user_replies:
            replies_data.append({
                "tweet_id": reply.tweet_id,
                "url": reply.url,
                "text": reply.text,
                "created_at": reply.created_at,
                "reply_to_tweet_id": reply.reply_to_tweet_id,
                "reply_to_username": reply.reply_to_username,
                "metrics": {
                    "retweets": reply.retweet_count,
                    "replies": reply.reply_count,
                    "likes": reply.like_count,
                    "quotes": reply.quote_count
                }
            })
        
        return {"replies": replies_data, "count": len(replies_data)}
    except Exception as e:
        logger.error(f"Error fetching user replies: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/replies/preview")
async def preview_reply(request: Request):
    """Preview a reply before sending"""
    try:
        body = await request.json()
        tweet_id = body.get("tweet_id", "").strip()
        reply_text = body.get("reply_text", "").strip()
        target_username = body.get("target_username", "").strip()
        
        if not tweet_id or not reply_text:
            raise HTTPException(status_code=400, detail="Tweet ID and reply text are required")
        
        # Validate reply text
        is_valid, validation_message = manual_reply_service.validate_reply_text(reply_text)
        
        # Generate preview
        preview = manual_reply_service.get_reply_preview(tweet_id, reply_text, target_username)
        
        return {
            "preview": preview,
            "is_valid": is_valid,
            "validation_message": validation_message,
            "character_count": len(reply_text)
        }
        
    except Exception as e:
        logger.error(f"Error generating reply preview: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# NEW AI-POWERED ENDPOINTS

@app.post("/api/tweet/analyze")
async def analyze_tweet(request: Request):
    """Analyze a single tweet URL and scrape its content"""
    try:
        body = await request.json()
        tweet_url = body.get("tweet_url", "").strip()
        
        if not tweet_url:
            raise HTTPException(status_code=400, detail="Tweet URL is required")
        
        add_to_activity_log(f"Analyzing tweet: {tweet_url}", "info")
        
        # Scrape tweet using RapidAPI
        scraped_tweet = await rapidapi_client.scrape_tweet(tweet_url)
        
        if not scraped_tweet:
            raise HTTPException(status_code=400, detail="Failed to scrape tweet. Please check the URL and try again.")
        
        add_to_activity_log(f"Successfully analyzed tweet from @{scraped_tweet.author_username}", "success")
        
        return {
            "success": True,
            "tweet": {
                "id": scraped_tweet.tweet_id,
                "url": scraped_tweet.url,
                "text": scraped_tweet.text,
                "author": {
                    "username": scraped_tweet.author_username,
                    "display_name": scraped_tweet.author_display_name,
                    "profile_image": scraped_tweet.author_profile_image
                },
                "created_at": scraped_tweet.created_at,
                "metrics": {
                    "likes": scraped_tweet.like_count,
                    "retweets": scraped_tweet.retweet_count,
                    "replies": scraped_tweet.reply_count,
                    "quotes": scraped_tweet.quote_count,
                    "views": scraped_tweet.view_count,
                    "bookmarks": scraped_tweet.bookmark_count
                },
                "hashtags": scraped_tweet.hashtags,
                "mentions": scraped_tweet.mentions,
                "media": scraped_tweet.media_urls
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error analyzing tweet: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/replies/generate")
async def generate_ai_replies(request: Request):
    """Generate AI reply suggestions for a tweet"""
    try:
        body = await request.json()
        tweet_data = body.get("tweet", {})
        options_data = body.get("options", {})
        
        if not tweet_data:
            raise HTTPException(status_code=400, detail="Tweet data is required")
        
        # Create ScrapedTweet object from request data
        from .rapidapi_client import ScrapedTweet
        scraped_tweet = ScrapedTweet(
            tweet_id=tweet_data.get("id", ""),
            url=tweet_data.get("url", ""),
            text=tweet_data.get("text", ""),
            author_username=tweet_data.get("author", {}).get("username", ""),
            author_display_name=tweet_data.get("author", {}).get("display_name", ""),
            author_profile_image=tweet_data.get("author", {}).get("profile_image", ""),
            created_at=tweet_data.get("created_at", ""),
            retweet_count=tweet_data.get("metrics", {}).get("retweets", 0),
            reply_count=tweet_data.get("metrics", {}).get("replies", 0),
            like_count=tweet_data.get("metrics", {}).get("likes", 0),
            quote_count=tweet_data.get("metrics", {}).get("quotes", 0),
            view_count=tweet_data.get("metrics", {}).get("views", 0),
            bookmark_count=tweet_data.get("metrics", {}).get("bookmarks", 0),
            is_retweet=tweet_data.get("is_retweet", False),
            is_quote=tweet_data.get("is_quote", False),
            media_urls=tweet_data.get("media", []),
            hashtags=tweet_data.get("hashtags", []),
            mentions=tweet_data.get("mentions", [])
        )
        
        # Create reply options
        reply_options = ReplyOptions(
            reply_style=options_data.get("reply_style", "engaging_casual"),
            custom_tone=options_data.get("custom_tone", ""),
            length=options_data.get("length", "medium"),
            include_emoji=options_data.get("include_emoji", True),
            include_hashtags=options_data.get("include_hashtags", False),
            max_replies=options_data.get("max_replies", 5)
        )
        
        add_to_activity_log(f"Generating AI replies for tweet from @{scraped_tweet.author_username}", "info")
        
        # Generate AI replies
        generated_replies = await ai_reply_generator.generate_replies(scraped_tweet, reply_options)
        
        if not generated_replies:
            raise HTTPException(status_code=500, detail="Failed to generate AI replies. Please try again.")
        
        add_to_activity_log(f"Generated {len(generated_replies)} AI reply suggestions", "success")
        
        # Check for similar replies against recent user replies
        try:
            user_replies = await rapidapi_client.get_user_replies(count=10)  # Check last 10 replies
            filtered_replies, similarity_reports = reply_comparator.filter_similar_replies(generated_replies, user_replies)
            
            if len(filtered_replies) < len(generated_replies):
                filtered_count = len(generated_replies) - len(filtered_replies)
                add_to_activity_log(f"Filtered out {filtered_count} similar replies", "info")
            
            # Use filtered replies for final output
            final_replies = filtered_replies if filtered_replies else generated_replies[:1]  # Keep at least one reply
            
        except Exception as e:
            logger.warning(f"Reply comparison failed, using all generated replies: {e}")
            final_replies = generated_replies
            similarity_reports = []
        
        # Format replies for frontend
        formatted_replies = []
        for reply in final_replies:
            formatted_replies.append({
                "id": reply.id,
                "text": reply.text,
                "reply_style": reply.reply_style,
                "custom_tone": reply.custom_tone,
                "character_count": reply.character_count,
                "confidence_score": reply.confidence_score,
                "reasoning": reply.reasoning,
                "suggested_improvements": reply.suggested_improvements
            })
        
        return {
            "success": True,
            "replies": formatted_replies,
            "count": len(formatted_replies),
            "similarity_reports": similarity_reports if 'similarity_reports' in locals() else [],
            "filtered_count": len(generated_replies) - len(final_replies) if 'final_replies' in locals() else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error generating AI replies: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/replies/edit")
async def edit_reply(request: Request):
    """Edit a generated reply before posting"""
    try:
        body = await request.json()
        reply_id = body.get("reply_id", "")
        new_text = body.get("new_text", "").strip()
        
        if not reply_id or not new_text:
            raise HTTPException(status_code=400, detail="Reply ID and new text are required")
        
        # Validate reply text
        is_valid, validation_message = manual_reply_service.validate_reply_text(new_text)
        if not is_valid:
            raise HTTPException(status_code=400, detail=validation_message)
        
        add_to_activity_log(f"Edited reply {reply_id}", "info")
        
        return {
            "success": True,
            "reply": {
                "id": reply_id,
                "text": new_text,
                "character_count": len(new_text),
                "is_valid": is_valid,
                "validation_message": validation_message
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error editing reply: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/replies/post-single")
async def post_single_reply(request: Request):
    """Post a single reply"""
    try:
        body = await request.json()
        tweet_id = body.get("tweet_id", "")
        reply_text = body.get("reply_text", "").strip()
        target_username = body.get("target_username", "")
        
        if not tweet_id or not reply_text:
            raise HTTPException(status_code=400, detail="Tweet ID and reply text are required")
        
        # Validate reply text
        is_valid, validation_message = manual_reply_service.validate_reply_text(reply_text)
        if not is_valid:
            raise HTTPException(status_code=400, detail=validation_message)
        
        add_to_activity_log(f"Posting single reply to tweet {tweet_id}", "info")
        
        # Send the reply using existing manual reply service
        result = await manual_reply_service.send_reply(tweet_id, reply_text, target_username)
        
        if result.success:
            add_to_activity_log(f"Reply posted successfully via {result.method_used}", "success")
            return {
                "success": True,
                "message": f"Reply posted successfully via {result.method_used}",
                "method_used": result.method_used,
                "reply_id": result.reply_id
            }
        else:
            add_to_activity_log(f"Reply failed: {result.error_message}", "error")
            return {
                "success": False,
                "message": result.error_message,
                "method_used": result.method_used
            }
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error posting reply: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/replies/post-bulk")
async def post_bulk_replies(request: Request):
    """Post multiple replies at once"""
    try:
        body = await request.json()
        tweet_id = body.get("tweet_id", "")
        replies = body.get("replies", [])
        target_username = body.get("target_username", "")
        delay_seconds = body.get("delay_seconds", 5)  # Delay between posts
        
        if not tweet_id or not replies:
            raise HTTPException(status_code=400, detail="Tweet ID and replies are required")
        
        add_to_activity_log(f"Posting {len(replies)} bulk replies to tweet {tweet_id}", "info")
        
        results = []
        successful_posts = 0
        
        for i, reply_text in enumerate(replies):
            try:
                # Validate each reply
                is_valid, validation_message = manual_reply_service.validate_reply_text(reply_text)
                if not is_valid:
                    results.append({
                        "index": i,
                        "text": reply_text,
                        "success": False,
                        "error": validation_message
                    })
                    continue
                
                # Send the reply
                result = await manual_reply_service.send_reply(tweet_id, reply_text, target_username)
                
                if result.success:
                    successful_posts += 1
                    results.append({
                        "index": i,
                        "text": reply_text,
                        "success": True,
                        "method_used": result.method_used,
                        "reply_id": result.reply_id
                    })
                else:
                    results.append({
                        "index": i,
                        "text": reply_text,
                        "success": False,
                        "error": result.error_message
                    })
                
                # Add delay between posts to avoid rate limiting
                if i < len(replies) - 1:  # Don't delay after the last post
                    await asyncio.sleep(delay_seconds)
                    
            except Exception as e:
                results.append({
                    "index": i,
                    "text": reply_text,
                    "success": False,
                    "error": str(e)
                })
        
        add_to_activity_log(f"Bulk posting completed: {successful_posts}/{len(replies)} successful", 
                          "success" if successful_posts > 0 else "error")
        
        return {
            "success": successful_posts > 0,
            "total_replies": len(replies),
            "successful_posts": successful_posts,
            "failed_posts": len(replies) - successful_posts,
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error posting bulk replies: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/ai/test")
async def test_ai_services():
    """Test AI and RapidAPI services"""
    try:
        results = {}
        
        # Test RapidAPI connection
        try:
            rapidapi_test = await rapidapi_client.test_connection()
            results["rapidapi"] = {
                "status": "success" if rapidapi_test else "failed",
                "message": "Connection successful" if rapidapi_test else "Connection failed"
            }
        except Exception as e:
            results["rapidapi"] = {
                "status": "error",
                "message": str(e)
            }
        
        # Test AI reply generation
        try:
            ai_test = await ai_reply_generator.test_generation()
            results["ai_generator"] = {
                "status": "success" if ai_test else "failed",
                "message": "Generation test successful" if ai_test else "Generation test failed"
            }
        except Exception as e:
            results["ai_generator"] = {
                "status": "error",
                "message": str(e)
            }
        
        overall_success = all(result["status"] == "success" for result in results.values())
        
        return {
            "success": overall_success,
            "services": results
        }
        
    except Exception as e:
        logger.error(f"Error testing AI services: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# TWEET INTERACTION ENDPOINTS

@app.post("/api/tweets/{tweet_id}/like")
async def like_tweet(tweet_id: str, request: Request):
    """Like a tweet"""
    try:
        body = await request.json()
        tweet_url = body.get("tweet_url", "")
        
        add_to_activity_log(f"Liking tweet {tweet_id}", "info")
        
        # Check if already liked
        if db.interaction_exists(tweet_id, "like"):
            return {
                "success": False,
                "message": "Tweet already liked",
                "already_liked": True
            }
        
        # Like the tweet
        result = await tweet_interaction_service.like_tweet(tweet_id, tweet_url)
        
        if result.success:
            # Save interaction to database
            from .database import TweetInteraction
            interaction = TweetInteraction(
                tweet_id=tweet_id,
                interaction_type="like",
                method_used=result.method_used,
                status="success",
                interaction_id=result.interaction_id,
                completed_at=datetime.now()
            )
            db.save_tweet_interaction(interaction)
            
            add_to_activity_log(f"Tweet liked successfully via {result.method_used}", "success")
            return {
                "success": True,
                "message": f"Tweet liked successfully via {result.method_used}",
                "method_used": result.method_used,
                "interaction_id": result.interaction_id
            }
        else:
            add_to_activity_log(f"Like failed: {result.error_message}", "error")
            return {
                "success": False,
                "message": result.error_message,
                "method_used": result.method_used
            }
            
    except Exception as e:
        error_msg = f"Error liking tweet: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/tweets/{tweet_id}/retweet")
async def retweet_tweet(tweet_id: str, request: Request):
    """Retweet a tweet"""
    try:
        body = await request.json()
        tweet_url = body.get("tweet_url", "")
        
        add_to_activity_log(f"Retweeting tweet {tweet_id}", "info")
        
        # Check if already retweeted
        if db.interaction_exists(tweet_id, "retweet"):
            return {
                "success": False,
                "message": "Tweet already retweeted",
                "already_retweeted": True
            }
        
        # Retweet the tweet
        result = await tweet_interaction_service.retweet_tweet(tweet_id, tweet_url)
        
        if result.success:
            # Save interaction to database
            from .database import TweetInteraction
            interaction = TweetInteraction(
                tweet_id=tweet_id,
                interaction_type="retweet",
                method_used=result.method_used,
                status="success",
                interaction_id=result.interaction_id,
                completed_at=datetime.now()
            )
            db.save_tweet_interaction(interaction)
            
            add_to_activity_log(f"Tweet retweeted successfully via {result.method_used}", "success")
            return {
                "success": True,
                "message": f"Tweet retweeted successfully via {result.method_used}",
                "method_used": result.method_used,
                "interaction_id": result.interaction_id
            }
        else:
            add_to_activity_log(f"Retweet failed: {result.error_message}", "error")
            return {
                "success": False,
                "message": result.error_message,
                "method_used": result.method_used
            }
            
    except Exception as e:
        error_msg = f"Error retweeting tweet: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/tweets/bulk-like")
async def bulk_like_tweets(request: Request):
    """Like multiple tweets"""
    try:
        body = await request.json()
        tweet_ids = body.get("tweet_ids", [])
        
        if not tweet_ids:
            raise HTTPException(status_code=400, detail="Tweet IDs are required")
        
        add_to_activity_log(f"Starting bulk like operation for {len(tweet_ids)} tweets", "info")
        
        # Filter out already liked tweets
        new_tweet_ids = []
        already_liked = 0
        for tweet_id in tweet_ids:
            if not db.interaction_exists(tweet_id, "like"):
                new_tweet_ids.append(tweet_id)
            else:
                already_liked += 1
        
        if already_liked > 0:
            add_to_activity_log(f"Skipping {already_liked} already-liked tweets", "info")
        
        if not new_tweet_ids:
            return {
                "success": True,
                "message": "All tweets already liked",
                "total_requested": len(tweet_ids),
                "successful_count": 0,
                "failed_count": 0,
                "already_liked_count": already_liked,
                "results": []
            }
        
        # Perform bulk like operation
        bulk_result = await tweet_interaction_service.bulk_like_tweets(new_tweet_ids)
        
        # Save successful interactions to database
        for result in bulk_result.results:
            if result.success:
                from .database import TweetInteraction
                interaction = TweetInteraction(
                    tweet_id=new_tweet_ids[bulk_result.results.index(result)],
                    interaction_type="like",
                    method_used=result.method_used,
                    status="success",
                    interaction_id=result.interaction_id,
                    completed_at=datetime.now()
                )
                db.save_tweet_interaction(interaction)
        
        add_to_activity_log(f"Bulk like completed: {bulk_result.successful_count} successful, {bulk_result.failed_count} failed", 
                          "success" if bulk_result.successful_count > 0 else "warning")
        
        return {
            "success": bulk_result.successful_count > 0,
            "message": f"Liked {bulk_result.successful_count}/{len(new_tweet_ids)} tweets",
            "total_requested": len(tweet_ids),
            "successful_count": bulk_result.successful_count,
            "failed_count": bulk_result.failed_count,
            "already_liked_count": already_liked,
            "results": [
                {
                    "tweet_id": new_tweet_ids[i],
                    "success": result.success,
                    "method_used": result.method_used,
                    "error_message": result.error_message
                }
                for i, result in enumerate(bulk_result.results)
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error in bulk like operation: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/tweets/bulk-retweet")
async def bulk_retweet_tweets(request: Request):
    """Retweet multiple tweets"""
    try:
        body = await request.json()
        tweet_ids = body.get("tweet_ids", [])
        
        if not tweet_ids:
            raise HTTPException(status_code=400, detail="Tweet IDs are required")
        
        add_to_activity_log(f"Starting bulk retweet operation for {len(tweet_ids)} tweets", "info")
        
        # Filter out already retweeted tweets
        new_tweet_ids = []
        already_retweeted = 0
        for tweet_id in tweet_ids:
            if not db.interaction_exists(tweet_id, "retweet"):
                new_tweet_ids.append(tweet_id)
            else:
                already_retweeted += 1
        
        if already_retweeted > 0:
            add_to_activity_log(f"Skipping {already_retweeted} already-retweeted tweets", "info")
        
        if not new_tweet_ids:
            return {
                "success": True,
                "message": "All tweets already retweeted",
                "total_requested": len(tweet_ids),
                "successful_count": 0,
                "failed_count": 0,
                "already_retweeted_count": already_retweeted,
                "results": []
            }
        
        # Perform bulk retweet operation
        bulk_result = await tweet_interaction_service.bulk_retweet_tweets(new_tweet_ids)
        
        # Save successful interactions to database
        for result in bulk_result.results:
            if result.success:
                from .database import TweetInteraction
                interaction = TweetInteraction(
                    tweet_id=new_tweet_ids[bulk_result.results.index(result)],
                    interaction_type="retweet",
                    method_used=result.method_used,
                    status="success",
                    interaction_id=result.interaction_id,
                    completed_at=datetime.now()
                )
                db.save_tweet_interaction(interaction)
        
        add_to_activity_log(f"Bulk retweet completed: {bulk_result.successful_count} successful, {bulk_result.failed_count} failed", 
                          "success" if bulk_result.successful_count > 0 else "warning")
        
        return {
            "success": bulk_result.successful_count > 0,
            "message": f"Retweeted {bulk_result.successful_count}/{len(new_tweet_ids)} tweets",
            "total_requested": len(tweet_ids),
            "successful_count": bulk_result.successful_count,
            "failed_count": bulk_result.failed_count,
            "already_retweeted_count": already_retweeted,
            "results": [
                {
                    "tweet_id": new_tweet_ids[i],
                    "success": result.success,
                    "method_used": result.method_used,
                    "error_message": result.error_message
                }
                for i, result in enumerate(bulk_result.results)
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error in bulk retweet operation: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/interactions/history")
async def get_interaction_history(limit: int = 20, interaction_type: str = None):
    """Get recent tweet interactions"""
    try:
        interactions = db.get_recent_interactions(limit, interaction_type)
        return {"interactions": interactions, "count": len(interactions)}
    except Exception as e:
        logger.error(f"Error fetching interaction history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tweets/{tweet_id}/interactions")
async def get_tweet_interactions(tweet_id: str):
    """Get all interactions for a specific tweet"""
    try:
        # Check what interactions exist for this tweet
        has_like = db.interaction_exists(tweet_id, "like")
        has_retweet = db.interaction_exists(tweet_id, "retweet")
        has_reply = tweet_id in db.get_replied_tweet_ids()
        
        return {
            "tweet_id": tweet_id,
            "interactions": {
                "liked": has_like,
                "retweeted": has_retweet,
                "replied": has_reply
            }
        }
    except Exception as e:
        logger.error(f"Error fetching tweet interactions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/twitter/validate")
async def validate_twitter_api():
    """Validate Twitter API credentials and permissions"""
    try:
        from .twitter_client import twitter_client
        
        add_to_activity_log("Validating Twitter API credentials and permissions...", "info")
        
        # Run comprehensive validation
        validation_results = twitter_client.validate_api_permissions()
        
        # Get human-readable summary
        status_summary = twitter_client.get_api_status_summary()
        
        # Log results
        if validation_results["read_access"] and validation_results["write_access"]:
            add_to_activity_log("Twitter API validation successful - full access confirmed", "success")
        elif validation_results["read_access"]:
            add_to_activity_log("Twitter API validation partial - read-only access", "warning")
        else:
            add_to_activity_log("Twitter API validation failed - check credentials", "error")
        
        return {
            "success": validation_results["read_access"],
            "status_summary": status_summary,
            "validation_results": validation_results,
            "setup_instructions": {
                "required_credentials": [
                    "TWITTER_CONSUMER_KEY",
                    "TWITTER_CONSUMER_SECRET", 
                    "TWITTER_ACCESS_TOKEN",
                    "TWITTER_ACCESS_TOKEN_SECRET",
                    "TWITTER_BEARER_TOKEN"
                ],
                "app_permissions_required": "Read and Write",
                "documentation": "https://developer.twitter.com/en/docs/authentication/oauth-1-0a"
            }
        }
    except Exception as e:
        error_msg = f"Error validating Twitter API: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/interactions/rate-limits")
async def get_rate_limit_status():
    """Get current rate limit status for tweet interactions"""
    try:
        rate_limits = tweet_interaction_service.get_rate_limit_status()
        
        # Calculate overall status
        total_used = sum(limits["used"] for limits in rate_limits.values())
        total_limit = sum(limits["total_limit"] for limits in rate_limits.values())
        overall_percentage = round((total_used / total_limit) * 100, 1) if total_limit > 0 else 0
        
        # Determine status level
        if overall_percentage >= 90:
            status_level = "critical"
            status_message = "Rate limits nearly exhausted - slow down interactions"
        elif overall_percentage >= 70:
            status_level = "warning"
            status_message = "Rate limits getting high - consider moderating interactions"
        elif overall_percentage >= 50:
            status_level = "caution"
            status_message = "Moderate rate limit usage"
        else:
            status_level = "good"
            status_message = "Rate limits healthy"
        
        return {
            "success": True,
            "overall_status": {
                "level": status_level,
                "message": status_message,
                "percentage_used": overall_percentage,
                "total_used": total_used,
                "total_limit": total_limit
            },
            "by_interaction_type": rate_limits,
            "recommendations": _get_rate_limit_recommendations(rate_limits)
        }
    except Exception as e:
        logger.error(f"Error getting rate limit status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _get_rate_limit_recommendations(rate_limits: Dict) -> List[str]:
    """Generate recommendations based on rate limit usage"""
    recommendations = []
    
    for interaction_type, limits in rate_limits.items():
        percentage = limits["percentage_used"]
        
        if percentage >= 90:
            recommendations.append(f"🔴 {interaction_type.capitalize()}: Stop {interaction_type}s for {limits['reset_in_seconds'] // 60} minutes")
        elif percentage >= 70:
            recommendations.append(f"🟡 {interaction_type.capitalize()}: Slow down - only {limits['remaining']} {interaction_type}s remaining")
        elif percentage >= 50:
            recommendations.append(f"🟠 {interaction_type.capitalize()}: Moderate usage - {limits['remaining']} {interaction_type}s left")
    
    if not recommendations:
        recommendations.append("✅ All rate limits healthy - continue normal operations")
    
    return recommendations

@app.post("/api/lists/batch-process")
async def batch_process_list_tweets(request: Request):
    """Load tweets from Twitter list and generate AI replies for batch processing"""
    try:
        body = await request.json()
        list_id = body.get("list_id", "1957324919269929248").strip()  # Default to your list ID
        count = body.get("count", 5)
        replies_per_tweet = body.get("replies_per_tweet", 3)
        reply_style = body.get("reply_style", "engaging_casual")
        custom_tone = body.get("custom_tone", "")
        enable_filtering = body.get("enable_filtering", True)
        relevance_threshold = body.get("relevance_threshold", 70.0)
        
        # Validate inputs
        if not list_id:
            raise HTTPException(status_code=400, detail="List ID is required")
        
        count = max(1, min(count, 10))  # Limit between 1-10
        replies_per_tweet = max(1, min(replies_per_tweet, 5))  # Limit between 1-5
        relevance_threshold = max(50.0, min(relevance_threshold, 100.0))  # Limit between 50-100%
        
        add_to_activity_log(f"Starting batch processing for list {list_id}, loading {count} tweets", "info")
        
        # Step 1: Smart Tweet Fetching with Backfill
        target_tweet_count = count
        max_fetch_attempts = 3
        max_total_tweets = count * 4  # Don't fetch more than 4x the target
        all_tweets = []
        fetch_stats = {
            "attempts": 0,
            "total_fetched": 0,
            "batch_sizes": []
        }
        
        try:
            add_to_activity_log(f"Starting smart tweet fetching for {target_tweet_count} relevant tweets", "info")
            
            # Initial fetch
            initial_batch_size = max(count, 10)  # Fetch at least 10 to start
            tweets = await rapidapi_client.scrape_twitter_list(list_id, initial_batch_size)
            
            if not tweets:
                # Force use of mock data for testing
                tweets = rapidapi_client._generate_mock_list_tweets(list_id, initial_batch_size)
            
            all_tweets.extend(tweets)
            fetch_stats["attempts"] = 1
            fetch_stats["total_fetched"] = len(tweets)
            fetch_stats["batch_sizes"].append(len(tweets))
            
            add_to_activity_log(f"Initial fetch: {len(tweets)} tweets retrieved", "success")
            
        except Exception as e:
            error_msg = f"Error loading tweets from list: {str(e)}"
            add_to_activity_log(error_msg, "error")
            raise HTTPException(status_code=500, detail=error_msg)
        
        # Step 1.5: Filter out already-processed tweets (including replied-to tweets)
        replied_tweet_ids = set(db.get_replied_tweet_ids())
        processed_tweet_ids = set(db.bulk_check_processed_tweets([tweet.tweet_id for tweet in all_tweets]))
        
        tweets_before_filter = len(all_tweets)
        
        # Count tweets to be filtered
        filtered_by_replies = len([t for t in all_tweets if t.tweet_id in replied_tweet_ids])
        filtered_by_processed = len([t for t in all_tweets if t.tweet_id in processed_tweet_ids])
        
        # Apply filter
        all_tweets = [tweet for tweet in all_tweets if tweet.tweet_id not in replied_tweet_ids and tweet.tweet_id not in processed_tweet_ids]
        total_filtered = tweets_before_filter - len(all_tweets)
        filtered_by_history = total_filtered  # Total tweets filtered by reply/processing history
        
        if total_filtered > 0:
            filter_details = []
            if filtered_by_replies > 0:
                filter_details.append(f"{filtered_by_replies} already replied")
            if filtered_by_processed > 0:
                filter_details.append(f"{filtered_by_processed} already processed")
            
            add_to_activity_log(f"Filtered out {total_filtered} tweets: {', '.join(filter_details)}", "info")
        
        if not all_tweets:
            add_to_activity_log("No new tweets found (all have been replied to)", "warning")
            return {
                "success": True,
                "list_id": list_id,
                "target_tweet_count": target_tweet_count,
                "total_tweets_fetched": tweets_before_filter,
                "relevant_tweets": 0,
                "filtered_out": tweets_before_filter,
                "filtered_by_history": filtered_by_history,
                "successful_generations": 0,
                "failed_generations": 0,
                "batch_results": [],
                "filtering_enabled": enable_filtering,
                "relevance_threshold": relevance_threshold,
                "fetch_stats": fetch_stats,
                "backfill_stats": {"needed_backfill": False, "target_count": target_tweet_count, "final_relevant_count": 0},
                "message": "No new tweets to process (all previously replied to)"
            }
        
        # Step 2: Intelligent Content Filtering with Backfill
        content_analyses = []
        filtered_tweets = all_tweets  # Start with all fetched tweets
        filtering_stats = {}
        backfill_stats = {
            "needed_backfill": False,
            "target_count": target_tweet_count,
            "final_relevant_count": 0
        }
        
        if enable_filtering:
            # Iterative filtering with backfill
            attempt = 1
            
            while len(filtered_tweets) < target_tweet_count and attempt <= max_fetch_attempts and len(all_tweets) < max_total_tweets:
                try:
                    add_to_activity_log(f"Attempt {attempt}: Analyzing {len(all_tweets)} tweets for content relevance (threshold: {relevance_threshold}%)", "info")
                    
                    # Set threshold for this analysis
                    content_analyzer.relevance_threshold = relevance_threshold
                    
                    # Analyze content relevance for all tweets
                    content_analyses = await content_analyzer.analyze_tweets(all_tweets)
                    
                    # Filter to only relevant tweets
                    filtered_tweets = content_analyzer.filter_relevant_tweets(all_tweets, content_analyses)
                    
                    # Check if we need more tweets
                    if len(filtered_tweets) < target_tweet_count and attempt < max_fetch_attempts:
                        backfill_stats["needed_backfill"] = True
                        
                        # Calculate how many more tweets we need to fetch
                        current_success_rate = len(filtered_tweets) / len(all_tweets) if len(all_tweets) > 0 else 0.5
                        needed_tweets = target_tweet_count - len(filtered_tweets)
                        
                        # Estimate batch size needed (with buffer)
                        if current_success_rate > 0:
                            estimated_batch_size = int(needed_tweets / current_success_rate * 1.5)
                        else:
                            estimated_batch_size = needed_tweets * 3
                        
                        # Cap the batch size
                        estimated_batch_size = min(estimated_batch_size, max_total_tweets - len(all_tweets))
                        
                        if estimated_batch_size > 0:
                            add_to_activity_log(
                                f"Need {needed_tweets} more relevant tweets. Fetching {estimated_batch_size} additional tweets (success rate: {current_success_rate:.1%})",
                                "info"
                            )
                            
                            # Fetch more tweets
                            additional_tweets = await rapidapi_client.scrape_twitter_list(list_id, estimated_batch_size)
                            if not additional_tweets:
                                additional_tweets = rapidapi_client._generate_mock_list_tweets(list_id, estimated_batch_size)
                            
                            # Remove duplicates by tweet ID
                            existing_ids = {tweet.tweet_id for tweet in all_tweets}
                            new_tweets = [tweet for tweet in additional_tweets if tweet.tweet_id not in existing_ids]
                            
                            all_tweets.extend(new_tweets)
                            fetch_stats["attempts"] += 1
                            fetch_stats["total_fetched"] += len(new_tweets)
                            fetch_stats["batch_sizes"].append(len(new_tweets))
                            
                            add_to_activity_log(f"Fetched {len(new_tweets)} additional tweets ({len(new_tweets)} new, {len(additional_tweets) - len(new_tweets)} duplicates)", "success")
                    
                    attempt += 1
                    
                except Exception as e:
                    error_msg = f"Error in content analysis (attempt {attempt}): {str(e)}"
                    add_to_activity_log(error_msg, "warning")
                    logger.warning(f"Content filtering failed on attempt {attempt}: {e}")
                    break
            
            # Keep all relevant tweets - don't waste good content
            
            backfill_stats["final_relevant_count"] = len(filtered_tweets)
            
            # Get final filtering statistics
            if content_analyses:
                filtering_stats = content_analyzer.get_filtering_stats(content_analyses)
            
            add_to_activity_log(
                f"Smart filtering complete: {len(filtered_tweets)}/{len(all_tweets)} tweets passed filter (fetched {len(all_tweets)} total to get {len(filtered_tweets)} relevant)",
                "success" if len(filtered_tweets) > 0 else "warning"
            )
                
        else:
            add_to_activity_log("Content filtering disabled, processing all tweets", "info")
            # Limit to target count if no filtering
            filtered_tweets = all_tweets[:target_tweet_count]
            backfill_stats["final_relevant_count"] = len(filtered_tweets)
        
        # Step 3: Generate AI replies for each relevant tweet
        batch_results = []
        successful_generations = 0
        
        for i, tweet in enumerate(filtered_tweets):
            try:
                add_to_activity_log(f"Generating AI replies for tweet {i+1}/{len(filtered_tweets)}", "info")
                
                # Find content analysis for this tweet if available
                content_context = None
                if content_analyses:
                    content_context = next((analysis for analysis in content_analyses if analysis.tweet_id == tweet.tweet_id), None)
                
                # Create reply options with content context
                reply_options = ReplyOptions(
                    reply_style=reply_style,
                    custom_tone=custom_tone,
                    length="medium",
                    include_emoji=True,
                    include_hashtags=False,
                    max_replies=replies_per_tweet  # Generate specified number of suggestions per tweet
                )
                
                # Generate AI replies with content context
                generated_replies = await ai_reply_generator.generate_replies(tweet, reply_options, content_context)
                
                if generated_replies:
                    successful_generations += 1
                    
                    # Format for frontend
                    formatted_replies = []
                    for reply in generated_replies:
                        formatted_replies.append({
                            "id": reply.id,
                            "text": reply.text,
                            "reply_style": reply.reply_style,
                            "custom_tone": reply.custom_tone,
                            "character_count": reply.character_count,
                            "confidence_score": reply.confidence_score,
                            "reasoning": reply.reasoning
                        })
                    
                    batch_results.append({
                        "tweet": {
                            "id": tweet.tweet_id,
                            "url": tweet.url,
                            "text": tweet.text,
                            "author": {
                                "username": tweet.author_username,
                                "display_name": tweet.author_display_name,
                                "profile_image": tweet.author_profile_image
                            },
                            "created_at": tweet.created_at,
                            "metrics": {
                                "likes": tweet.like_count,
                                "retweets": tweet.retweet_count,
                                "replies": tweet.reply_count,
                                "quotes": tweet.quote_count,
                                "views": tweet.view_count,
                                "bookmarks": tweet.bookmark_count
                            },
                            "hashtags": tweet.hashtags,
                            "mentions": tweet.mentions
                        },
                        "ai_replies": formatted_replies,
                        "status": "ready"
                    })
                else:
                    # Tweet with no AI replies generated
                    batch_results.append({
                        "tweet": {
                            "id": tweet.tweet_id,
                            "url": tweet.url,
                            "text": tweet.text,
                            "author": {
                                "username": tweet.author_username,
                                "display_name": tweet.author_display_name,
                                "profile_image": tweet.author_profile_image
                            },
                            "created_at": tweet.created_at,
                            "metrics": {
                                "likes": tweet.like_count,
                                "retweets": tweet.retweet_count,
                                "replies": tweet.reply_count,
                                "quotes": tweet.quote_count,
                                "views": tweet.view_count,
                                "bookmarks": tweet.bookmark_count
                            },
                            "hashtags": tweet.hashtags,
                            "mentions": tweet.mentions
                        },
                        "ai_replies": [],
                        "status": "failed",
                        "error": "Failed to generate AI replies"
                    })
                
            except Exception as e:
                logger.error(f"Error processing tweet {i+1}: {e}")
                batch_results.append({
                    "tweet": {
                        "id": tweet.tweet_id,
                        "text": tweet.text,
                        "author": {
                            "username": tweet.author_username,
                            "display_name": tweet.author_display_name
                        }
                    },
                    "ai_replies": [],
                    "status": "error",
                    "error": str(e)
                })
        
        # Step 4: Save all processed tweets to database for deduplication
        for i, tweet in enumerate(filtered_tweets):
            try:
                # Find content analysis for this tweet if available
                content_context = None
                if content_analyses:
                    content_context = next((analysis for analysis in content_analyses if analysis.tweet_id == tweet.tweet_id), None)
                
                # Create processed tweet record
                processed_tweet = ProcessedTweet(
                    tweet_id=tweet.tweet_id,
                    list_id=list_id,
                    author_username=tweet.author_username,
                    tweet_url=tweet.url,
                    tweet_text=tweet.text,
                    was_analyzed=content_context is not None,
                    was_relevant=content_context.is_relevant if content_context else True,
                    relevance_score=content_context.relevance_score if content_context else None,
                    analysis_categories=json.dumps(content_context.categories) if content_context and content_context.categories else None,
                    skip_reason=content_context.skip_reason if content_context else None,
                    processed_at=datetime.now()
                )
                
                # Save to database
                db.save_processed_tweet(processed_tweet)
                
            except Exception as e:
                logger.warning(f"Error saving processed tweet {tweet.tweet_id}: {e}")
        
        add_to_activity_log(f"Saved {len(filtered_tweets)} processed tweets to database", "info")
        
        # Create success message that celebrates bonus tweets
        if len(filtered_tweets) > target_tweet_count:
            bonus_count = len(filtered_tweets) - target_tweet_count
            success_message = f"Batch processing completed: {successful_generations}/{len(filtered_tweets)} relevant tweets processed successfully (🎉 Found {bonus_count} bonus tweets!)"
        else:
            success_message = f"Batch processing completed: {successful_generations}/{len(filtered_tweets)} relevant tweets processed successfully"
        
        add_to_activity_log(success_message, "success" if successful_generations > 0 else "warning")
        
        # Prepare response with filtering and backfill information
        response = {
            "success": True,
            "list_id": list_id,
            "target_tweet_count": target_tweet_count,
            "total_tweets_fetched": tweets_before_filter,
            "relevant_tweets": len(filtered_tweets),
            "filtered_out": len(all_tweets) - len(filtered_tweets),
            "filtered_by_history": filtered_by_history,
            "successful_generations": successful_generations,
            "failed_generations": len(filtered_tweets) - successful_generations,
            "batch_results": batch_results,
            "filtering_enabled": enable_filtering,
            "relevance_threshold": relevance_threshold
        }
        
        # Add fetch statistics
        response["fetch_stats"] = fetch_stats
        
        # Add backfill statistics
        response["backfill_stats"] = backfill_stats
        
        # Add filtering stats if available
        if filtering_stats:
            response["filtering_stats"] = filtering_stats
        
        # Add content analyses if available
        if content_analyses:
            response["content_analyses"] = [
                {
                    "tweet_id": analysis.tweet_id,
                    "relevance_score": analysis.relevance_score,
                    "categories": analysis.categories,
                    "is_relevant": analysis.is_relevant,
                    "content_type": analysis.content_type,
                    "reasoning": analysis.reasoning,
                    "skip_reason": analysis.skip_reason
                }
                for analysis in content_analyses
            ]
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error in batch processing: {str(e)}"
        add_to_activity_log(error_msg, "error")
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

def run_dashboard(host="127.0.0.1", port=8000):
    """Run the web dashboard"""
    print(f"🌐 Starting Twitter Bot Dashboard at http://{host}:{port}")
    print("Press Ctrl+C to stop")
    
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    run_dashboard()