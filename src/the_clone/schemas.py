#!/usr/bin/env python3
"""
JSON schemas for Perplexity Clone structured responses.
Defines all schemas used for search term generation, result evaluation, and synthesis.
"""

from typing import Dict, Any


def get_search_generation_schema() -> Dict[str, Any]:
    """
    Schema for initial search term generation and settings.
    Used by the search management model to generate optimal search queries.
    """
    return {
        "type": "object",
        "properties": {
            "search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optimized search queries for the Perplexity Search API"
            },
            "search_settings": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of results per search (1-20)"
                    },
                    "search_recency_filter": {
                        "type": "string",
                        "enum": ["", "day", "week", "month", "year"],
                        "description": "Filter by recency. MUST be one of: '' (no filter), 'day', 'week', 'month', 'year'. Do NOT use years like '2024'!"
                    }
                },
                "description": "Settings for Perplexity Search API"
            },
            "reasoning": {
                "type": "string",
                "description": "Explanation of search strategy and term selection"
            }
        },
        "required": ["search_terms", "search_settings", "reasoning"]
    }


def get_result_evaluation_schema() -> Dict[str, Any]:
    """
    Schema for evaluating search results and determining next steps.
    Simplified for minimal token usage - quick checks only.
    Includes source reliability assessment.
    """
    return {
        "type": "object",
        "properties": {
            "relevant_count": {
                "type": "integer",
                "description": "Number of relevant results found"
            },
            "high_reliability_count": {
                "type": "integer",
                "description": "Number of HIGH reliability sources (academic, official docs, established institutions)"
            },
            "medium_reliability_count": {
                "type": "integer",
                "description": "Number of MEDIUM reliability sources (tech blogs, news sites, industry pubs)"
            },
            "low_reliability_count": {
                "type": "integer",
                "description": "Number of LOW reliability sources (forums, user content, unclear sources)"
            },
            "best_source_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "0-indexed positions of sources to use (max 10-12). Prioritize sources that: 1) Are highly relevant (early in results list), 2) Have good reliability, 3) Provide unique information not duplicated elsewhere. Filter out redundant sources covering the same facts."
            },
            "has_sufficient_info": {
                "type": "boolean",
                "description": "True if we have at least 1 HIGH reliability source OR 3+ MEDIUM sources"
            },
            "missing_aspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific missing aspects (if has_sufficient_info=false)"
            },
            "next_search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search terms to fill gaps (empty if sufficient)"
            }
        },
        "required": ["relevant_count", "high_reliability_count", "medium_reliability_count", "best_source_indices", "has_sufficient_info"]
    }


def get_synthesis_schema() -> Dict[str, Any]:
    """
    Schema for final answer synthesis with structured JSON output.
    Returns format similar to Sonar Pro with cited facts AND extracted snippets.
    """
    return {
        "type": "object",
        "properties": {
            "comparison": {
                "type": "object",
                "description": "Structured comparison organized by topics/aspects",
                "additionalProperties": True
            },
            "key_facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "fact": {"type": "string", "description": "Direct quote or close paraphrase from the citation snippet"},
                        "citation_index": {"type": "integer", "description": "Citation number (1-indexed) - use ONLY indices from provided list"},
                        "relevance": {"type": "string", "description": "Why this fact matters for the query"}
                    }
                },
                "description": "Key facts extracted from provided sources - use citation indices ONLY"
            },
            "citation_snippets": {
                "type": "object",
                "description": "Extracted snippets for each citation (key: citation index, value: short snippet)",
                "additionalProperties": {"type": "string"},
                "example": {
                    "1": "DeepSeek-V3 uses 671B parameters with MoE architecture",
                    "2": "Claude Opus 4 achieves 72.5% on SWE-bench coding tasks"
                }
            }
        },
        "required": ["comparison", "key_facts", "citation_snippets"]
    }


def get_qc_assessment_schema() -> Dict[str, Any]:
    """
    Schema for QC (Quality Check) assessment of Sonar output.
    Determines if Sonar's answer is sufficient or needs refinement.
    """
    return {
        "type": "object",
        "properties": {
            "is_sufficient": {
                "type": "boolean",
                "description": "True if Sonar's answer adequately addresses the query"
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence in answer quality and completeness"
            },
            "missing_aspects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific aspects or topics missing from the answer"
            },
            "domain_expansions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "description": "Domain to search (e.g., 'arxiv.org')"},
                        "query": {"type": "string", "description": "Specific query for this domain"},
                        "reason": {"type": "string", "description": "Why expand this domain"}
                    }
                },
                "description": "Domains to search more deeply (preferred if Sonar found good sources)"
            },
            "new_search_terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "New search terms for missing topics (if domain expansion insufficient)"
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of assessment and recommendations"
            }
        },
        "required": ["is_sufficient", "confidence", "reasoning"]
    }


def get_direct_synthesis_schema() -> Dict[str, Any]:
    """
    Schema for direct answer synthesis without search (max_iterations=0).
    Used when generating answers from model knowledge without external sources.
    """
    return {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Direct answer based on model knowledge (no citations)"
            },
            "limitations": {
                "type": "string",
                "description": "Acknowledgment of knowledge cutoff or uncertainty if applicable"
            }
        },
        "required": ["answer"]
    }
