#!/usr/bin/env python3
"""
Golden Sample Tests for Bulletproof Content Analyzer V2

Tests the exact filtering scenarios from the requirements to ensure 
no regressions and proper rejection/approval behavior.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.content_analyzer_v2 import bulletproof_analyzer
from src.rapidapi_client import ScrapedTweet

class FilteringTestSuite:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def create_mock_tweet(self, tweet_id: str, text: str, author: str = "testuser") -> ScrapedTweet:
        """Create a mock tweet for testing"""
        return ScrapedTweet(
            tweet_id=tweet_id,
            url=f"https://x.com/{author}/status/{tweet_id}",
            text=text,
            author_username=author,
            author_display_name=f"Test {author}",
            author_profile_image="",
            created_at=datetime.now(),
            retweet_count=0,
            reply_count=0,
            like_count=0,
            quote_count=0,
            bookmark_count=0,
            view_count=0,
            hashtags=[],
            mentions=[],
            media_urls=[],
            is_retweet=False,
            is_quote=False
        )
    
    async def test_golden_rejects(self):
        """Test tweets that MUST be rejected"""
        print("🔴 Testing Golden Rejects (must fail)")
        
        test_cases = [
            {
                "id": "reject_1",
                "text": "sunset at the lake with family 🎣",
                "expected_reason": "blacklist_keyword",
                "description": "Lifestyle content with blacklisted keywords"
            },
            {
                "id": "reject_2", 
                "text": "RT Beautiful sunset tonight! Amazing view from my hotel balcony",
                "expected_reason": "retweet_no_tech",
                "description": "Retweet without tech hints"
            },
            {
                "id": "reject_3",
                "text": "AI will change everything!!!",
                "expected_reason": "ai_reject",
                "description": "Vague AI hype without substance"
            },
            {
                "id": "reject_4",
                "text": "Check this out https://example.com #AI #ML #Tech #Amazing #Wow #Cool #Nice #Great #Awesome #Perfect",
                "expected_reason": "hashtag_spam",
                "description": "Link with excessive hashtags"
            },
            {
                "id": "reject_5",
                "text": "Hermosa puesta de sol en la playa",
                "expected_reason": "no_tech_hints",
                "description": "Non-English lifestyle content"
            },
            {
                "id": "reject_6",
                "text": "Going to bed, good night everyone! 😴",
                "expected_reason": "blacklist_keyword",
                "description": "Social pleasantries"
            }
        ]
        
        for test_case in test_cases:
            tweet = self.create_mock_tweet(test_case["id"], test_case["text"])
            decision = await bulletproof_analyzer.analyze_tweet(tweet)
            
            if decision.final == "rejected":
                print(f"   ✅ {test_case['id']}: REJECTED ({decision.quick_reason or decision.ai_reason}) - {test_case['description']}")
                self.passed += 1
            else:
                print(f"   ❌ {test_case['id']}: APPROVED (should be rejected!) - {test_case['description']}")
                self.failed += 1
            
            self.results.append({
                "test": test_case["id"],
                "expected": "rejected",
                "actual": decision.final,
                "reason": decision.quick_reason or decision.ai_reason,
                "passed": decision.final == "rejected"
            })
    
    async def test_golden_approvals(self):
        """Test tweets that MUST be approved"""
        print("\n🟢 Testing Golden Approvals (must pass)")
        
        test_cases = [
            {
                "id": "approve_1",
                "text": "New AI agents can now automatically open GitHub PRs with full test coverage and documentation. Here's the technical architecture: 1) Code analysis with AST parsing 2) Test generation via LLM 3) CI/CD integration. Built with Python, FastAPI, OpenAI API.",
                "description": "Technical implementation with concrete details"
            },
            {
                "id": "approve_2", 
                "text": "Cursor IDE vs GitHub Copilot: Performance comparison on real codebases. Cursor: 89% completion accuracy, 3.2s response time. Copilot: 76% accuracy, 1.8s response. Tested on React, Python, Go projects. Cursor wins for complex refactoring tasks.",
                "description": "Technical comparison with metrics"
            },
            {
                "id": "approve_3",
                "text": "Tutorial: Building a RAG system with vector embeddings. Step 1: Document chunking (512 tokens). Step 2: Generate embeddings (OpenAI text-embedding-3-large). Step 3: Vector DB (Pinecone/Weaviate). Step 4: Retrieval + LLM synthesis. Full code: github.com/example",
                "description": "Technical tutorial with implementation steps"
            },
            {
                "id": "approve_4",
                "text": "Supabase just released real-time vector similarity search. Game-changer for AI apps. Now you can do semantic search directly in PostgreSQL with pgvector extension. 100x faster than external vector DBs for most use cases.",
                "description": "Technical tool announcement with specifics"
            }
        ]
        
        for test_case in test_cases:
            tweet = self.create_mock_tweet(test_case["id"], test_case["text"])
            decision = await bulletproof_analyzer.analyze_tweet(tweet)
            
            if decision.final == "approved":
                score = decision.ai_score or 0
                print(f"   ✅ {test_case['id']}: APPROVED ({score}%) - {test_case['description']}")
                self.passed += 1
            else:
                print(f"   ❌ {test_case['id']}: REJECTED (should be approved!) - {test_case['description']}")
                print(f"      Reason: {decision.quick_reason or decision.ai_reason}")
                self.failed += 1
            
            self.results.append({
                "test": test_case["id"],
                "expected": "approved",
                "actual": decision.final,
                "reason": decision.quick_reason or decision.ai_reason,
                "ai_score": decision.ai_score,
                "passed": decision.final == "approved"
            })
    
    async def test_edge_cases(self):
        """Test edge cases and boundary conditions"""
        print("\n🟡 Testing Edge Cases")
        
        test_cases = [
            {
                "id": "edge_1",
                "text": "QT: 'Vector database performance improvements with 10x faster similarity search' → This changes everything for RAG applications!",
                "description": "Quote tweet with substantive quoted content",
                "expected": "approved",
                "author": "edge_user_1"
            },
            {
                "id": "edge_2",
                "text": "Just shipped a new feature using Next.js, Supabase, and OpenAI API 🚀 Building AI-powered web applications with real-time vector search",
                "description": "Technical implementation with emoji",
                "expected": "approved",
                "author": "edge_user_2"
            },
            {
                "id": "edge_3",
                "text": "RT @openai GPT-4o is now available with vision capabilities and 50% cost reduction for API usage",
                "description": "Retweet of technical news",
                "expected": "approved",
                "author": "edge_user_3"
            },
            {
                "id": "edge_4",
                "text": "AI",  # Very short
                "description": "Extremely short tweet",
                "expected": "rejected",
                "author": "edge_user_4"
            }
        ]
        
        for test_case in test_cases:
            author = test_case.get("author", "testuser") 
            tweet = self.create_mock_tweet(test_case["id"], test_case["text"], author)
            decision = await bulletproof_analyzer.analyze_tweet(tweet)
            
            expected_result = test_case["expected"]
            actual_result = decision.final
            passed = expected_result == actual_result
            
            status = "✅" if passed else "❌"
            score = f" ({decision.ai_score}%)" if decision.ai_score else ""
            print(f"   {status} {test_case['id']}: {actual_result.upper()}{score} - {test_case['description']}")
            
            if not passed:
                print(f"      Expected: {expected_result}, Got: {actual_result}")
                print(f"      Reason: {decision.quick_reason or decision.ai_reason}")
            
            if passed:
                self.passed += 1
            else:
                self.failed += 1
            
            self.results.append({
                "test": test_case["id"],
                "expected": expected_result,
                "actual": actual_result,
                "reason": decision.quick_reason or decision.ai_reason,
                "ai_score": decision.ai_score,
                "passed": passed
            })
    
    async def test_rate_limiting(self):
        """Test rate limiting functionality"""
        print("\n⏱️  Testing Rate Limiting")
        
        # Create multiple tweets from same author
        author = "prolific_tweeter"
        tweets = []
        for i in range(5):
            tweet = self.create_mock_tweet(
                f"rate_test_{i}",
                f"Advanced MLOps pipeline deployment #{i}: Kubernetes + Docker + MLflow for model versioning and monitoring in production environments.",
                author
            )
            tweets.append(tweet)
        
        approved_count = 0
        rate_limited_count = 0
        
        for tweet in tweets:
            decision = await bulletproof_analyzer.analyze_tweet(tweet)
            
            if decision.final == "approved":
                approved_count += 1
            elif "limit" in (decision.ai_reason or ""):
                rate_limited_count += 1
        
        # Should have some rate limiting after max_per_author_6h tweets
        max_per_author = bulletproof_analyzer.max_per_author_6h
        print(f"   Approved: {approved_count}, Rate Limited: {rate_limited_count}")
        print(f"   Max per author (6h): {max_per_author}")
        
        if approved_count <= max_per_author:
            print("   ✅ Rate limiting working correctly")
            self.passed += 1
        else:
            print("   ❌ Rate limiting not enforced")
            self.failed += 1
    
    async def test_threshold_enforcement(self):
        """Test threshold enforcement"""
        print("\n🎯 Testing Threshold Enforcement")
        
        # Test with different thresholds
        original_threshold = bulletproof_analyzer.relevance_threshold
        
        # Borderline technical content
        tweet = self.create_mock_tweet(
            "threshold_test",
            "AI is pretty cool and might be useful for some things in the future maybe"
        )
        
        try:
            # Test with high threshold (should reject)
            bulletproof_analyzer.relevance_threshold = 90.0
            decision_high = await bulletproof_analyzer.analyze_tweet(tweet)
            
            # Test with low threshold (might approve)
            bulletproof_analyzer.relevance_threshold = 30.0
            decision_low = await bulletproof_analyzer.analyze_tweet(tweet)
            
            print(f"   High threshold (90%): {decision_high.final} (score: {decision_high.ai_score}%)")
            print(f"   Low threshold (30%): {decision_low.final} (score: {decision_low.ai_score}%)")
            
            # Should be more restrictive with higher threshold
            if decision_high.final == "rejected":
                print("   ✅ High threshold correctly rejects borderline content")
                self.passed += 1
            else:
                print("   ❌ High threshold should reject borderline content")
                self.failed += 1
                
        finally:
            # Restore original threshold
            bulletproof_analyzer.relevance_threshold = original_threshold
    
    def print_summary(self):
        """Print test summary"""
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"🎯 BULLETPROOF FILTER TEST RESULTS")
        print(f"{'='*60}")
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ✅")
        print(f"Failed: {self.failed} ❌")
        print(f"Pass Rate: {pass_rate:.1f}%")
        
        if self.failed > 0:
            print(f"\n❌ FAILED TESTS:")
            for result in self.results:
                if not result["passed"]:
                    print(f"   {result['test']}: Expected {result['expected']}, got {result['actual']} ({result['reason']})")
        
        print(f"\n🎖️  {'ALL TESTS PASSED!' if self.failed == 0 else 'SOME TESTS FAILED - CHECK FILTERING LOGIC'}")
        
        return self.failed == 0

async def main():
    """Run all filtering tests"""
    print("🚀 Bulletproof Content Analyzer V2 - Golden Sample Tests")
    print("=" * 60)
    
    suite = FilteringTestSuite()
    
    # Run all test suites
    await suite.test_golden_rejects()
    await suite.test_golden_approvals() 
    await suite.test_edge_cases()
    await suite.test_rate_limiting()
    await suite.test_threshold_enforcement()
    
    # Print final results
    all_passed = suite.print_summary()
    
    # Exit code for CI/CD
    sys.exit(0 if all_passed else 1)

if __name__ == "__main__":
    asyncio.run(main())