#!/usr/bin/env python3
"""
Twitter Auto Bot - Main Application Entry Point

A tool to automatically track, respond to, and engage with tweets from target accounts.
"""

import asyncio
import argparse
import sys
import logging
from datetime import datetime
from .scheduler import scheduler
from .logger import logger
from .config import settings
from .engagement_tracker import engagement_tracker

async def test_connections():
    """Test all API connections"""
    logger.info("Testing API connections...")
    
    try:
        # Test Twitter connection
        from .twitter_client import twitter_client
        if not twitter_client.test_connection():
            logger.error("Twitter API connection failed")
            return False
        logger.info("Twitter API connection successful")
        
        # Test database connection
        from .database import db
        await db.init_database()
        logger.info("Database connection successful")
        
        # Test OpenAI (by checking if API key is set)
        if not settings.openai_api_key:
            logger.error("OpenAI API key not configured")
            return False
        logger.info("OpenAI API key configured")
        
        return True
        
    except Exception as e:
        logger.error("Connection test failed", exception=e)
        return False

async def run_once():
    """Run a single cycle of the bot"""
    logger.info("Running single cycle...")
    
    if not await test_connections():
        logger.error("Connection tests failed. Exiting.")
        return False
    
    if not await scheduler.initialize():
        logger.error("Scheduler initialization failed. Exiting.")
        return False
    
    await scheduler.run_once()
    return True

async def run_continuous():
    """Run the bot continuously"""
    logger.log_startup()
    
    try:
        if not await test_connections():
            logger.error("Connection tests failed. Exiting.")
            return False
        
        if not await scheduler.initialize():
            logger.error("Scheduler initialization failed. Exiting.")
            return False
        
        # Setup signal handlers for graceful shutdown
        scheduler.setup_signal_handlers()
        
        # Start the scheduler
        await scheduler.run_continuous()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error("Unexpected error in main loop", exception=e)
    finally:
        logger.log_shutdown()

async def show_stats():
    """Show current statistics"""
    try:
        # Get scheduler stats
        stats = scheduler.get_stats()
        
        print("\n📊 Twitter Bot Statistics")
        print("=" * 40)
        print(f"Cycles completed: {stats['cycles_completed']}")
        print(f"Total tweets processed: {stats['total_tweets_processed']}")
        print(f"Successful posts: {stats['total_successful_posts']}")
        print(f"Total errors: {stats['total_errors']}")
        
        if stats['last_poll_time']:
            print(f"Last poll time: {stats['last_poll_time']}")
        
        if stats['last_engagement_update']:
            print(f"Last engagement update: {stats['last_engagement_update']}")
        
        # Get performance analysis
        analysis = await engagement_tracker.get_performance_analysis()
        if analysis:
            print(f"\nTotal tweets in database: {analysis.get('total_tweets', 0)}")
            
            avg_engagement = analysis.get('avg_engagement', {})
            if avg_engagement:
                print(f"Average likes: {avg_engagement.get('likes', 0):.1f}")
                print(f"Average retweets: {avg_engagement.get('retweets', 0):.1f}")
                print(f"Average replies: {avg_engagement.get('replies', 0):.1f}")
            
            trends = analysis.get('performance_trends', {})
            if trends:
                print(f"Performance trend: {trends.get('trend', 'unknown')}")
        
    except Exception as e:
        logger.error("Error generating statistics", exception=e)
        print("Error generating statistics. Check logs for details.")

async def update_engagement():
    """Manually update engagement metrics"""
    logger.info("Manually updating engagement metrics...")
    
    if not await test_connections():
        logger.error("Connection tests failed. Exiting.")
        return False
    
    stats = await engagement_tracker.update_engagement_metrics()
    print(f"Updated engagement metrics: {stats}")
    return True

def print_config():
    """Print current configuration"""
    print("\n⚙️  Configuration")
    print("=" * 30)
    print(f"Target accounts: {settings.target_accounts}")
    print(f"Poll interval: {settings.poll_interval_minutes} minutes")
    print(f"Engagement check interval: {settings.engagement_check_hours} hours")
    print(f"Twitter API configured: {'✓' if settings.twitter_bearer_token else '✗'}")
    print(f"OpenAI API configured: {'✓' if settings.openai_api_key else '✗'}")
    print(f"Supabase configured: {'✓' if settings.supabase_url else '✗'}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Twitter Auto Bot")
    parser.add_argument(
        "command",
        choices=["start", "once", "stats", "engagement", "config", "test", "dashboard"],
        help="Command to run"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set logging level"
    )
    
    args = parser.parse_args()
    
    # Configure logging level
    logger.logger.setLevel(getattr(logging, args.log_level))
    
    try:
        if args.command == "start":
            asyncio.run(run_continuous())
        elif args.command == "once":
            success = asyncio.run(run_once())
            sys.exit(0 if success else 1)
        elif args.command == "stats":
            asyncio.run(show_stats())
        elif args.command == "engagement":
            success = asyncio.run(update_engagement())
            sys.exit(0 if success else 1)
        elif args.command == "config":
            print_config()
        elif args.command == "test":
            success = asyncio.run(test_connections())
            if success:
                print("✓ All connections successful")
            else:
                print("✗ Connection tests failed")
            sys.exit(0 if success else 1)
        elif args.command == "dashboard":
            from .web_dashboard import run_dashboard
            run_dashboard()
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Unexpected error", exception=e)
        sys.exit(1)

if __name__ == "__main__":
    import logging
    main()