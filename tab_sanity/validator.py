"""AI-powered validation functionality."""

import os
from typing import Dict, List, Optional, Tuple
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.console import Console
from rich.progress import Progress
import pandas as pd
from datetime import datetime, timedelta
import asyncio
from .config import Config, ValidationTarget, ColumnImportance
import logging
import yaml
from .cache import PerplexityCache
import re
import traceback
import hashlib
import requests
import json
import csv

console = Console()

class RateLimiter:
    """Rate limiter for API calls."""
    def __init__(self, calls_per_minute: int = 49):  # limit to stay under 50 RPM
        self.calls_per_minute = calls_per_minute
        self.interval = 60.0 / calls_per_minute
        self.last_call = 0.0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self.last_call
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self.last_call = asyncio.get_event_loop().time()

class Validator:
    """Handles AI-powered validation of table data."""
    
    def __init__(self, config: Config, api_key: str, enable_next_check_date: bool = True):
        self.config = config
        self.api_key = api_key
        self.enable_next_check_date = enable_next_check_date
        # Set cache directory to be inside the table's directory
        table_dir = os.path.dirname(config.spreadsheet)
        cache_dir = os.path.join(table_dir, ".perplexity_cache")
        self.cache = PerplexityCache(cache_dir=cache_dir)
        
        # Load column configuration
        config_path = os.path.join(table_dir, "column_config.yml")
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            self.column_config = config_data['columns']
            # Get model name from config or use default
            self.model_name = config_data.get('model_name', 'sonar-pro')
            logging.info(f"Using model: {self.model_name}")
        
        self.prompts = self._load_prompts()
        
        # Clear old cache entries on startup
        self.cache.clear_old_entries()
        
        self.rate_limiter = RateLimiter()
        
    def _load_prompts(self) -> Dict[str, str]:
        """Load prompt templates from the prompts file."""
        prompts = {}
        try:
            # Try loading YAML format first (preferred)
            prompts_yml_path = os.path.join(os.path.dirname(__file__), "prompts.yml")
            if os.path.exists(prompts_yml_path):
                logging.info(f"Loading prompts from YAML file: {prompts_yml_path}")
                with open(prompts_yml_path, 'r', encoding='utf-8') as f:
                    prompts = yaml.safe_load(f)
                
            # Fall back to CSV if YAML doesn't exist
            else:
                prompts_csv_path = os.path.join(os.path.dirname(__file__), "prompts.csv")
                if os.path.exists(prompts_csv_path):
                    logging.info(f"Loading prompts from CSV file: {prompts_csv_path}")
                    with open(prompts_csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.reader(f, delimiter='|')
                        next(reader)  # Skip header
                        for row in reader:
                            if len(row) >= 3:
                                prompts[row[0]] = row[2]
                else:
                    logging.warning("No prompts file found. Using default prompts.")
                
            # Apply any prompt overrides from config
            if hasattr(self.config, "prompts") and isinstance(self.config.prompts, dict):
                prompts.update(self.config.prompts)
            
        except Exception as e:
            logging.error(f"Error loading prompts: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
        
        # Log available prompts
        logging.info(f"Loaded {len(prompts)} prompt templates: {', '.join(prompts.keys())}")
        return prompts

    def _load_column_config(self) -> Dict:
        """Load column configuration from YAML file."""
        try:
            # Get the directory containing the spreadsheet
            table_dir = os.path.dirname(self.config.spreadsheet)
            config_path = os.path.join(table_dir, "column_config.yml")
            
            # Load column configuration
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)['columns']
        except Exception as e:
            logging.error(f"Failed to load column config: {e}")
            return {}

    def _get_general_notes(self) -> str:
        """Helper to get general notes from config."""
        try:
            # Get the directory containing the spreadsheet
            table_dir = os.path.dirname(self.config.spreadsheet)
            config_path = os.path.join(table_dir, "column_config.yml")
            
            # Load column configuration
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_content = yaml.safe_load(f)
                if isinstance(yaml_content, dict) and "general_notes" in yaml_content:
                    return yaml_content.get("general_notes", "")
            return ""
        except Exception as e:
            logging.error(f"Failed to load general notes: {e}")
            return ""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def _query_perplexity(
        self,
        prompt: str,
        context_url: Optional[str] = None,
        message_history: Optional[List[Dict[str, str]]] = None
    ) -> Tuple[str, float, List[str], str, str, str]:
        """Query Perplexity AI with the prompt."""
        # If API key is not specified, look for it in environment variables
        api_key = self.api_key
        if not api_key:
            logging.error("No API key provided for Perplexity API")
            return "No API key provided", 0.0, [], "LOW", "", ""
        
        # Prepare headers and endpoint
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}"
        }
        endpoint = "https://api.perplexity.ai/chat/completions"
        
        # Rate limiting
        await self.rate_limiter.acquire()
        
        try:
            # Prepare messages
            messages = []
            if message_history:
                messages.extend(message_history)
            
            # System message
            messages.append(
                {"role": "system", "content": self.prompts["system_message"]}
            )
            
            # Format the main prompt with examples
            messages.append(
                {"role": "user", "content": prompt}
            )
            
            # Add context URL if provided
            if context_url:
                logging.debug(f"Adding context URL: {context_url}")
                # Add as a system message
                messages.append(
                    {"role": "system", "content": f"Use the following URL to help answer: {context_url}"}
                )
            
            # Build the API request
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": 0.1
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extract answer from the response
                full_response = data["choices"][0]["message"]["content"]
                
                # Log the raw response for debugging
                logging.debug(f"Raw response: {full_response}")
                
                # Split response into lines
                lines = full_response.split("\n")
                
                # Initialize variables
                answer = ""
                confidence_level = "MEDIUM"  # Default
                citations = data.get("citations", [])
                quote = ""
                explanation = ""
                main_source = ""
                
                # Check if this might be a multiplex response (JSON array)
                is_multiplex = full_response.strip().startswith("[") and "]" in full_response
                
                if is_multiplex:
                    # For multiplex, we'll just store the raw response
                    # and return minimal default values
                    result = {
                        "answer": "",
                        "confidence": 0.8,  # Default medium confidence
                        "citations": citations,
                        "confidence_level": "MEDIUM",
                        "quote": "",
                        "main_source": "",
                        "explanation": "",
                        "raw_response": full_response  # Store the full JSON response
                    }
                    self.cache.set("perplexity", self.model_name, prompt, result, context_url)
                    
                    # Also cache with a special key for multiplex results
                    self.cache.set("perplexity_multiplex", self.model_name, prompt, {
                        "content": full_response,
                        "timestamp": datetime.now().isoformat()
                    }, context_url)
                    
                    return "", 0.8, citations, "MEDIUM", "", ""
                else:
                    # Parse the standard response format
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.upper().startswith("ANSWER:"):
                            answer = line[7:].strip()  # Remove "ANSWER:" prefix
                        elif line.upper().startswith("CONFIDENCE:"):
                            confidence = line[11:].strip().upper()  # Remove "CONFIDENCE:" prefix
                            if confidence in ["LOW", "MEDIUM", "HIGH"]:
                                confidence_level = confidence
                        elif line.upper().startswith("QUOTE:"):
                            quote = line[6:].strip()  # Remove "QUOTE:" prefix
                        elif line.upper().startswith("SOURCES:") or line.upper().startswith("SOURCE:"):
                            source_text = line[(line.find(":")+1):].strip()
                            # Extract first URL if available for main source
                            if source_text:
                                urls = re.findall(r'https?://[^\s,\]]+', source_text)
                                if urls:
                                    main_source = urls[0]
                        elif line.upper().startswith("EXPLANATION:"):
                            explanation = line[12:].strip()  # Remove "EXPLANATION:" prefix
                
                # If answer is empty after parsing, try using the first line
                if not answer and lines:
                    answer = lines[0].strip()
                    # But still remove ANSWER: if it starts with that
                    if answer.upper().startswith("ANSWER:"):
                        answer = answer[7:].strip()
                
                # Clean the answer further if needed - remove any instances of "ANSWER:"
                answer = re.sub(r'^ANSWER:\s*', '', answer, flags=re.IGNORECASE)
                
                # Log the parsed result
                logging.info(f"Parsed response: answer='{answer}', confidence={confidence_level}")
                
                # Convert confidence level to numeric value
                confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                confidence = confidence_map.get(confidence_level, 0.8)
                
                # Cache the result
                result = {
                    "answer": answer,
                    "confidence": confidence,
                    "citations": citations,
                    "confidence_level": confidence_level,
                    "quote": quote,
                    "main_source": main_source,
                    "explanation": explanation,
                    "raw_response": full_response  # Store the full response for later processing
                }
                self.cache.set("perplexity", self.model_name, prompt, result, context_url)
                
                return answer, confidence, citations, confidence_level, quote, main_source
                
        except Exception as e:
            logging.error(f"Error querying Perplexity: {str(e)}")
            logging.error(f"Error details: {traceback.format_exc()}")
            return "", 0.5, [], "LOW", "", ""

    def _extract_multiplex_quotes(self, raw_response: str) -> Dict[str, str]:
        """Extract quotes from a multiplex response."""
        quotes = {}
        try:
            parsed_results = self._parse_multiplex_response(raw_response)
            for column_result in parsed_results:
                column_name = column_result.get('column')
                if column_name:
                    quotes[column_name] = column_result.get('quote', '')
            return quotes
        except Exception as e:
            logging.error(f"Error extracting quotes from multiplex response: {e}")
            return {}

    def _get_column_info(self, column: str) -> Dict:
        """Get configuration information for a column."""
        return self.column_config.get(column, {
            'importance': 'ignored',
            'description': '',
            'format': 'String',
            'notes': ''
        })

    def _build_prompt(self, row: pd.Series, target: ValidationTarget) -> str:
        """Build a detailed prompt for the LLM."""
        column_info = self.column_config.get(target.column, {})
        description = column_info.get('description', '')
        format_info = column_info.get('format', '')
        notes = column_info.get('notes', '')
        
        # Use the improved formatting for examples
        examples_text = self._format_examples(target.column)
        
        # Get general notes 
        general_notes = self._get_general_notes()
        
        # Add a time-sensitive note about focusing on future events
        # This won't affect caching because we're not adding timestamps to the prompt
        if any(word in target.column.lower() for word in ['date', 'year', 'time', 'when', 'event']):
            time_note = "\nNOTE: When validating dates or time-sensitive information, focus on FUTURE events that have not yet occurred. Ignore past events."
            general_notes = general_notes + time_note if general_notes else time_note
        
        # Build the context string
        context = ""
        for pk in self.config.primary_key:
            context += f"{pk}: {row.get(pk, '')}\n"
        
        # Use template from prompts file
        prompt_template = self.prompts.get('validation_prompt', '')
        return prompt_template.format(
            context=context,
            column=target.column,
            description=description,
            format_info=format_info,
            notes=notes,
            value=row.get(target.column, ''),
            general_notes=general_notes,
            examples=examples_text
        ), row.get(self.config.website_column, '')

    async def determine_next_check_date(
        self,
        row: pd.Series,
        validation_results: Dict[str, Tuple[Optional[str], float, List[str], str]]
    ) -> Tuple[datetime, List[str]]:
        """Determine the next check date based on validation results and conference details."""
        # Build context string
        context = ""
        for pk in self.config.primary_key:
            context += f"{pk}: {row.get(pk, '')}\n"
        
        # Identify critical issues and items needing verification
        critical_issues = []
        medium_confidence = []
        for column, (_, confidence, _, _) in validation_results.items():
            if confidence < 0.6:  # Low confidence
                critical_issues.append(column)
            elif confidence < 0.9:  # Medium confidence
                medium_confidence.append(column)
        
        # Format lists for template
        critical_issues_str = ', '.join(critical_issues) if critical_issues else 'None'
        medium_confidence_str = ', '.join(medium_confidence) if medium_confidence else 'None'
        
        # Use template from prompts file
        prompt = self.prompts.get('next_check_date', '').format(
            context=context,
            critical_issues=critical_issues_str,
            medium_confidence=medium_confidence_str
        )

        try:
            logging.info("Querying Perplexity for next check date recommendation...")
            # Fix: Unpack 6 values properly
            answer, _, citations, confidence_level, quote, source_url = await self._query_perplexity(prompt)
            logging.info("Perplexity response: %s", answer)
            
            # Parse the response - handle both formats with and without asterisks
            date_match = re.search(r'NEXT_CHECK_DATE:\s*\*?\*?(\d{4}-\d{2}-\d{2})\*?\*?', answer)
            reason_match = re.search(r'REASON:\s*(.*?)(?=PRIORITY_ITEMS:|$)', answer, re.DOTALL)
            
            if date_match:
                next_check = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                reason = reason_match.group(1).strip() if reason_match else "Based on validation results"
                logging.info("Next check date determined: %s", next_check.strftime("%Y-%m-%d"))
                logging.info("Reason: %s", reason)
                return next_check, [reason] + citations
            else:
                logging.warning("No specific date found in response, using default policy")
                # Default to conference policy if no specific date found
                now = datetime.now()
                if critical_issues:
                    next_check = now + timedelta(days=30)  # Check in 1 month for critical issues
                    reason = "Critical issues found"
                elif medium_confidence:
                    next_check = now + timedelta(days=60)  # Check in 2 months for medium confidence
                    reason = "Items need verification"
                else:
                    next_check = now + timedelta(days=90)  # Check in 3 months by default
                    reason = "Default check interval"
                logging.info("Using default next check date: %s", next_check.strftime("%Y-%m-%d"))
                logging.info("Reason: %s", reason)
                return next_check, [reason]
                
        except Exception as e:
            logging.error("Failed to determine next check date: %s", str(e))
            logging.error("Traceback: %s", traceback.format_exc())
            # Default to 3 months from now
            next_check = datetime.now() + timedelta(days=90)
            logging.info("Using fallback next check date: %s", next_check.strftime("%Y-%m-%d"))
            return next_check, ["Default check interval"]

    async def validate_row_batch(
        self,
        row: pd.Series,
        targets: List[ValidationTarget],
    ) -> Dict[str, Tuple[Optional[str], float, List[str], str]]:
        """Validate all columns for a row in a single API call."""
        # Skip ignored columns
        targets = [t for t in targets if t.importance != ColumnImportance.IGNORED]
        logging.info(f"\nAttempting batch validation for {row['Conference']}")
        logging.info(f"Validating {len(targets)} columns: {', '.join(t.column for t in targets)}")
        
        # Initialize results with Last Check and Next Check Date
        results = {
            "Last Check": (datetime.now(), 1.0, [], "HIGH"),
            "Next Check Date": (None, 1.0, [], "HIGH")
        }
        
        # Build conversation history with conference context
        website_url = row.get(self.config.website_column, "")
        messages = [
            {"role": "system", "content": self.prompts.get('system_base', '')}
        ]
        
        # Add website URL context if available
        if website_url:
            messages.append({
                "role": "system", 
                "content": self.prompts.get('system_url', '').format(context_url=website_url)
            })
        
        # Initialize conversation with conference information
        messages.append({
            "role": "system", 
            "content": self.prompts.get('batch_validation', '')
        })
        
        # Add conference context
        context_prompt = "I'm validating information for the following conference:\n"
        for pk in self.config.primary_key:
            if row.get(pk):
                context_prompt += f"{pk}: {row.get(pk)}\n"
        
        if website_url:
            context_prompt += f"Website: {website_url}\n"
            
        context_prompt += f"\n{self._get_general_notes()}"
        
        messages.append({"role": "user", "content": context_prompt})
        messages.append({"role": "assistant", "content": "I understand. I'll help validate the information for this conference. What would you like me to check first?"})
        
        # Validate each column in sequence, building conversation history
        for target in targets:
            value = row[target.column]
            if pd.isna(value):
                results[target.column] = (None, 0.0, [], "LOW")
                continue
                
            # Build the prompt using template
            prompt = self.prompts.get('batch_column', '').format(
                column=target.column,
                value=value,
                type=target.type.value,
                general_notes=self._get_general_notes(),
                examples=self._format_examples(target.column)
            )
            
            # Log the prompt for debugging
            logging.info(f"Prompt sent to LLM (batch): {prompt}")
            
            # Query Perplexity with conversation history
            try:
                answer, confidence, citations, confidence_level, quote, main_source = await self._query_perplexity(
                    prompt=prompt,
                    context_url=website_url,
                    message_history=messages.copy()  # Pass the current conversation history
                )
                
                if not answer or (isinstance(answer, str) and answer.strip() == ""):
                    logging.error(f"Empty answer received for prompt: {prompt}")
                    results[target.column] = (None, 0.0, [], "LOW")
                else:
                    results[target.column] = (answer, confidence, citations, confidence_level)
                    
                    # Add this interaction to the conversation history
                    messages.append({"role": "user", "content": prompt})
                    messages.append({"role": "assistant", "content": f"ANSWER: {answer}\nCONFIDENCE: {confidence_level}\nQUOTE: {quote}"})
                    
            except Exception as e:
                logging.error(f"Failed to perform web search (batch) for column {target.column}: {e}")
                logging.error(f"Exception details: {traceback.format_exc()}")
                results[target.column] = (None, 0.0, [], "LOW")
            
        return results

    def _format_examples(self, column_name: str) -> str:
        """Format examples for a column to be included in prompts."""
        column_info = self.column_config.get(column_name, {})
        examples = column_info.get('examples', [])
        if not examples:
            return ""
        
        # Get column format/type information
        column_type = column_info.get('type', '')
        column_format = column_info.get('format', '')
        format_info = column_format if column_format else column_type
        
        # Build a more visually distinct example display
        examples_formatted = []
        for i, example in enumerate(examples):
            examples_formatted.append(f"Example {i+1}: '{example}'")
        
        # Add type hint based on column type
        type_hint = ""
        if column_type or column_format:
            type_hint = f"\nFormat: {format_info}"
            
            # Add special note based on type
            if "date" in str(format_info).lower():
                type_hint += " (valid conference dates)"
            elif "url" in str(format_info).lower():
                type_hint += " (official conference websites)"
            elif "boolean" in str(format_info).lower():
                type_hint += " (Yes/No values)"
        
        return f"Examples of valid {column_name} values:{type_hint}\n" + "\n".join(examples_formatted)

    def _parse_batch_response(
        self,
        response: str,
        citations: List[str],
        targets: List[ValidationTarget]
    ) -> Dict[str, Tuple[Optional[str], float, List[str], str]]:
        """Parse the batch validation response."""
        results = {}
        lines = response.split("\n")
        
        current_column = None
        current_answer = None
        current_confidence = "MEDIUM"
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith("ANSWER:"):
                current_answer = line[7:].strip()  # Remove "ANSWER:" prefix
            elif line.startswith("CONFIDENCE:"):
                confidence = line[11:].strip().upper()  # Remove "CONFIDENCE:" prefix
                if confidence in ["LOW", "MEDIUM", "HIGH"]:
                    current_confidence = confidence
            elif line.startswith("COLUMN:"):
                if current_column and current_answer:
                    confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                    confidence = confidence_map.get(current_confidence, 0.8)
                    results[current_column] = (current_answer, confidence, citations, current_confidence)
                current_column = line[7:].strip()  # Remove "COLUMN:" prefix
                current_answer = None
                current_confidence = "MEDIUM"
        
        # Add the last result if exists
        if current_column and current_answer:
            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
            confidence = confidence_map.get(current_confidence, 0.8)
            results[current_column] = (current_answer, confidence, citations, current_confidence)
        
        return results

    async def validate_row(
        self,
        row: pd.Series,
        target: ValidationTarget,
    ) -> Tuple[Optional[str], float, List[str], str, str, str]:
        """Validate a single cell using AI."""
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
            answer, confidence, citations, confidence_level, quote, main_source = await self._query_perplexity(prompt, website_url)
            if not answer or (isinstance(answer, str) and answer.strip() == ""):
                logging.error(f"Empty answer received for prompt: {prompt}")
                return None, 0.0, [], "LOW", "", ""
            return answer, confidence, citations, confidence_level, quote, main_source
        except Exception as e:
            logging.error(f"Failed to perform web search: {e}")
            logging.error(f"Exception details: {traceback.format_exc()}")
            return None, 0.0, [], "LOW", "", ""
        
    async def validate_dataframe(
        self,
        df: pd.DataFrame,
    ) -> Dict[str, Dict[str, Tuple[Optional[str], float, List[str], str]]]:
        """Validate all target columns in the DataFrame."""
        # Add Last Check and Next Check Date columns if they don't exist, initialized as empty
        if "Last Check" not in df.columns:
            df["Last Check"] = pd.NaT  # Use NaT (Not a Time) for empty datetime
        if "Next Check Date" not in df.columns:
            df["Next Check Date"] = pd.NaT

        results = {}
        run_log = {
            "total_rows": len(df),
            "multiplex_groups": 0,
            "individual_validations": 0,
            "low_confidence_critical": [],
            "next_check_dates": []
        }
        
        with Progress() as progress:
            task = progress.add_task("[cyan]Validating...", total=len(df))
            
            for idx, row in df.iterrows():
                row_key = "|".join(str(row[col]) for col in self.config.primary_key)
                results[row_key] = {}
                
                # Use multiplex validation for this row
                multiplex_results, mplex_groups, indiv_validations = await self.validate_row_multiplex(row, self.config.validation_targets)
                results[row_key].update(multiplex_results)
                
                # Update statistics
                run_log["multiplex_groups"] += mplex_groups
                run_log["individual_validations"] += indiv_validations
                
                # Check for critical items with low confidence
                for target in self.config.validation_targets:
                    if (target.importance == ColumnImportance.CRITICAL and 
                        target.column in multiplex_results and 
                        multiplex_results[target.column][1] < target.confidence_threshold):
                        run_log["low_confidence_critical"].append({
                            "row": row_key,
                            "column": target.column,
                            "confidence": multiplex_results[target.column][1],
                            "value": multiplex_results[target.column][0]
                        })
                
                # Set check dates for this row
                if results[row_key]:
                    df.at[idx, "Last Check"] = datetime.now()
                    results[row_key]["Last Check"] = (datetime.now(), 1.0, [], "HIGH")
                    
                    if self.enable_next_check_date:
                        next_check_date, next_check_reason = await self.determine_next_check_date(row, results[row_key])
                        df.at[idx, "Next Check Date"] = next_check_date
                        results[row_key]["Next Check Date"] = (next_check_date, 1.0, next_check_reason, "HIGH")
                        run_log["next_check_dates"].append(next_check_date)
                
                progress.advance(task)
            
            # Generate run summary
            self._log_run_summary(run_log)
                    
        return results, df  # Return both results and updated DataFrame

    def _log_run_summary(self, run_log: Dict) -> None:
        """Generate and log a summary of the validation run."""
        console.print("\n[bold]Validation Run Summary[/bold]")
        console.print(f"Total rows processed: {run_log['total_rows']}")
        console.print(f"Multiplex validation groups: {run_log['multiplex_groups']}")
        console.print(f"Individual column validations: {run_log['individual_validations']}")
        
        total_validations = run_log['multiplex_groups'] + run_log['individual_validations']
        if total_validations > 0:
            efficiency = run_log['multiplex_groups'] / total_validations * 100
            console.print(f"Validation efficiency: {efficiency:.1f}% (higher is better)")
        
        if run_log['low_confidence_critical']:
            console.print("\n[bold yellow]Low Confidence Critical Items:[/bold yellow]")
            for item in run_log['low_confidence_critical']:
                console.print(f"- {item['row']}: {item['column']} (Confidence: {item['confidence']:.2f})")
                console.print(f"  Value: {item['value']}")
        
        # Find earliest next check date
        if run_log['next_check_dates']:
            earliest_check = min(run_log['next_check_dates'])
            console.print(f"\n[bold]Recommended Next Run Date:[/bold] {earliest_check.strftime('%Y-%m-%d')}")
            console.print("Note: This is based on the earliest recommended check date across all rows.")

    def _parse_response(self, response: Dict) -> Tuple[Optional[str], List[str], str]:
        """Parse the response from Perplexity API."""
        try:
            content = response["choices"][0]["message"]["content"]
            citations = response.get("citations", [])
            
            # Split response into lines
            lines = content.split("\n")
            
            # Find the answer line
            answer = None
            for line in lines:
                if line.startswith("ANSWER:"):
                    answer = line[7:].strip()  # Remove "ANSWER:" prefix
                    break
            
            return answer, citations, content
        except Exception as e:
            logging.error(f"Error parsing response: {e}")
            return None, [], str(e)

    def _get_column_search_group(self, column_name: str) -> int:
        """Get the search group for a column, defaulting to 0 if not specified."""
        column_info = self.column_config.get(column_name, {})
        return column_info.get('search_group', 0)
    
    def _group_columns_by_search_group(self, targets: List[ValidationTarget]) -> Dict[int, List[ValidationTarget]]:
        """Group columns by their search_group attribute."""
        grouped_columns = {}
        for target in targets:
            if target.importance == ColumnImportance.IGNORED:
                continue
                
            search_group = self._get_column_search_group(target.column)
            if search_group not in grouped_columns:
                grouped_columns[search_group] = []
            grouped_columns[search_group].append(target)
        
        return grouped_columns
    
    def _build_multiplex_prompt(self, row: pd.Series, targets: List[ValidationTarget]) -> str:
        """Build a prompt for validating multiple columns at once."""
        # Build context
        context = ""
        for pk in self.config.primary_key:
            context += f"{pk}: {row.get(pk, '')}\n"
        
        # Build column details
        columns_to_validate = ""
        for target in targets:
            column_info = self.column_config.get(target.column, {})
            description = column_info.get('description', '')
            format_info = column_info.get('format', '')
            notes = column_info.get('notes', '')
            examples = self._format_examples(target.column)
            
            columns_to_validate += f"Column: {target.column}\n"
            columns_to_validate += f"Current Value: {row.get(target.column, '')}\n"
            columns_to_validate += f"Description: {description}\n"
            columns_to_validate += f"Format: {format_info}\n"
            if notes:
                columns_to_validate += f"Notes: {notes}\n"
            if examples:
                columns_to_validate += f"Examples:\n{examples}\n"
            columns_to_validate += "\n---\n\n"
        
        # Get general notes
        general_notes = self._get_general_notes()
        
        # Add a reminder about focusing on future events for conference data
        # This won't break caching as we're not adding timestamps
        if any("date" in target.column.lower() for target in targets):
            time_note = "\nIMPORTANT: For any date-related validation, prioritize information about FUTURE events that have not yet occurred. Ignore past events."
            if general_notes:
                general_notes = general_notes + time_note 
            else:
                general_notes = time_note
        
        # Use template with all variables properly populated
        try:
            # Safely get the template, providing a basic default if missing
            prompt_template = self.prompts.get('multiplex_validation', '')
            
            # If we don't have a template at all, use a basic one
            if not prompt_template:
                return self._build_basic_multiplex_prompt(context, columns_to_validate), row.get(self.config.website_column, '')
                
            # This will raise KeyError if template has missing placeholders
            return prompt_template.format(
                context=context,
                column_count=len(targets),
                columns_to_validate=columns_to_validate,
                general_notes=general_notes
            ), row.get(self.config.website_column, '')
            
        except KeyError as e:
            # Handle missing keys in template
            logging.error(f"Error formatting multiplex prompt: {e}")
            return self._build_basic_multiplex_prompt(context, columns_to_validate), row.get(self.config.website_column, '')
    
    def _build_basic_multiplex_prompt(self, context: str, columns_to_validate: str) -> str:
        """Build a basic multiplex prompt without any template requirements."""
        return f"""You are a data validation expert. Your task is to validate multiple fields:

Context:
{context}

I need you to validate the following columns:

{columns_to_validate}

Provide your answer as a valid JSON array with objects for each column. You MUST format your response as JSON and nothing else - no markdown, no explanations, just valid JSON:

[
  {{
    "column": "Column Name 1",
    "answer": "validated value 1",
    "quote": "direct quote from source",
    "sources": ["url1", "url2"],
    "confidence": "HIGH/MEDIUM/LOW",
    "update_required": true,
    "explanation": "brief explanation"
  }},
  {{
    "column": "Column Name 2",
    "answer": "validated value 2",
    "quote": "direct quote from source",
    "sources": ["url1", "url2"],
    "confidence": "HIGH/MEDIUM/LOW", 
    "update_required": false,
    "explanation": "brief explanation"
  }}
]

IMPORTANT: Your response must be valid JSON containing objects for ALL the requested columns. No text or formatting outside of the JSON array."""
    
    def _parse_multiplex_response(self, response: str) -> List[Dict]:
        """Parse a JSON response containing validation results for multiple columns."""
        try:
            logging.debug(f"Attempting to parse multiplex response: {response[:200]}...")
            
            # Step 1: Look for JSON within markdown code blocks
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                json_str = json_match.group(1).strip()
                logging.debug(f"Found JSON in code block: {json_str[:100]}...")
            else:
                # Step 2: Try to find a standalone JSON array
                array_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
                if array_match:
                    json_str = array_match.group(0).strip()
                    logging.debug(f"Found JSON array: {json_str[:100]}...")
                else:
                    # Step 3: Try the entire response as JSON
                    logging.debug("No JSON structure found, trying entire response")
                    json_str = response.strip()
            
            # Clean up the string - replace invalid characters
            json_str = re.sub(r'[^\x20-\x7E]', '', json_str)  # Remove non-printable chars
            
            # Parse the JSON
            try:
                results = json.loads(json_str)
                
                # If it's a dict with a specific structure, try to extract array
                if isinstance(results, dict) and "results" in results:
                    results = results["results"]
                
                # Ensure it's a list
                if not isinstance(results, list):
                    logging.error(f"Parsed JSON is not a list: {type(results)}")
                    return []
                    
                logging.info(f"Successfully parsed multiplex response with {len(results)} columns")
                return results
                
            except json.JSONDecodeError as e:
                logging.error(f"JSON decode error: {e}, trying to extract partial JSON")
                
                # Last resort: try to find individual column objects
                column_matches = re.finditer(r'{\s*"column"\s*:\s*"([^"]+)".*?}', json_str, re.DOTALL)
                results = []
                
                for match in column_matches:
                    try:
                        column_json = match.group(0).strip()
                        # Try to make it valid JSON - replace single quotes, fix booleans
                        column_json = column_json.replace("'", '"')
                        column_json = re.sub(r':\s*(true|false)\s*([,}])', r': \1\2', column_json)
                        column_obj = json.loads(column_json)
                        results.append(column_obj)
                    except json.JSONDecodeError:
                        logging.error(f"Failed to parse column JSON: {match.group(0)}")
                
                if results:
                    logging.info(f"Extracted {len(results)} column objects from partial JSON")
                    return results
                
                logging.error("Failed to extract any valid column objects")
                return []
                
        except Exception as e:
            logging.error(f"Failed to parse multiplex response: {e}")
            logging.error(f"Response was: {response[:500]}...")
            return []
    
    async def validate_row_multiplex(
        self,
        row: pd.Series,
        targets: List[ValidationTarget],
    ) -> Dict[str, Tuple[Optional[str], float, List[str], str]]:
        """Validate multiple columns for a row grouped by search_group."""
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
                # For multiple columns, use multiplex validation
                logging.info(f"Multiplex validating search group {search_group} with {len(group_targets)} columns")
                multiplex_groups += 1
                
                # Build multiplex prompt
                prompt, website_url = self._build_multiplex_prompt(row, group_targets)
                
                try:
                    # Query the API
                    answer, confidence, citations, confidence_level, quote, main_source = await self._query_perplexity(prompt, website_url)
                    
                    # Parse the JSON response
                    parsed_results = self._parse_multiplex_response(answer)
                    
                    # Process each column's result
                    for column_result in parsed_results:
                        column_name = column_result.get('column')
                        if not column_name:
                            continue
                            
                        # Extract data from the result - including quote if available
                        column_answer = column_result.get('answer', '')
                        column_confidence = column_result.get('confidence', 'LOW')
                        column_sources = column_result.get('sources', [])
                        column_quote = column_result.get('quote', '')  # Extract quote from multiplex response
                        column_explanation = column_result.get('explanation', '')
                        
                        if isinstance(column_sources, str):
                            column_sources = [column_sources]
                        
                        # Map confidence level to numeric value
                        confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                        numeric_confidence = confidence_map.get(column_confidence, 0.5)
                        
                        # Store the result - with quote data accessible in detailed view
                        # We need to extend the test_single_row_multiplex.py to store these details
                        column_info = {
                            'answer': column_answer,
                            'confidence': numeric_confidence,
                            'sources': column_sources,
                            'confidence_level': column_confidence,
                            'quote': column_quote,
                            'explanation': column_explanation
                        }
                        # Store in the standard format
                        results[column_name] = (column_answer, numeric_confidence, column_sources, column_confidence)
                        
                        # Log the result
                        quote_preview = f" | Quote: {column_quote[:30]}..." if column_quote else ""
                        logging.info(f"Processed multiplex result for {column_name}: {column_answer[:30]}...{quote_preview} (confidence: {column_confidence})")
                        
                except Exception as e:
                    logging.error(f"Error in multiplex validation for search group {search_group}: {e}")
                    logging.error(f"Traceback: {traceback.format_exc()}")
                    
                    # Set default values for all columns in this group
                    for target in group_targets:
                        results[target.column] = (None, 0.0, [], "LOW")
        
        # Update run_log statistics
        return results, multiplex_groups, individual_validations 
 