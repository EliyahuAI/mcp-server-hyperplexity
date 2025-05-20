"""Enhanced validator that uses JSON schema to enforce structured API responses."""

import os
from typing import Dict, List, Optional, Tuple, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.console import Console
import pandas as pd
from datetime import datetime, timedelta
import asyncio
import logging
import yaml
import json
import hashlib
import traceback
from .validator import Validator, RateLimiter
from .config import Config, ValidationTarget, ColumnImportance
import re
import time

console = Console()

class SchemaValidator(Validator):
    """Validator that uses JSON schema to enforce structured responses."""
    
    def __init__(self, config: Config, api_key: str, enable_next_check_date: bool = True):
        """Initialize with the same parameters as the parent class."""
        super().__init__(config, api_key, enable_next_check_date)
        
        # Define schemas for different validation types
        self._single_column_schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "quote": {"type": "string"},
                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "update_required": {"type": "boolean"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "explanation": {"type": "string"}
            },
            "required": ["answer", "quote", "confidence", "update_required", "sources", "explanation"]
        }
        
        self._multiplex_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "answer": {"type": "string"},
                    "quote": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "update_required": {"type": "boolean"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "explanation": {"type": "string"}
                },
                "required": ["column", "answer", "quote", "confidence", "sources", "explanation"]
            }
        }
        
        logging.info("Initialized SchemaValidator with JSON schema validation")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _query_perplexity(
        self,
        prompt: str,
        context_url: Optional[str] = None,
        message_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, float, List[str], str, str, str]:
        """Query Perplexity AI with schema enforcement."""
        # Try using the parent class method first, then apply schema validation
        try:
            # Set up a timeout for the API call
            timeout = httpx.Timeout(120.0, connect=30.0)  # 120 second timeout
            
            # Store start time for tracking
            start_time = time.time()
            logging.info(f"Starting Perplexity API call with 120s timeout")
            
            try:
                # Determine if this is a multiplex validation
                is_multiplex = prompt.count("Column:") > 1
                
                # Prepare headers and endpoint
                headers = {
                    "accept": "application/json",
                    "content-type": "application/json",
                    "authorization": f"Bearer {self.api_key}"
                }
                endpoint = "https://api.perplexity.ai/chat/completions"
                
                # Prepare messages
                messages = []
                if message_history:
                    messages.extend(message_history)
                
                # System message with JSON format instructions
                if is_multiplex:
                    system_msg = "You are a data validation expert. Return ONLY a JSON array where each object validates one column. " 
                    system_msg += "Include column, answer, quote, confidence (HIGH/MEDIUM/LOW), sources (array), and explanation fields. Format: "
                    system_msg += '''[
                        {"column": "Column Name", "answer": "validated value", "quote": "supporting quote", "confidence": "HIGH", "sources": ["url1", "url2"], "explanation": "reason"},
                        {"column": "Next Column", "answer": "value", "quote": "quote", "confidence": "MEDIUM", "sources": ["url"], "explanation": "reason"}
                    ]'''
                else:
                    system_msg = "You are a data validation expert. Return ONLY a JSON object with your validation result. "
                    system_msg += "Include answer, quote, confidence (HIGH/MEDIUM/LOW), sources (array), and explanation fields. Format: "
                    system_msg += '''{"answer": "validated value", "quote": "supporting quote", "confidence": "HIGH", "sources": ["url1", "url2"], "explanation": "reason"}'''
                
                # Add context URL to system message if provided
                if context_url:
                    system_msg += f" Use this URL for information: {context_url}"
                    
                # Add system message first
                messages.append({"role": "system", "content": system_msg})
                
                # Then add user prompt
                messages.append({"role": "user", "content": prompt})
                
                # Prepare the API request
                # Try Method 1: Use response_format with json_schema
                schema = self._multiplex_schema if is_multiplex else self._single_column_schema
                payload = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": 0.1,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "schema": schema
                        }
                    }
                }
                
                # Rate limiting
                await self.rate_limiter.acquire()
                
                # Make the API call
                async with httpx.AsyncClient(timeout=timeout) as client:
                    try:
                        response = await client.post(endpoint, headers=headers, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        
                        # Log completion time
                        elapsed = time.time() - start_time
                        logging.info(f"API call completed in {elapsed:.2f} seconds using response_format method")
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 400:
                            # Method 1 failed, try Method 2: Using system prompt to enforce JSON structure
                            logging.warning(f"response_format method failed with 400 error, trying system prompt method")
                            
                            # Build the API request without response_format
                            system_content = f"Return a response ONLY in the following JSON schema format (no markdown formatting, no extra text): {json.dumps(schema)}"
                            
                            # Add context URL to system message if provided
                            if context_url:
                                system_content += f" Use this URL for information: {context_url}"
                                
                            fallback_messages = [
                                {"role": "system", "content": system_content},
                                {"role": "user", "content": prompt}
                            ]
                            
                            payload = {
                                "model": self.model_name,
                                "messages": fallback_messages,
                                "temperature": 0.1
                            }
                            
                            # Make the API call with the fallback method
                            response = await client.post(endpoint, headers=headers, json=payload)
                            response.raise_for_status()
                            data = response.json()
                            
                            # Log completion time for fallback method
                            elapsed = time.time() - start_time
                            logging.info(f"API call completed in {elapsed:.2f} seconds using system prompt method")
                        else:
                            # Re-raise other HTTP errors
                            raise
                    
                    # Extract response text
                    full_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    if not full_response:
                        logging.error("Empty response from Perplexity API")
                        return "Empty response from API", 0.0, [], "LOW", "", ""
                    
                    # Process the structured response
                    if is_multiplex:
                        # For multiplex, return the raw response for validate_row_multiplex to process
                        # Extract JSON from a potentially markdown-formatted response
                        try:
                            if "```json" in full_response:
                                # Extract JSON from code block
                                json_start = full_response.find("```json") + 7
                                json_end = full_response.find("```", json_start)
                                if json_end > json_start:
                                    json_text = full_response[json_start:json_end].strip()
                                    parsed_data = json.loads(json_text)
                                    logging.info(f"Successfully extracted JSON from markdown code block")
                            elif "```" in full_response:
                                # Extract from generic code block
                                json_start = full_response.find("```") + 3
                                json_end = full_response.find("```", json_start)
                                if json_end > json_start:
                                    json_text = full_response[json_start:json_end].strip()
                                    parsed_data = json.loads(json_text)
                                    logging.info(f"Successfully extracted JSON from generic code block")
                            else:
                                # Try direct JSON parsing
                                parsed_data = json.loads(full_response.strip())
                                logging.info(f"Successfully parsed direct JSON response")
                            
                            # Store in cache
                            self.cache.set("perplexity_schema_raw", self.model_name, prompt, parsed_data, context_url)
                        except json.JSONDecodeError as e:
                            logging.error(f"JSON decode error: {e}")
                            logging.error(f"Raw response: {full_response[:500]}...")
                            parsed_data = []
                        
                        # Return an intermediate response - the actual processing is done in validate_row_multiplex
                        return full_response, 0.9, [], "HIGH", "", ""
                    else:
                        # For single column, process the structured response
                        try:
                            # Extract JSON from a potentially markdown-formatted response
                            if "```json" in full_response:
                                # Extract JSON from code block
                                json_start = full_response.find("```json") + 7
                                json_end = full_response.find("```", json_start)
                                if json_end > json_start:
                                    result = json.loads(full_response[json_start:json_end].strip())
                            elif "```" in full_response:
                                # Extract from generic code block
                                json_start = full_response.find("```") + 3
                                json_end = full_response.find("```", json_start)
                                if json_end > json_start:
                                    result = json.loads(full_response[json_start:json_end].strip())
                            else:
                                # Try direct JSON parsing
                                result = json.loads(full_response.strip())
                            
                            # Extract fields
                            answer = result.get("answer", "")
                            quote = result.get("quote", "")
                            confidence_level = result.get("confidence", "LOW")
                            sources = result.get("sources", [])
                            
                            # Map confidence level to numeric value
                            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                            numeric_confidence = confidence_map.get(confidence_level, 0.5)
                            
                            # Get main source if available
                            main_source = sources[0] if sources else ""
                            
                            return answer, numeric_confidence, sources, confidence_level, quote, main_source
                        except json.JSONDecodeError as e:
                            logging.error(f"JSON decode error: {e}")
                            logging.error(f"Raw response: {full_response[:500]}...")
                            # Fall back to using the raw response
                            return full_response, 0.5, [], "LOW", "", ""
            
            except asyncio.TimeoutError:
                logging.error(f"API call timed out after 120 seconds")
                return "API call timed out, please try again later", 0.0, [], "LOW", "", ""
            except json.JSONDecodeError as je:
                logging.error(f"JSON decoding error: {je}")
                logging.error(f"Raw response: {full_response[:500]}...")
                return f"JSON parsing error: {str(je)}", 0.0, [], "LOW", "", ""
            except httpx.HTTPError as he:
                logging.error(f"HTTP error: {he}")
                return f"API connection error: {str(he)}", 0.0, [], "LOW", "", ""
            
        except Exception as e:
            logging.error(f"Error in SchemaValidator._query_perplexity: {e}")
            logging.error(f"Error details: {traceback.format_exc()}")
            return "API error: " + str(e), 0.5, [], "LOW", "", ""
    
    async def validate_row_multiplex(
        self,
        row: pd.Series,
        targets: List[ValidationTarget],
    ) -> Dict[str, Tuple[Optional[str], float, List[str], str]]:
        """Validate multiple columns for a row grouped by search_group using JSON schema."""
        # Group columns by search_group
        grouped_columns = self._group_columns_by_search_group(targets)
        logging.info(f"Grouped {len(targets)} columns into {len(grouped_columns)} search groups")
        
        # Initialize results and statistics
        results = {}
        multiplex_groups = 0
        individual_validations = 0
        
        # Process each group separately
        for search_group, group_targets in grouped_columns.items():
            if len(group_targets) == 1:
                # If only one column in the group, use regular validation
                target = group_targets[0]
                value = row[target.column]
                if pd.isna(value):
                    results[target.column] = (None, 0.0, [], "LOW")
                    continue
                    
                answer, confidence, citations, confidence_level, quote, main_source = await self.validate_row(row, target)
                results[target.column] = (answer, confidence, citations, confidence_level)
                individual_validations += 1
            else:
                # For multiple columns, use multiplex validation with schema
                logging.info(f"Multiplex validating search group {search_group} with {len(group_targets)} columns")
                multiplex_groups += 1
                
                # Build multiplex prompt
                prompt, website_url = self._build_multiplex_prompt(row, group_targets)
                prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:10]
                
                try:
                    # Use consistent API name for caching
                    api_name = "perplexity_schema_raw"
                    
                    # Check for cached results 
                    cached_result = self.cache.get(api_name, self.model_name, prompt, website_url)
                    
                    if not cached_result:
                        logging.info(f"No cached multiplex result found with hash {prompt_hash}, querying API...")
                        
                        # Call API with json_schema response format - this should return already structured JSON
                        response_json, _, _, _, _, _ = await self._query_perplexity(prompt, website_url, None)
                        
                        # Since we're using json_schema response_format in the API call,
                        # we should get a properly formatted JSON response directly
                        try:
                            # Parse the JSON response if it's a string
                            if isinstance(response_json, str):
                                cached_result = json.loads(response_json)
                                logging.info(f"Successfully parsed JSON response with {len(cached_result)} items")
                            else:
                                # If it's already parsed (our _query_perplexity might have done this)
                                cached_result = response_json
                                
                            # Ensure we have a valid array
                            if not isinstance(cached_result, list):
                                logging.error(f"Expected array response, got {type(cached_result)}")
                                cached_result = []
                        except json.JSONDecodeError as je:
                            logging.error(f"Failed to parse multiplex JSON response: {je}")
                            cached_result = []
                    else:
                        logging.info(f"Using cached multiplex result with hash {prompt_hash}")
                    
                    if not cached_result:
                        logging.error(f"No valid result available after API call for multiplex group {search_group}")
                        # Fall back to individual validation for this group
                        logging.info(f"Falling back to individual validation for search group {search_group}")
                        for target in group_targets:
                            try:
                                # Try individual validation as fallback
                                column = target.column
                                logging.info(f"Individually validating {column} as fallback")
                                indiv_answer, indiv_confidence, indiv_citations, indiv_confidence_level, _, _ = await self.validate_row(row, target)
                                results[column] = (indiv_answer, indiv_confidence, indiv_citations, indiv_confidence_level)
                            except Exception as indiv_err:
                                logging.error(f"Individual validation fallback also failed for {target.column}: {indiv_err}")
                                results[target.column] = (None, 0.0, [], "LOW")
                        continue
                    
                    # Debug log the cached result structure
                    logging.info(f"Processing array response with {len(cached_result)} items")
                    
                    # Process each column's result
                    processed_columns = []
                    for column_result in cached_result:
                        if not isinstance(column_result, dict):
                            logging.error(f"Expected dict for column result, got {type(column_result)}")
                            continue
                            
                        column_name = column_result.get('column')
                        if not column_name:
                            logging.error(f"Missing column name in result: {column_result.keys()}")
                            continue
                            
                        processed_columns.append(column_name)
                        
                        # Extract data from the result
                        column_answer = column_result.get('answer', '')
                        column_confidence = column_result.get('confidence', 'LOW')
                        column_sources = column_result.get('sources', [])
                        column_quote = column_result.get('quote', '')
                        
                        # Map confidence level to numeric value
                        confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                        numeric_confidence = confidence_map.get(column_confidence, 0.5)
                        
                        # Store the result with quote if available
                        source_url = column_sources[0] if column_sources and len(column_sources) > 0 else ""
                        
                        # Store in standard format for validator.py but include quote and source_url
                        # This expands the return format to (answer, confidence, citations, confidence_level, quote, source_url)
                        results[column_name] = (column_answer, numeric_confidence, column_sources, column_confidence, column_quote, source_url)
                        
                        # Log the result with quote preview
                        quote_preview = f" | Quote: {column_quote[:30]}..." if column_quote else ""
                        logging.info(f"Processed multiplex result for {column_name}: {column_answer[:30]}...{quote_preview} (confidence: {column_confidence})")
                    
                    # Check for missing columns that should have been in the result
                    target_columns = [t.column for t in group_targets]
                    missing_columns = set(target_columns) - set(processed_columns)
                    if missing_columns:
                        logging.warning(f"Missing columns in multiplex result: {missing_columns}")
                        for column in missing_columns:
                            results[column] = (None, 0.0, [], "LOW")
                        
                except Exception as e:
                    logging.error(f"Error in schema multiplex validation for search group {search_group}: {e}")
                    logging.error(f"Traceback: {traceback.format_exc()}")
                    
                    # Set default values for all columns in this group
                    for target in group_targets:
                        results[target.column] = (None, 0.0, [], "LOW")
        
        # Update run_log statistics
        return results, multiplex_groups, individual_validations
    
    async def validate_row(
        self,
        row: pd.Series,
        target: ValidationTarget,
    ) -> Tuple[Optional[str], float, List[str], str, str, str]:
        """Validate a single cell using AI with schema enforcement."""
        # Skip validation for ignored columns
        if target.importance == ColumnImportance.IGNORED:
            return row[target.column], 1.0, [], "HIGH", "", ""

        # Check if recheck is needed
        if not self.config.recheck.force_recheck:
            last_check = row.get("Last Check")
            next_check = row.get("Next Check Date")
            if next_check and isinstance(next_check, datetime):
                if datetime.now() < next_check:
                    logging.info(f"Skipping validation for {target.column} - next check not due until {next_check}")
                    return row[target.column], 1.0, [], "HIGH", "", ""  # Skip validation if not due for recheck
        
        try:
            prompt, website_url = self._build_prompt(row, target)
            answer, confidence, citations, confidence_level, quote, main_source = await self._query_perplexity(
                prompt, website_url, None
            )
            
            if not answer or (isinstance(answer, str) and answer.strip() == ""):
                logging.error(f"Empty answer received for prompt: {prompt}")
                return None, 0.0, [], "LOW", "", ""
                
            return answer, confidence, citations, confidence_level, quote, main_source
        except Exception as e:
            logging.error(f"Failed to perform web search: {e}")
            logging.error(f"Exception details: {traceback.format_exc()}")
            return None, 0.0, [], "LOW", "", "" 