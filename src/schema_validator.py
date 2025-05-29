from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import re
from pathlib import Path
from perplexity_schema import VALIDATION_RESPONSE_SCHEMA, MULTIPLEX_RESPONSE_SCHEMA

# Import multiplex_parser for parsing API responses
try:
    from multiplex_parser import parse_multiplex_with_citations, parse_multiplex_with_references, apply_references_to_items
except ImportError:
    # Define fallback functions in case the module is not available
    def parse_multiplex_with_citations(result):
        # Silent fallback instead of warning
        return [], {}
        
    def parse_multiplex_with_references(content):
        # Silent fallback instead of warning
        return [], {}
        
    def apply_references_to_items(items, references):
        # Silent fallback instead of warning
        return items

# Import prompt_loader
try:
    from prompt_loader import load_prompts, format_prompt
    from url_extractor import normalize_sources, extract_urls_from_text, extract_main_url_from_quote, ensure_url_sources, extract_citations_from_api_response
except ImportError:
    # For local development, might need to adjust the path
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    try:
        from prompt_loader import load_prompts, format_prompt
        from url_extractor import normalize_sources, extract_urls_from_text, extract_main_url_from_quote, ensure_url_sources, extract_citations_from_api_response
    except ImportError:
        # Fallback if module can't be imported
        def load_prompts(path=None):
            return {}
        
        def normalize_sources(response_obj):
            return response_obj
            
        def extract_urls_from_text(text):
            return []
            
        def extract_main_url_from_quote(quote):
            return None
            
        def ensure_url_sources(result_obj, citations):
            return result_obj
            
        def extract_citations_from_api_response(result):
            return []

logger = logging.getLogger()

@dataclass
class ValidationTarget:
    column: str
    validation_type: str
    rules: Dict[str, Any]
    description: str
    importance: str = "MEDIUM"  # ID, CRITICAL, HIGH, MEDIUM, LOW, IGNORED
    search_group: int = 0  # Added search_group field for multiplexing

class SchemaValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_targets = self._parse_validation_targets()
        self.primary_key = config.get('primary_key', [])
        self.cache_ttl_days = config.get('cache_ttl_days', 30)
        
        # For accessing examples and other column metadata
        # First try column_config directly from config
        self.column_config = config.get('column_config', {})
        
        # If column_config is empty, but validation_targets has examples, extract them
        if not self.column_config and 'validation_targets' in config:
            # Create column_config from validation_targets
            logger.info("No column_config found in config, extracting from validation_targets")
            self.column_config = {}
            for target in config['validation_targets']:
                column_name = target.get('column', '')
                if column_name:
                    self.column_config[column_name] = {
                        'description': target.get('description', ''),
                        'format': target.get('format', ''),
                        'notes': target.get('notes', ''),
                        'examples': target.get('examples', [])
                    }
        
        # Log column config info for debugging
        logger.info(f"Initialized column_config with {len(self.column_config)} columns")
        for column, config in self.column_config.items():
            if 'examples' in config and config['examples']:
                logger.info(f"Column {column} has {len(config['examples'])} examples")
            
        self.similarity_threshold = config.get('similarity_threshold', 0.8)  # Threshold for determining substantially difference
        
        # Load prompt templates
        self.prompts = load_prompts()
        logger.info(f"Loaded {len(self.prompts)} prompt templates")
        
        # Define JSON schemas for API responses - import from perplexity_schema.py
        self._single_column_schema = VALIDATION_RESPONSE_SCHEMA
        self._multiplex_schema = MULTIPLEX_RESPONSE_SCHEMA
    
    def _parse_validation_targets(self) -> List[ValidationTarget]:
        """Parse validation targets from config."""
        targets = []
        for target_config in self.config.get('validation_targets', []):
            target = ValidationTarget(
                column=target_config['column'],
                validation_type=target_config['validation_type'],
                rules=target_config.get('rules', {}),
                description=target_config.get('description', ''),
                importance=target_config.get('importance', 'MEDIUM'),
                search_group=target_config.get('search_group', 0)  # Parse search_group for multiplexing
            )
            targets.append(target)
        return targets
    
    def _group_columns_by_search_group(self, targets: List[ValidationTarget]) -> Dict[int, List[ValidationTarget]]:
        """Group validation targets by search_group for multiplexing."""
        grouped = {}
        for target in targets:
            if target.search_group not in grouped:
                grouped[target.search_group] = []
            grouped[target.search_group].append(target)
        return grouped
    
    def _get_id_fields(self, targets: List[ValidationTarget]) -> List[ValidationTarget]:
        """Get fields with ID importance level."""
        return [target for target in targets if target.importance.upper() == "ID"]
    
    def _get_ignored_fields(self, targets: List[ValidationTarget]) -> List[ValidationTarget]:
        """Get fields with IGNORED importance level."""
        return [target for target in targets if target.importance.upper() == "IGNORED"]
    
    def _get_critical_fields(self, targets: List[ValidationTarget]) -> List[ValidationTarget]:
        """Get fields with CRITICAL importance level."""
        return [target for target in targets if target.importance.upper() == "CRITICAL"]
    
    def _is_substantially_different(self, original_value: str, validated_value: str) -> bool:
        """
        Determine if the validated value is substantially different from the original.
        Returns True if they are substantially different, False otherwise.
        """
        if original_value is None and validated_value is None:
            return False
        if original_value is None or validated_value is None:
            return True
            
        # Convert to strings for comparison
        original_str = str(original_value).strip().lower()
        validated_str = str(validated_value).strip().lower()
        
        # If they're identical, they're not different
        if original_str == validated_str:
            return False
            
        # If one is blank and the other isn't, they're different
        if not original_str or not validated_str:
            return True
            
        # Calculate similarity
        # For longer strings, use a more sophisticated approach
        if len(original_str) > 10 or len(validated_str) > 10:
            # Simple Jaccard similarity for words
            original_words = set(re.findall(r'\w+', original_str))
            validated_words = set(re.findall(r'\w+', validated_str))
            
            if not original_words or not validated_words:
                return True
                
            intersection = len(original_words.intersection(validated_words))
            union = len(original_words.union(validated_words))
            
            similarity = intersection / union if union > 0 else 0
            return similarity < self.similarity_threshold
        else:
            # For short strings, use character-level difference
            if len(original_str) == 0 or len(validated_str) == 0:
                return True
                
            # Simple edit distance-based similarity for short strings
            changes = sum(1 for a, b in zip(original_str, validated_str) if a != b)
            changes += abs(len(original_str) - len(validated_str))
            max_len = max(len(original_str), len(validated_str))
            
            similarity = 1 - (changes / max_len)
            return similarity < self.similarity_threshold
    
    def generate_validation_prompt(self, row: Dict[str, Any], target: ValidationTarget, previous_results: Dict[str, Dict[str, Any]] = None) -> str:
        """Generate a validation prompt for a specific target with context from previous validations."""
        # Get column configuration
        column_info = self.column_config.get(target.column, {})
        description = column_info.get('description', target.description)
        format_info = column_info.get('format', '')
        notes = column_info.get('notes', '')
        examples = self._format_examples(target.column)
        
        # Get general notes from config
        general_notes = self.config.get('general_notes', '')
        
        # Build the prompt directly without template substitution
        prompt_parts = []
        
        # Main section - Field to validate
        prompt_parts.append("=== FIELD TO VALIDATE ===")
        prompt_parts.append(f"Column: {target.column}")
        prompt_parts.append(f"Current Value: {row.get(target.column, '')}")
        prompt_parts.append(f"Description: {description}")
        
        if format_info:
            prompt_parts.append(f"Format: {format_info}")
            
        prompt_parts.append(f"Importance: {target.importance}")
        
        if notes:
            prompt_parts.append(f"Notes: {notes}")
        
        # ID Fields section
        context_lines = []
        id_fields = self._get_id_fields(self.validation_targets)
        if id_fields:
            prompt_parts.append("\n=== CONTEXT INFORMATION ===")
            for id_field in id_fields:
                prompt_parts.append(f"{id_field.column}: {row.get(id_field.column, '')}")
        
        # Previous validation results
        if previous_results and len(previous_results) > 0:
            prompt_parts.append("\n=== PREVIOUS VALIDATION RESULTS ===")
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                prompt_parts.append(f"{col}: {value} (Confidence: {confidence_level})")
        
        # General notes section - explicitly include this if available
        prompt_parts.append("\n=== GENERAL VALIDATION GUIDELINES ===")
        if general_notes:
            prompt_parts.append(general_notes)
        
        # Examples section
        if examples and examples.strip():
            prompt_parts.append("\n=== EXAMPLES ===")
            prompt_parts.append(examples)
        
        # Response format instructions
        prompt_parts.append("\n=== RESPONSE FORMAT ===")
        
        # Use a clear JSON example with proper formatting
        json_example = """
{
  "answer": "the validated value",
  "confidence": "HIGH, MEDIUM, or LOW",
  "quote": "direct quote from source if available",
  "sources": ["source URL 1", "source URL 2"],
  "update_required": true/false,
  "substantially_different": true/false,
  "consistent_with_model_knowledge": "YES/NO followed by brief explanation"
}
"""
        prompt_parts.append(json_example)
        
        # Add important instructions
        prompt_parts.append("IMPORTANT:")
        prompt_parts.append("- The response MUST be valid JSON")
        prompt_parts.append("- Place actual URLs in the sources array, not reference numbers")
        prompt_parts.append("- Include direct quotes from authoritative sources")
        prompt_parts.append("- If you cannot find information, indicate LOW confidence")
        
        # Join with proper line separation
        return "\n".join(prompt_parts)
    
    def generate_multiplex_prompt(self, row: Dict[str, Any], targets: List[ValidationTarget], previous_results: Dict[str, Dict[str, Any]] = None, validation_history: Dict[str, List[Dict[str, Any]]] = None) -> str:
        """Generate a validation prompt for multiple targets (multiplex) with progressive context."""
        # Get general notes from config
        general_notes = self.config.get('general_notes', '')
        
        # First, filter out the ID fields - we don't validate these, just use them for context
        validation_targets = [t for t in targets if t.importance.upper() != "ID"]
        
        # If we have no fields to validate after filtering out ID fields, return empty prompt
        if not validation_targets:
            logger.warning("No non-ID fields to validate in multiplex prompt. All fields are ID or IGNORED.")
            # Create a minimal prompt with just the response format
            return "No fields to validate."
        
        # Use the template from prompts.yml
        multiplex_template = self.prompts.get('multiplex_validation', '')
        if not multiplex_template:
            logger.warning("No multiplex_validation template found in prompts.yml, falling back to hardcoded template")
            return self._generate_multiplex_prompt_fallback(row, validation_targets, previous_results, validation_history)
        
        # Format the context section (ID fields)
        context_lines = []
        all_id_fields = self._get_id_fields(self.validation_targets)
        if all_id_fields:
            for id_field in all_id_fields:
                context_lines.append(f"{id_field.column}: {row.get(id_field.column, '')}")
        context = "\n".join(context_lines)
            
        # Format the previous results section
        previous_results_lines = []
        if previous_results and len(previous_results) > 0:
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                previous_results_lines.append(f"{col}: {value} (Confidence: {confidence_level})")
        previous_results_text = "\n".join(previous_results_lines)
        
        # Remove the general validation history section entirely
        validation_history_text = ""
            
        # Format the fields to validate section
        fields_to_validate = []
        for i, target in enumerate(validation_targets, 1):
            column_info = self.column_config.get(target.column, {})
            description = column_info.get('description', target.description)
            format_info = column_info.get('format', '')
            notes = column_info.get('notes', '')
            
            field_parts = []
            field_parts.append(f"----- FIELD {i}: {target.column} -----")
            field_parts.append(f"Current Value: {row.get(target.column, '')}")
            field_parts.append(f"Description: {description}")
            
            if format_info:
                field_parts.append(f"Format: {format_info}")
                
            field_parts.append(f"Importance: {target.importance}")
            
            if notes:
                field_parts.append(f"Notes: {notes}")
            
            # Include field validation history if available
            if validation_history and target.column in validation_history:
                field_parts.append("Previous validation entries:")
                
                # Sort entries by timestamp (newest first)
                entries = sorted(
                    validation_history[target.column],
                    key=lambda x: x.get('timestamp', ''),
                    reverse=True
                )
                
                # Add the entries (limit to most recent 3)
                for i, entry in enumerate(entries[:3]):
                    timestamp = entry.get('timestamp', 'Unknown date')
                    # Try to format the timestamp in a more readable way
                    try:
                        if isinstance(timestamp, str) and timestamp:
                            dt_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            formatted_date = dt_timestamp.strftime('%Y-%m-%d')
                        else:
                            formatted_date = "Unknown date"
                    except (ValueError, TypeError):
                        formatted_date = str(timestamp)[:10]  # Just take the date part
                        
                    value = entry.get('value', '')
                    confidence = entry.get('confidence_level', 'UNKNOWN')
                    quote = entry.get('quote', '')
                    
                    history_entry = f"  - [{formatted_date}] Value: {value} (Confidence: {confidence})"
                    if quote:
                        # Add a shortened quote if available (up to 100 chars)
                        shortened_quote = quote[:100] + ("..." if len(quote) > 100 else "")
                        history_entry += f" - Source quote: \"{shortened_quote}\""
                    
                    field_parts.append(history_entry)
            
            # Only include examples if they exist and are not empty
            # Check if column has examples before getting them
            if self.column_config.get(target.column, {}).get('examples', []):
                field_parts.append("Examples:")
                field_parts.append(self._format_examples(target.column))
            
            fields_to_validate.append("\n".join(field_parts))
        
        columns_to_validate = "\n\n".join(fields_to_validate)
        
        # Format the prompt using the template
        prompt_context = {
            'general_notes': general_notes,
            'context': context,
            'previous_results': previous_results_text,
            'validation_history': validation_history_text,
            'columns_to_validate': columns_to_validate
        }
        
        # Use the format_prompt function to fill in the template
        prompt = format_prompt(multiplex_template, prompt_context)
        
        # Clean up any instances of multiple consecutive newlines
        while "\n\n\n" in prompt:
            prompt = prompt.replace("\n\n\n", "\n\n")
            
        return prompt
        
    def _get_importance_score(self, importance: str) -> int:
        """Convert importance string to numeric score for sorting."""
        importance = importance.upper() if isinstance(importance, str) else ""
        scores = {
            "ID": 5,  # Highest importance
            "CRITICAL": 4,
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
            "IGNORED": 0  # Lowest importance
        }
        return scores.get(importance, 1)  # Default to MEDIUM if unknown

    def _generate_multiplex_prompt_fallback(self, row: Dict[str, Any], validation_targets: List[ValidationTarget], previous_results: Dict[str, Dict[str, Any]] = None, validation_history: Dict[str, List[Dict[str, Any]]] = None) -> str:
        """Fallback method to generate multiplex prompt if template is missing."""
        # Build the prompt directly
        prompt_parts = []
        
        # Main header
        prompt_parts.append("=== MULTIPLE FIELDS VALIDATION ===")
        if len(validation_targets) == 1:
            prompt_parts.append(f"Please validate the following field: {validation_targets[0].column}")
        else:
            prompt_parts.append(f"Please validate the following {len(validation_targets)} fields:")
        
        # General notes section first
        general_notes = self.config.get('general_notes', '')
        prompt_parts.append("=== GENERAL VALIDATION GUIDELINES ===")
        if general_notes:
            prompt_parts.append(general_notes)
        
        # ID Fields section for context
        prompt_parts.append("=== CONTEXT INFORMATION ===")
        context_lines = []
        all_id_fields = self._get_id_fields(self.validation_targets)
        if all_id_fields:
            for id_field in all_id_fields:
                context_lines.append(f"{id_field.column}: {row.get(id_field.column, '')}")
            prompt_parts.append("\n".join(context_lines))
        
        # Previous validation results
        prompt_parts.append("=== PREVIOUS VALIDATION RESULTS ===")
        previous_results_lines = []
        if previous_results and len(previous_results) > 0:
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                previous_results_lines.append(f"{col}: {value} (Confidence: {confidence_level})")
            prompt_parts.append("\n".join(previous_results_lines))
        else:
            prompt_parts.append("No previous validation results available.")
            
        # Validation history section if available
        if validation_history:
            prompt_parts.append("=== VALIDATION HISTORY ===")
            history_lines = []
            
            # Sort fields by importance
            field_importance = {}
            for target in validation_targets:
                field_importance[target.column] = self._get_importance_score(target.importance)
                
            sorted_fields = sorted(
                validation_history.keys(), 
                key=lambda x: field_importance.get(x, 999),
                reverse=True  # Higher importance first
            )
            
            for field in sorted_fields:
                if field in validation_history:
                    history_lines.append(f"\n{field} validation history:")
                    
                    # Sort entries by timestamp (newest first)
                    entries = sorted(
                        validation_history[field],
                        key=lambda x: x.get('timestamp', ''),
                        reverse=True
                    )
                    
                    # Add the entries (limit to most recent 3)
                    for i, entry in enumerate(entries[:3]):
                        timestamp = entry.get('timestamp', 'Unknown date')
                        # Try to format the timestamp in a more readable way
                        try:
                            if isinstance(timestamp, str) and timestamp:
                                dt_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                formatted_date = dt_timestamp.strftime('%Y-%m-%d')
                            else:
                                formatted_date = "Unknown date"
                        except (ValueError, TypeError):
                            formatted_date = str(timestamp)[:10]
                            
                        value = entry.get('value', '')
                        confidence = entry.get('confidence_level', 'UNKNOWN')
                        history_lines.append(f"  - [{formatted_date}] Value: {value} (Confidence: {confidence})")
            
            if history_lines:
                prompt_parts.append("\n".join(history_lines))
            else:
                prompt_parts.append("No validation history available.")
        
        # Fields to validate section - ONLY non-ID fields
        prompt_parts.append("=== FIELDS TO VALIDATE ===")
        
        # Format each field with clear separation
        for i, target in enumerate(validation_targets, 1):
            column_info = self.column_config.get(target.column, {})
            description = column_info.get('description', target.description)
            format_info = column_info.get('format', '')
            notes = column_info.get('notes', '')
            
            field_parts = []
            field_parts.append(f"----- FIELD {i}: {target.column} -----")
            field_parts.append(f"Current Value: {row.get(target.column, '')}")
            field_parts.append(f"Description: {description}")
            
            if format_info:
                field_parts.append(f"Format: {format_info}")
                
            field_parts.append(f"Importance: {target.importance}")
            
            if notes:
                field_parts.append(f"Notes: {notes}")
            
            # Include field validation history if available
            if validation_history and target.column in validation_history:
                field_parts.append("Previous validation entries:")
                
                # Sort entries by timestamp (newest first)
                entries = sorted(
                    validation_history[target.column],
                    key=lambda x: x.get('timestamp', ''),
                    reverse=True
                )
                
                # Add the entries (limit to most recent 3)
                for i, entry in enumerate(entries[:3]):
                    timestamp = entry.get('timestamp', 'Unknown date')
                    # Try to format the timestamp in a more readable way
                    try:
                        if isinstance(timestamp, str) and timestamp:
                            dt_timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            formatted_date = dt_timestamp.strftime('%Y-%m-%d')
                        else:
                            formatted_date = "Unknown date"
                    except (ValueError, TypeError):
                        formatted_date = str(timestamp)[:10]
                        
                    value = entry.get('value', '')
                    confidence = entry.get('confidence_level', 'UNKNOWN')
                    quote = entry.get('quote', '')
                    
                    history_entry = f"  - [{formatted_date}] Value: {value} (Confidence: {confidence})"
                    if quote:
                        # Add a shortened quote if available (up to 100 chars)
                        shortened_quote = quote[:100] + ("..." if len(quote) > 100 else "")
                        history_entry += f" - Source quote: \"{shortened_quote}\""
                    
                    field_parts.append(history_entry)
            
            # Only include examples if they exist and are not empty
            # Check if column has examples before getting them
            if self.column_config.get(target.column, {}).get('examples', []):
                field_parts.append("Examples:")
                field_parts.append(self._format_examples(target.column))
            
            # Add this field's info to the prompt
            prompt_parts.append("\n".join(field_parts))
            prompt_parts.append("")  # Add a blank line between fields
        
        # Add explicit examples usage section
        prompt_parts.append("=== EXAMPLES USAGE ===")
        prompt_parts.append("For each field, use the provided examples (both in list format and JSON format) as guidance for expected formats and values.")
        prompt_parts.append("The examples represent valid values that should inform your validation process. When validating a field, check if the")
        prompt_parts.append("current value follows similar patterns or formats as the examples provided.")
        
        # Response format instructions
        prompt_parts.append("=== RESPONSE FORMAT ===")
        response_format_intro = "Please respond with a JSON array containing an object for each field."
        if len(validation_targets) == 1:
            response_format_intro += f" Even though there is only 1 field ({validation_targets[0].column}), still return an array with a single object."
        prompt_parts.append(f"{response_format_intro} Each object must have the following structure:")
        
        # Use a clear JSON example with proper formatting
        json_example = """
[
  {
    "column": "field name",
    "answer": "validated value", 
    "confidence": "HIGH|MEDIUM|LOW",
    "quote": "direct quote from source if available",
    "sources": ["source URL 1", "source URL 2"],
    "update_required": true/false,
    "substantially_different": true/false,
    "consistent_with_model_knowledge": "YES/NO followed by brief explanation"
  },
  ...
]
"""
        prompt_parts.append(json_example)
        
        # Add important instructions
        prompt_parts.append("IMPORTANT:")
        prompt_parts.append("- The response MUST be valid JSON")
        prompt_parts.append("- Each field must have its own object in the array")
        prompt_parts.append("- Include the column name in each object")
        prompt_parts.append("- Place actual URLs in the sources arrays, not reference numbers")
        prompt_parts.append("- Include direct quotes from authoritative sources")
        prompt_parts.append("- If you cannot find information for a field, indicate LOW confidence")
        prompt_parts.append("- Use provided examples to guide your validation of format and expected values")
        prompt_parts.append("- Consider the validation history when determining if updates are needed")
        
        # Join with proper line separation
        prompt = "\n".join(prompt_parts)
            
        # Clean up any instances of multiple consecutive newlines
        while "\n\n\n" in prompt:
            prompt = prompt.replace("\n\n\n", "\n\n")
            
        return prompt
    
    def _format_examples(self, column: str) -> str:
        """
        Format examples for a column in a more structured way that's 
        easy to parse by LLMs in the validation prompt.
        """
        if column not in self.column_config:
            logger.warning(f"Column {column} not found in column_config")
            return ""
            
        column_info = self.column_config.get(column, {})
        examples = column_info.get('examples', [])
        
        if not examples:
            logger.debug(f"No examples found for column {column}")
            return ""
        
        logger.info(f"Formatting {len(examples)} examples for column {column}")
        
        # Just format as bullet points, removing both the redundant header and JSON format
        formatted = ""
        for example in examples:
            formatted += f"- {example}\n"
            
        return formatted
    
    def parse_validation_result(self, result: Dict, target: ValidationTarget, original_value: Any) -> Tuple[Any, None, List[str], str, str, str, bool, bool, Optional[str]]:
        """Parse the validation result from Perplexity API response."""
        try:
            # Extract content from API response
            if not isinstance(result, dict) or 'choices' not in result:
                return None, None, [], "LOW", "", "", False, False, None
            
            content = result['choices'][0]['message'].get('content', '')
            if not content:
                return None, None, [], "LOW", "", "", False, False, None
            
            # Parse JSON response
            try:
                validation_result = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        validation_result = json.loads(content[json_start:json_end].strip())
                    else:
                        return None, None, [], "LOW", "", "", False, False, None
                else:
                    return None, None, [], "LOW", "", "", False, False, None
            
            # Normalize sources to extract URLs from all text fields
            validation_result = normalize_sources(validation_result)
            
            # Extract values
            answer = validation_result.get('answer', '')
            confidence_level = validation_result.get('confidence', 'LOW')
            quote = validation_result.get('quote', '')
            sources = validation_result.get('sources', [])
            update_required = validation_result.get('update_required', False)
            consistent_with_model_knowledge = validation_result.get('consistent_with_model_knowledge', '')
            
            # Lower confidence if not consistent with model knowledge
            if consistent_with_model_knowledge and 'no' in consistent_with_model_knowledge.lower():
                if confidence_level == 'HIGH':
                    confidence_level = 'MEDIUM'
                elif confidence_level == 'MEDIUM':
                    confidence_level = 'LOW'
                
                # Add the inconsistency note to the quote
                if quote and consistent_with_model_knowledge:
                    quote = f"{quote} NOTE: {consistent_with_model_knowledge}"
            
            # Determine if substantially different
            substantially_different = validation_result.get('substantially_different', None)
            if substantially_different is None:
                substantially_different = self._is_substantially_different(original_value, answer)
            
            # Map confidence level to numeric value
            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95, "UNDEFINED": 0.0}
            numeric_confidence = confidence_map.get(confidence_level, 0.5)
            
            # Convert any numeric references in sources to actual URLs using citations from API
            if 'citations' in result and isinstance(result['citations'], list):
                citations = result['citations']
                source_obj = {
                    "sources": sources,
                    "main_source": sources[0] if sources else ""
                }
                processed_sources = ensure_url_sources(source_obj, citations)
                sources = processed_sources["sources"]
                main_source = processed_sources["main_source"]
            else:
                # Get main source if available
                main_source = sources[0] if sources else ""
            
            return answer, None, sources, confidence_level, quote, main_source, update_required, substantially_different, consistent_with_model_knowledge
            
        except Exception as e:
            logger.error(f"Error parsing validation result: {str(e)}")
            return None, None, [], "LOW", "", "", False, False, None
    
    def parse_multiplex_result(self, result: Dict, row: Dict[str, Any]) -> Dict[str, Tuple[Any, None, List[str], str, str, str, bool, bool, Optional[str]]]:
        """Parse results from a multiplex validation request."""
        results = {}
        
        try:
            # Extract content from API response
            if not isinstance(result, dict) or 'choices' not in result:
                logger.error("Invalid API response format for multiplex validation")
                return results
            
            content = result['choices'][0]['message'].get('content', '')
            if not content:
                logger.error("Empty content in API response for multiplex validation")
                return results
            
            # Extract citations from the API response - this is the preferred approach
            citations = extract_citations_from_api_response(result)
            if citations:
                logger.info(f"Found {len(citations)} citations in API response")
                # Convert to dictionary
                citations_dict = {}
                for i, citation in enumerate(citations):
                    citations_dict[i + 1] = citation
                
                # Try to parse items from content
                items, _ = parse_multiplex_with_citations(result)
                if items:
                    # Apply citations to items
                    items = apply_references_to_items(items, citations_dict)
                    
                    # Process each item
                    for item in items:
                        try:
                            column = item.get("column", "")
                            if not column:
                                continue
                                
                            answer = item.get("answer", "")
                            confidence_level = item.get("confidence", "LOW")
                            quote = item.get("quote", "")
                            sources = item.get("sources", [])
                            update_required = item.get("update_required", False)
                            consistent_with_model_knowledge = item.get("consistent_with_model_knowledge", "")
                            
                            # Lower confidence if not consistent with model knowledge
                            if consistent_with_model_knowledge and 'no' in consistent_with_model_knowledge.lower():
                                if confidence_level == 'HIGH':
                                    confidence_level = 'MEDIUM'
                                elif confidence_level == 'MEDIUM':
                                    confidence_level = 'LOW'
                                
                                # Add the inconsistency note to the quote
                                if quote and consistent_with_model_knowledge:
                                    quote = f"{quote} NOTE: {consistent_with_model_knowledge}"
                            
                            # Get original value
                            original_value = row.get(column, "")
                            
                            # Determine if substantially different
                            substantially_different = item.get("substantially_different", None)
                            if substantially_different is None:
                                substantially_different = self._is_substantially_different(original_value, answer)
                            
                            # No need to map to numeric value - use string confidence level directly
                            
                            # Convert any numeric references in sources to actual URLs using citations from API
                            if citations:
                                source_obj = {
                                    "sources": sources,
                                    "main_source": sources[0] if sources else ""
                                }
                                processed_sources = ensure_url_sources(source_obj, citations)
                                sources = processed_sources["sources"]
                                main_source = processed_sources["main_source"]
                            else:
                                # Get main source if available
                                main_source = sources[0] if sources else ""
                            
                            results[column] = (answer, None, sources, confidence_level, quote, main_source, update_required, substantially_different, consistent_with_model_knowledge)
                            logger.info(f"Processed multiplex result for column {column} using API citations")
                        except Exception as item_error:
                            logger.error(f"Error processing multiplex item: {str(item_error)}")
                    
                    if results:
                        return results
            
            # Try to parse with references section
            try:
                items, references = parse_multiplex_with_references(content)
                if items and references:
                    logger.info(f"Successfully parsed references format: {len(items)} items, {len(references)} references")
                    # Apply references to items
                    items = apply_references_to_items(items, references)
                    
                    # Process each item
                    for item in items:
                        try:
                            column = item.get("column", "")
                            if not column:
                                continue
                                
                            answer = item.get("answer", "")
                            confidence_level = item.get("confidence", "LOW")
                            quote = item.get("quote", "")
                            sources = item.get("sources", [])  # This is populated by apply_references_to_items
                            update_required = item.get("update_required", False)
                            main_source = item.get("main_source", "")  # Also populated by apply_references_to_items
                            
                            # Get original value
                            original_value = row.get(column, "")
                            
                            # Determine if substantially different
                            substantially_different = item.get("substantially_different", None)
                            if substantially_different is None:
                                substantially_different = self._is_substantially_different(original_value, answer)
                            
                            # No need to map to numeric value - use string confidence level directly
                            
                            results[column] = (answer, None, sources, confidence_level, quote, main_source, update_required, substantially_different, None)
                            logger.info(f"Processed multiplex result for column {column}")
                        except Exception as item_error:
                            logger.error(f"Error processing multiplex item: {str(item_error)}")
                    
                    return results
            except Exception as ref_error:
                logger.warning(f"Failed to parse with references format: {str(ref_error)}")
                # Fall back to standard parsing
            
            # Standard JSON parsing (fallback)
            try:
                validation_results = json.loads(content)
                if not isinstance(validation_results, list):
                    # Try to extract from code block if not directly parseable as array
                    if "```json" in content:
                        json_start = content.find("```json") + 7
                        json_end = content.find("```", json_start)
                        if json_end > json_start:
                            validation_results = json.loads(content[json_start:json_end].strip())
                        else:
                            return results
                    if not isinstance(validation_results, list):
                        logger.error(f"Expected array of results but got: {type(validation_results)}")
                        return results
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON in multiplex response: {str(e)}")
                # Try to extract JSON from markdown code block
                if "```json" in content:
                    try:
                        json_start = content.find("```json") + 7
                        json_end = content.find("```", json_start)
                        if json_end > json_start:
                            validation_results = json.loads(content[json_start:json_end].strip())
                        else:
                            return results
                    except:
                        return results
                else:
                    return results
            
            # Apply API citations to the validation results if available
            if citations and isinstance(validation_results, list):
                citations_dict = {}
                for i, citation in enumerate(citations):
                    citations_dict[i + 1] = citation
                validation_results = apply_references_to_items(validation_results, citations_dict)
            
            # Process each item in the array
            for item in validation_results:
                try:
                    column = item.get("column", "")
                    if not column:
                        continue
                    
                    # Normalize sources for this item
                    item = normalize_sources(item)
                    
                    answer = item.get("answer", "")
                    confidence_level = item.get("confidence", "LOW")
                    quote = item.get("quote", "")
                    sources = item.get("sources", [])
                    update_required = item.get("update_required", False)
                    
                    # Get original value
                    original_value = row.get(column, "")
                    
                    # Determine if substantially different
                    substantially_different = item.get("substantially_different", None)
                    if substantially_different is None:
                        substantially_different = self._is_substantially_different(original_value, answer)
                    
                    # No need to map to numeric value - use string confidence level directly
                    
                    # Convert any numeric references in sources to actual URLs using citations from API
                    if citations:
                        source_obj = {
                            "sources": sources,
                            "main_source": sources[0] if sources else ""
                        }
                        processed_sources = ensure_url_sources(source_obj, citations)
                        sources = processed_sources["sources"]
                        main_source = processed_sources["main_source"]
                    else:
                        # Get main source if available
                        main_source = sources[0] if sources else ""
                    
                    results[column] = (answer, None, sources, confidence_level, quote, main_source, update_required, substantially_different, None)
                    logger.info(f"Processed multiplex result for column {column}")
                except Exception as item_error:
                    logger.error(f"Error processing multiplex item: {str(item_error)}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error parsing multiplex validation results: {str(e)}")
            return results
    
    def perform_holistic_validation(
        self, 
        row: Dict[str, Any],
        validation_results: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Perform a holistic validation of the entire row to check for consistencies
        and overall correctness.
        
        Args:
            row: The original row data
            validation_results: The individual field validation results
            
        Returns:
            A dictionary containing the holistic validation results
        """
        # Initialize holistic validation result
        holistic_result = {
            "is_consistent": True,
            "overall_confidence": "HIGH",
            "concerns": [],
            "needs_review": False,
            "priority_fields": []
        }
        
        # Check if there are any inconsistencies between related fields
        self._check_field_relationships(row, validation_results, holistic_result)
        
        # Check for pattern of low confidence results
        self._evaluate_confidence_pattern(validation_results, holistic_result)
        
        # Check for critical fields with issues
        self._check_critical_fields(validation_results, holistic_result)
        
        # Set overall confidence level based on concerns
        if len(holistic_result["concerns"]) > 3:
            holistic_result["overall_confidence"] = "LOW"
            holistic_result["needs_review"] = True
        elif len(holistic_result["concerns"]) > 0:
            holistic_result["overall_confidence"] = "MEDIUM"
            if any("CRITICAL" in concern for concern in holistic_result["concerns"]):
                holistic_result["needs_review"] = True
        
        return holistic_result
    
    def _check_field_relationships(
        self,
        row: Dict[str, Any],
        validation_results: Dict[str, Dict[str, Any]],
        holistic_result: Dict[str, Any]
    ) -> None:
        """Check for inconsistencies between related fields."""
        # Get list of validated fields
        validated_fields = [
            field for field in validation_results.keys() 
            if field not in ['next_check', 'reasons', 'holistic_validation']
        ]
        
        # Identify field relationships from config
        related_fields = self.config.get('field_relationships', [])
        
        # Check each field relationship
        for relation in related_fields:
            # Skip if any fields in the relationship are missing
            if not all(field in validated_fields for field in relation['fields']):
                continue
            
            # Check the relationship type
            if relation['type'] == 'mutually_exclusive':
                # Fields should not all have values together
                non_empty_count = sum(
                    1 for field in relation['fields'] 
                    if validation_results[field].get('value') and str(validation_results[field].get('value')).strip()
                )
                if non_empty_count > 1:
                    holistic_result["concerns"].append(
                        f"Mutually exclusive fields have values: {', '.join(relation['fields'])}"
                    )
                    holistic_result["is_consistent"] = False
                    holistic_result["priority_fields"].extend(relation['fields'])
            
            elif relation['type'] == 'required_together':
                # Either all fields should have values or none should
                has_value = [
                    bool(validation_results[field].get('value') and str(validation_results[field].get('value')).strip())
                    for field in relation['fields']
                ]
                if any(has_value) and not all(has_value):
                    holistic_result["concerns"].append(
                        f"Required together fields are inconsistent: {', '.join(relation['fields'])}"
                    )
                    holistic_result["is_consistent"] = False
                    empty_fields = [relation['fields'][i] for i, v in enumerate(has_value) if not v]
                    holistic_result["priority_fields"].extend(empty_fields)
            
            elif relation['type'] == 'dependent':
                # If primary field has value, dependent fields should also have values
                primary_field = relation['primary']
                dependent_fields = relation['dependent']
                
                if primary_field in validated_fields and validation_results[primary_field].get('value'):
                    for dep_field in dependent_fields:
                        if dep_field in validated_fields and not validation_results[dep_field].get('value'):
                            holistic_result["concerns"].append(
                                f"Dependent field '{dep_field}' is empty but primary field '{primary_field}' has value"
                            )
                            holistic_result["is_consistent"] = False
                            holistic_result["priority_fields"].append(dep_field)
        
        # Look for inconsistencies in date fields
        date_fields = [
            field for field in validated_fields
            if any(date_term in field.lower() for date_term in ['date', 'year', 'month', 'day'])
        ]
        
        if len(date_fields) > 1:
            # Check for chronological consistency
            for i, field1 in enumerate(date_fields):
                for field2 in date_fields[i+1:]:
                    # Skip if either field doesn't have a configuration
                    if field1 not in self.column_config or field2 not in self.column_config:
                        continue
                    
                    field1_config = self.column_config.get(field1, {})
                    field2_config = self.column_config.get(field2, {})
                    
                    # Check if there's a chronological relationship defined
                    rel_type = None
                    if 'chronological_relation' in field1_config:
                        for rel in field1_config['chronological_relation']:
                            if rel['field'] == field2:
                                rel_type = rel['type']
                                break
                    
                    if rel_type:
                        field1_value = validation_results[field1].get('value')
                        field2_value = validation_results[field2].get('value')
                        
                        if field1_value and field2_value:
                            # Try to parse as dates for comparison
                            try:
                                # This is a simplified check - in practice, you'd need more robust date parsing
                                field1_date = field1_value
                                field2_date = field2_value
                                
                                inconsistent = False
                                if rel_type == 'before' and field1_date > field2_date:
                                    inconsistent = True
                                elif rel_type == 'after' and field1_date < field2_date:
                                    inconsistent = True
                                
                                if inconsistent:
                                    holistic_result["concerns"].append(
                                        f"Date inconsistency: {field1} should be {rel_type} {field2}"
                                    )
                                    holistic_result["is_consistent"] = False
                                    holistic_result["priority_fields"].extend([field1, field2])
                            except:
                                # If we can't parse as dates, skip this check
                                pass
    
    def _evaluate_confidence_pattern(
        self,
        validation_results: Dict[str, Dict[str, Any]],
        holistic_result: Dict[str, Any]
    ) -> None:
        """Evaluate the pattern of confidence levels across all fields."""
        # Count confidence levels
        confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNDEFINED": 0}
        total_fields = 0
        fields_with_defined_confidence = 0
        
        for field, result in validation_results.items():
            # Skip non-field entries
            if field in ['next_check', 'reasons', 'holistic_validation']:
                continue
            
            confidence_level = result.get('confidence_level', 'LOW')
            confidence_counts[confidence_level] += 1
            total_fields += 1
            
            # Don't count UNDEFINED in percentage calculations
            if confidence_level != "UNDEFINED":
                fields_with_defined_confidence += 1
        
        # Calculate percentages - only for defined confidence levels
        if fields_with_defined_confidence > 0:
            low_percentage = (confidence_counts["LOW"] / fields_with_defined_confidence) * 100
            medium_percentage = (confidence_counts["MEDIUM"] / fields_with_defined_confidence) * 100
            
            # Identify patterns of concern
            if low_percentage > 30:
                holistic_result["concerns"].append(
                    f"High percentage of LOW confidence results: {low_percentage:.1f}%"
                )
                holistic_result["needs_review"] = True
            
            if (low_percentage + medium_percentage) > 60:
                holistic_result["concerns"].append(
                    f"Majority of fields have less than HIGH confidence: {low_percentage + medium_percentage:.1f}%"
                )
                holistic_result["overall_confidence"] = "MEDIUM"
            
            # If more than 20% are low confidence, flag as needing review
            if low_percentage > 20:
                holistic_result["needs_review"] = True
                
        # Note how many fields have UNDEFINED confidence
        if confidence_counts["UNDEFINED"] > 0:
            holistic_result["concerns"].append(
                f"{confidence_counts['UNDEFINED']} fields have UNDEFINED confidence"
            )
    
    def _check_critical_fields(
        self,
        validation_results: Dict[str, Dict[str, Any]],
        holistic_result: Dict[str, Any]
    ) -> None:
        """Check if critical fields have issues."""
        critical_fields = self._get_critical_fields(self.validation_targets)
        high_importance_fields = [t for t in self.validation_targets if t.importance.upper() == "HIGH"]
        
        for field in critical_fields:
            if field.column not in validation_results:
                continue
                
            result = validation_results[field.column]
            confidence_level = result.get('confidence_level', 'LOW')
            
            if confidence_level == 'UNDEFINED':
                holistic_result["concerns"].append(
                    f"CRITICAL field '{field.column}' has UNDEFINED confidence - requires investigation"
                )
                holistic_result["needs_review"] = True
                holistic_result["priority_fields"].append(field.column)
            elif confidence_level != 'HIGH':
                holistic_result["concerns"].append(
                    f"CRITICAL field '{field.column}' has {confidence_level} confidence"
                )
                holistic_result["needs_review"] = True
                holistic_result["priority_fields"].append(field.column)
            
            if result.get('update_required', False):
                holistic_result["concerns"].append(
                    f"CRITICAL field '{field.column}' requires update"
                )
                holistic_result["priority_fields"].append(field.column)
        
        # Also check HIGH importance fields
        for field in high_importance_fields:
            if field.column not in validation_results:
                continue
                
            result = validation_results[field.column]
            confidence_level = result.get('confidence_level', 'LOW')
            
            if confidence_level == 'LOW':
                holistic_result["concerns"].append(
                    f"HIGH importance field '{field.column}' has LOW confidence"
                )
                holistic_result["priority_fields"].append(field.column)
    
    def determine_next_check_date(
        self,
        row: Dict[str, Any],
        validation_results: Dict[str, Dict[str, Any]]
    ) -> Tuple[Optional[datetime], List[str]]:
        """Determine the next check date based on validation results and holistic validation."""
        reasons = []
        min_confidence = 0.8  # Minimum confidence threshold
        
        # DISABLED: Perform holistic validation
        # holistic_result = self.perform_holistic_validation(row, validation_results)
        
        # Create a simple placeholder holistic result with no issues
        holistic_result = {
            "is_consistent": True,
            "overall_confidence": "HIGH",
            "concerns": [],
            "needs_review": False,
            "priority_fields": []
        }
        
        # Store holistic validation result in the validation_results
        validation_results['holistic_validation'] = holistic_result
        
        # If holistic validation found issues, add to reasons
        if holistic_result["concerns"]:
            reasons.extend(holistic_result["concerns"])
        
        # Check individual fields
        for target in self.validation_targets:
            if target.column in validation_results:
                result = validation_results[target.column]
                confidence_level = result.get('confidence_level', 'LOW')
                validated_value = result.get('value')
                quote = result.get('quote', '')
                
                # Check if confidence level is below threshold
                if confidence_level in ['LOW', 'UNDEFINED']:
                    reasons.append(f"Low confidence ({confidence_level}) for {target.column}: {quote}")
                    continue
                
                if validated_value is None:
                    reasons.append(f"Invalid value for {target.column}: {quote}")
                    continue
        
        # Determine when to schedule the next check
        if holistic_result["needs_review"]:
            # If holistic validation indicates need for review, schedule sooner
            next_check = datetime.now() + timedelta(days=1)
            if not reasons:
                reasons.append("Holistic validation indicates need for review")
            return next_check, reasons
        elif reasons:
            # If there are other issues, schedule next check in 1 day
            next_check = datetime.now() + timedelta(days=1)
            return next_check, reasons
        else:
            # If all validations passed, schedule next check based on cache TTL
            next_check = datetime.now() + timedelta(days=self.cache_ttl_days)
            return next_check, ["All validations passed"] 