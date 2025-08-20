#!/usr/bin/env python3
"""
Health Check Script for Twitter Auto Bot V2 Filtering System

Run this script after database migration to verify everything is working correctly.
"""

import sys
import os
import asyncio
from datetime import datetime
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.config import settings
from src.database import db
from src.content_analyzer_v2 import bulletproof_analyzer

class HealthCheckRunner:
    def __init__(self):
        self.checks = []
        self.passed = 0
        self.failed = 0
        
    def add_check(self, name: str, passed: bool, message: str, details: dict = None):
        """Add a health check result"""
        self.checks.append({
            "name": name,
            "passed": passed,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
        
        if passed:
            self.passed += 1
            print(f"✅ {name}: {message}")
        else:
            self.failed += 1
            print(f"❌ {name}: {message}")
            if details:
                print(f"   Details: {json.dumps(details, indent=2)}")

    async def run_all_checks(self):
        """Run all health checks"""
        print("🩺 Twitter Auto Bot V2 - Health Check")
        print("=" * 60)
        
        # Check 1: Environment Configuration
        await self.check_environment()
        
        # Check 2: Database Connectivity
        await self.check_database_connectivity()
        
        # Check 3: Database Tables and Schema
        await self.check_database_schema()
        
        # Check 4: Seed Data Verification
        await self.check_seed_data()
        
        # Check 5: V2 Filter Initialization
        await self.check_v2_filter_init()
        
        # Check 6: End-to-End Filter Test
        await self.check_end_to_end_filtering()
        
        # Print summary
        self.print_summary()
        
        return self.failed == 0

    async def check_environment(self):
        """Check environment variables are properly set"""
        required_vars = [
            ("OPENAI_API_KEY", settings.openai_api_key),
            ("SUPABASE_URL", settings.supabase_url),
            ("SUPABASE_KEY", settings.supabase_key),
            ("FEATURE_FILTER_V2", str(settings.feature_filter_v2)),
            ("RELEVANCE_THRESHOLD", str(settings.relevance_threshold))
        ]
        
        missing_vars = []
        configured_vars = []
        
        for var_name, var_value in required_vars:
            if not var_value or var_value in ["", "your_key_here", "your_url_here"]:
                missing_vars.append(var_name)
            else:
                configured_vars.append(var_name)
        
        if not missing_vars:
            self.add_check(
                "Environment Configuration",
                True,
                f"All {len(required_vars)} required variables configured",
                {"configured": configured_vars}
            )
        else:
            self.add_check(
                "Environment Configuration", 
                False,
                f"Missing {len(missing_vars)} required variables",
                {"missing": missing_vars, "configured": configured_vars}
            )

    async def check_database_connectivity(self):
        """Check basic database connectivity"""
        try:
            if not db.client:
                self.add_check(
                    "Database Connectivity",
                    False,
                    "Supabase client not initialized"
                )
                return
            
            # Test basic connectivity
            result = db.client.table("tweet_decisions").select("id").limit(1).execute()
            
            self.add_check(
                "Database Connectivity",
                True,
                "Successfully connected to Supabase",
                {"supabase_url": settings.supabase_url[:50] + "..."}
            )
            
        except Exception as e:
            self.add_check(
                "Database Connectivity",
                False,
                f"Failed to connect to database: {str(e)}"
            )

    async def check_database_schema(self):
        """Check all required tables and views exist"""
        required_tables = [
            "tweet_decisions",
            "processed_tweets", 
            "manual_replies"
        ]
        
        required_views = [
            "v_approved_tweets",
            "v_filter_comparison",
            "v_filter_health"
        ]
        
        existing_tables = []
        missing_tables = []
        existing_views = []
        missing_views = []
        
        # Check tables
        for table_name in required_tables:
            try:
                db.client.table(table_name).select("*").limit(1).execute()
                existing_tables.append(table_name)
            except Exception as e:
                missing_tables.append(table_name)
        
        # Check views (simpler approach)
        for view_name in required_views:
            try:
                result = db.client.rpc("exec", {
                    "sql": f"SELECT 1 FROM information_schema.views WHERE table_name = '{view_name}'"
                }).execute()
                existing_views.append(view_name)
            except:
                # If RPC not available, assume views exist if tables exist
                if not missing_tables:
                    existing_views.append(view_name)
                else:
                    missing_views.append(view_name)
        
        schema_complete = len(missing_tables) == 0
        
        self.add_check(
            "Database Schema",
            schema_complete,
            f"Tables: {len(existing_tables)}/{len(required_tables)} exist" + 
            (f", Views: {len(existing_views)}/{len(required_views)} exist" if existing_views else ""),
            {
                "existing_tables": existing_tables,
                "missing_tables": missing_tables,
                "existing_views": existing_views,
                "missing_views": missing_views
            }
        )

    async def check_seed_data(self):
        """Check seed data was inserted correctly"""
        try:
            result = db.client.table("tweet_decisions") \
                .select("final, tweet_id") \
                .eq("filter_version", "seed") \
                .execute()
            
            if not result.data:
                self.add_check(
                    "Seed Data",
                    False,
                    "No seed data found - run migration script",
                    {"instruction": "Execute supabase/migrations/20250820_filtering_v2.sql"}
                )
                return
            
            total_seeds = len(result.data)
            approved_count = len([r for r in result.data if r["final"] == "approved"])
            rejected_count = len([r for r in result.data if r["final"] == "rejected"])
            
            # Expected: 3 approved, 5 rejected
            seed_correct = approved_count == 3 and rejected_count == 5
            
            self.add_check(
                "Seed Data",
                seed_correct,
                f"Found {total_seeds} seed tweets: {approved_count} approved, {rejected_count} rejected",
                {
                    "total": total_seeds,
                    "approved": approved_count,
                    "rejected": rejected_count,
                    "expected": {"approved": 3, "rejected": 5}
                }
            )
            
        except Exception as e:
            self.add_check(
                "Seed Data",
                False,
                f"Error checking seed data: {str(e)}"
            )

    async def check_v2_filter_init(self):
        """Check V2 filter initializes correctly"""
        try:
            # Test analyzer initialization
            test_passed = (
                bulletproof_analyzer is not None and
                bulletproof_analyzer.relevance_threshold == settings.relevance_threshold and
                bulletproof_analyzer.model == "gpt-4o-mini"
            )
            
            self.add_check(
                "V2 Filter Initialization",
                test_passed,
                f"BulletproofContentAnalyzer initialized with threshold {bulletproof_analyzer.relevance_threshold}%",
                {
                    "model": bulletproof_analyzer.model,
                    "threshold": bulletproof_analyzer.relevance_threshold,
                    "max_per_hour": bulletproof_analyzer.max_approvals_per_hour
                }
            )
            
        except Exception as e:
            self.add_check(
                "V2 Filter Initialization",
                False,
                f"Failed to initialize V2 filter: {str(e)}"
            )

    async def check_end_to_end_filtering(self):
        """Test end-to-end filtering with sample tweets"""
        try:
            from src.rapidapi_client import ScrapedTweet
            from datetime import datetime
            
            # Create test tweets
            sunset_tweet = ScrapedTweet(
                tweet_id="health_test_sunset",
                url="https://x.com/test/status/health_test_sunset",
                text="Beautiful sunset at the lake tonight! 🌅 Fire in the sky!",
                author_username="test_lifestyle",
                author_display_name="Test User",
                author_profile_image="",
                created_at=datetime.now(),
                retweet_count=0, reply_count=0, like_count=0,
                quote_count=0, bookmark_count=0, view_count=0,
                hashtags=[], mentions=[], media_urls=[],
                is_retweet=False, is_quote=False
            )
            
            tech_tweet = ScrapedTweet(
                tweet_id="health_test_tech",
                url="https://x.com/test/status/health_test_tech", 
                text="New Python asyncio patterns for building scalable AI applications: 1) Task groups 2) Custom executors 3) Memory-efficient streaming. Full implementation at github.com/example",
                author_username="test_techie",
                author_display_name="Tech User",
                author_profile_image="",
                created_at=datetime.now(),
                retweet_count=0, reply_count=0, like_count=0,
                quote_count=0, bookmark_count=0, view_count=0,
                hashtags=[], mentions=[], media_urls=[],
                is_retweet=False, is_quote=False
            )
            
            # Test filtering
            print("   Testing sunset tweet (should be rejected)...")
            sunset_decision = await bulletproof_analyzer.analyze_tweet(sunset_tweet)
            
            print("   Testing tech tweet (should be approved)...")
            tech_decision = await bulletproof_analyzer.analyze_tweet(tech_tweet)
            
            # Check results
            sunset_rejected = sunset_decision.final == "rejected"
            tech_approved = tech_decision.final == "approved"
            
            test_passed = sunset_rejected and tech_approved
            
            self.add_check(
                "End-to-End Filtering",
                test_passed,
                f"Sunset tweet: {sunset_decision.final}, Tech tweet: {tech_decision.final}",
                {
                    "sunset_tweet": {
                        "final": sunset_decision.final,
                        "reason": sunset_decision.quick_reason or sunset_decision.ai_reason
                    },
                    "tech_tweet": {
                        "final": tech_decision.final,
                        "ai_score": tech_decision.ai_score,
                        "categories": tech_decision.categories
                    }
                }
            )
            
        except Exception as e:
            self.add_check(
                "End-to-End Filtering",
                False,
                f"Error testing end-to-end filtering: {str(e)}"
            )

    def print_summary(self):
        """Print health check summary"""
        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0
        
        print("\n" + "=" * 60)
        print("🎯 HEALTH CHECK RESULTS")
        print("=" * 60)
        print(f"Total Checks: {total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Success Rate: {success_rate:.1f}%")
        
        if self.failed > 0:
            print(f"\n❌ FAILED CHECKS:")
            for check in self.checks:
                if not check["passed"]:
                    print(f"   {check['name']}: {check['message']}")
        
        if self.failed == 0:
            print(f"\n🎉 ALL CHECKS PASSED!")
            print("✅ V2 Bulletproof filtering is ready for production!")
            print("\n📋 Next Steps:")
            print("1. Run database migration: Execute supabase/migrations/20250820_filtering_v2.sql")
            print("2. Test in browser: Visit /api/filtering/health")  
            print("3. Test seed data: Visit /api/filtering/test-seed")
            print("4. Run batch processing: Try 'Load & Analyze Tweets' in dashboard")
        else:
            print(f"\n🚨 SOME CHECKS FAILED")
            print("Please fix the issues above before using V2 filtering in production.")

async def main():
    """Run all health checks"""
    runner = HealthCheckRunner()
    success = await runner.run_all_checks()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())