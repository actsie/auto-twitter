#!/usr/bin/env python3
"""
Twitter Auto Bot - Reply Comparison Logic

Handles comparison of AI-generated replies against recent user replies 
to prevent repetitive or similar content.
"""

import re
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher
from dataclasses import dataclass

from .rapidapi_client import UserReply
from .ai_reply_generator import GeneratedReply
from .logger import logger


@dataclass
class SimilarityResult:
    """Result of similarity comparison"""
    is_similar: bool
    similarity_score: float
    similar_to_reply_id: str
    reason: str


class ReplyComparator:
    """Handles comparison logic for reply deduplication and similarity detection"""
    
    def __init__(self):
        self.similarity_threshold = 0.7  # 70% similarity threshold
        self.keyword_weight = 0.3  # Weight for keyword similarity
        self.structure_weight = 0.4  # Weight for structural similarity
        self.semantic_weight = 0.3  # Weight for semantic similarity
    
    def compare_against_recent_replies(self, generated_reply: GeneratedReply, 
                                     recent_replies: List[UserReply]) -> SimilarityResult:
        """
        Compare a generated reply against recent user replies
        
        Args:
            generated_reply: AI-generated reply to check
            recent_replies: List of recent user replies to compare against
            
        Returns:
            SimilarityResult indicating if the reply is too similar
        """
        logger.info(f"Comparing generated reply against {len(recent_replies)} recent replies")
        
        if not recent_replies:
            return SimilarityResult(
                is_similar=False,
                similarity_score=0.0,
                similar_to_reply_id="",
                reason="No recent replies to compare against"
            )
        
        highest_similarity = 0.0
        most_similar_reply_id = ""
        similarity_reason = ""
        
        for user_reply in recent_replies:
            similarity_score = self._calculate_similarity(generated_reply.text, user_reply.text)
            
            if similarity_score > highest_similarity:
                highest_similarity = similarity_score
                most_similar_reply_id = user_reply.tweet_id
                similarity_reason = self._get_similarity_reason(similarity_score)
        
        is_too_similar = highest_similarity >= self.similarity_threshold
        
        if is_too_similar:
            logger.warning(f"Generated reply too similar ({highest_similarity:.2f}) to recent reply {most_similar_reply_id}")
        else:
            logger.info(f"Generated reply acceptable (max similarity: {highest_similarity:.2f})")
        
        return SimilarityResult(
            is_similar=is_too_similar,
            similarity_score=highest_similarity,
            similar_to_reply_id=most_similar_reply_id,
            reason=similarity_reason
        )
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity score between two reply texts using multiple methods
        
        Args:
            text1: First text to compare
            text2: Second text to compare
            
        Returns:
            Float similarity score between 0.0 and 1.0
        """
        # Normalize texts
        norm_text1 = self._normalize_text(text1)
        norm_text2 = self._normalize_text(text2)
        
        # Calculate different similarity metrics
        sequence_similarity = self._sequence_similarity(norm_text1, norm_text2)
        keyword_similarity = self._keyword_similarity(norm_text1, norm_text2)
        structure_similarity = self._structure_similarity(norm_text1, norm_text2)
        
        # Weighted combination
        total_similarity = (
            sequence_similarity * self.semantic_weight +
            keyword_similarity * self.keyword_weight +
            structure_similarity * self.structure_weight
        )
        
        return min(1.0, total_similarity)
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        # Convert to lowercase
        text = text.lower()
        
        # Remove URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        
        # Remove mentions and hashtags for comparison (but keep the content)
        text = re.sub(r'[@#](\w+)', r'\\1', text)
        
        # Remove extra whitespace and punctuation for core comparison
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _sequence_similarity(self, text1: str, text2: str) -> float:
        """Calculate sequence similarity using difflib"""
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _keyword_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity based on common keywords"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        # Filter out common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'this', 'that', 'these', 'those'}
        words1 = words1 - stop_words
        words2 = words2 - stop_words
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def _structure_similarity(self, text1: str, text2: str) -> float:
        """Calculate structural similarity (length, question marks, etc.)"""
        similarity_factors = []
        
        # Length similarity
        len1, len2 = len(text1), len(text2)
        length_similarity = 1.0 - abs(len1 - len2) / max(len1, len2, 1)
        similarity_factors.append(length_similarity)
        
        # Question mark presence
        has_question1 = '?' in text1
        has_question2 = '?' in text2
        question_similarity = 1.0 if has_question1 == has_question2 else 0.0
        similarity_factors.append(question_similarity)
        
        # Exclamation mark presence
        has_exclamation1 = '!' in text1
        has_exclamation2 = '!' in text2
        exclamation_similarity = 1.0 if has_exclamation1 == has_exclamation2 else 0.0
        similarity_factors.append(exclamation_similarity)
        
        # Sentence count similarity
        sentences1 = len([s for s in text1.split('.') if s.strip()])
        sentences2 = len([s for s in text2.split('.') if s.strip()])
        sentence_similarity = 1.0 - abs(sentences1 - sentences2) / max(sentences1, sentences2, 1)
        similarity_factors.append(sentence_similarity)
        
        return sum(similarity_factors) / len(similarity_factors)
    
    def _get_similarity_reason(self, similarity_score: float) -> str:
        """Get human-readable reason for similarity score"""
        if similarity_score >= 0.9:
            return "Nearly identical content"
        elif similarity_score >= 0.8:
            return "Very similar wording and structure"
        elif similarity_score >= 0.7:
            return "Similar theme and approach"
        elif similarity_score >= 0.5:
            return "Some similarities detected"
        else:
            return "Different content"
    
    def filter_similar_replies(self, generated_replies: List[GeneratedReply], 
                             recent_replies: List[UserReply]) -> Tuple[List[GeneratedReply], List[Dict[str, Any]]]:
        """
        Filter out generated replies that are too similar to recent replies
        
        Args:
            generated_replies: List of AI-generated replies
            recent_replies: List of recent user replies
            
        Returns:
            Tuple of (filtered_replies, similarity_reports)
        """
        filtered_replies = []
        similarity_reports = []
        
        for reply in generated_replies:
            similarity_result = self.compare_against_recent_replies(reply, recent_replies)
            
            similarity_report = {
                "reply_id": reply.id,
                "reply_text": reply.text,
                "is_similar": similarity_result.is_similar,
                "similarity_score": similarity_result.similarity_score,
                "similar_to_reply_id": similarity_result.similar_to_reply_id,
                "reason": similarity_result.reason
            }
            similarity_reports.append(similarity_report)
            
            if not similarity_result.is_similar:
                filtered_replies.append(reply)
            else:
                logger.info(f"Filtered out similar reply: {reply.text[:50]}...")
        
        logger.info(f"Filtered {len(generated_replies) - len(filtered_replies)} similar replies out of {len(generated_replies)}")
        
        return filtered_replies, similarity_reports
    
    def get_diversity_score(self, replies: List[GeneratedReply]) -> float:
        """
        Calculate diversity score for a set of generated replies
        
        Args:
            replies: List of generated replies
            
        Returns:
            Float diversity score between 0.0 and 1.0 (higher = more diverse)
        """
        if len(replies) <= 1:
            return 1.0
        
        total_similarity = 0.0
        comparisons = 0
        
        for i in range(len(replies)):
            for j in range(i + 1, len(replies)):
                similarity = self._calculate_similarity(replies[i].text, replies[j].text)
                total_similarity += similarity
                comparisons += 1
        
        average_similarity = total_similarity / comparisons if comparisons > 0 else 0.0
        diversity_score = 1.0 - average_similarity
        
        return max(0.0, min(1.0, diversity_score))


# Global comparator instance
reply_comparator = ReplyComparator()