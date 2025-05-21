from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import re
from pathlib import Path
import traceback

# Import prompt_loader
try:
    from prompt_loader import load_prompts
    from url_extractor import normalize_sources, extract_urls_from_text, extract_main_url_from_quote, ensure_url_sources, extract_citations_from_api_response
except ImportError:
    # For local development, might need to adjust the path
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    try:
        from prompt_loader import load_prompts
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
        self.column_config = config.get('column_config', {})
        self.similarity_threshold = config.get('similarity_threshold', 0.8)  # Threshold for determining substantially difference
        
        # Load prompt templates
        self.prompts = load_prompts()
        logger.info(f"Loaded {len(self.prompts)} prompt templates")
        
        # Define JSON schemas for API responses
        self._single_column_schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "quote": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "update_required": {"type": "boolean"},
                "substantially_different": {"type": "boolean"}
            },
            "required": ["answer", "confidence"]
        }
        
        self._multiplex_schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "answer": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "quote": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                    "update_required": {"type": "boolean"},
                    "substantially_different": {"type": "boolean"}
                },
                "required": ["column", "answer", "confidence"]
            }
        }
    
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
        
        # Check if we have the validation_prompt template
        if 'validation_prompt' in self.prompts:
            # Create context string from ID fields
            context = ""
            id_fields = self._get_id_fields(self.validation_targets)
            if id_fields:
                context += "ID Fields:\n"
                for id_field in id_fields:
                    context += f"  {id_field.column}: {row.get(id_field.column, '')}\n"
            
            # Add previous results as context if available
            if previous_results and len(previous_results) > 0:
                context += "\nPrevious Validation Results:\n"
                for col, result in previous_results.items():
                    confidence_level = result.get('confidence_level', 'UNKNOWN')
                    value = result.get('value', '')
                    context += f"  {col}: {value} (Confidence: {confidence_level})\n"
            
            # Format the template with our data
            template = self.prompts['validation_prompt']
            prompt = template.format(
                context=context,
                column=target.column,
                description=description,
                format_info=format_info,
                notes=notes,
                general_notes=self.config.get('general_notes', ''),
                examples=examples,
                value=row.get(target.column, '')
            )
            
            return prompt
        
        # Fallback to the original implementation if template is not available
        prompt = f"""Please validate the following data according to these rules:
Column: {target.column}
Current Value: {row.get(target.column, '')}
Validation Type: {target.validation_type}
Rules: {json.dumps(target.rules, indent=2)}
Description: {description}
Format: {format_info}
Importance: {target.importance}"""

        if notes:
            prompt += f"\nNotes: {notes}"
        if examples:
            prompt += f"\nExamples:\n{examples}"
        
        # Add ID fields for context
        id_fields = self._get_id_fields(self.validation_targets)
        if id_fields:
            prompt += "\n\nID Fields:\n"
            for id_field in id_fields:
                prompt += f"  {id_field.column}: {row.get(id_field.column, '')}\n"
        
        # Add previous results as context if available
        if previous_results and len(previous_results) > 0:
            prompt += "\nPrevious Validation Results:\n"
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                prompt += f"  {col}: {value} (Confidence: {confidence_level})\n"
            
        prompt += f"""

Please respond in the following JSON format:
{{
    "answer": <the validated value>,
    "confidence": <confidence level: HIGH, MEDIUM, or LOW>,
    "quote": <direct quote from source if available>,
    "sources": [<list of source URLs>],
    "update_required": <true if value needs to be updated>,
    "substantially_different": <true if validated value is substantially different from input>
}}"""
        
        return prompt
    
    def generate_multiplex_prompt(self, row: Dict[str, Any], targets: List[ValidationTarget], previous_results: Dict[str, Dict[str, Any]] = None) -> str:
        """Generate a validation prompt for multiple targets (multiplex) with progressive context."""
        general_notes = self.config.get('general_notes', '')
        
        # Check if we have the multiplex template
        if 'multiplex_validation' in self.prompts:
            # Create context string from ID fields
            context = ""
            id_fields = self._get_id_fields(self.validation_targets)
            if id_fields:
                context += "ID Fields:\n"
                for id_field in id_fields:
                    context += f"  {id_field.column}: {row.get(id_field.column, '')}\n"
            
            # Add previous results as context if available
            if previous_results and len(previous_results) > 0:
                context += "\nPrevious Validation Results:\n"
                for col, result in previous_results.items():
                    confidence_level = result.get('confidence_level', 'UNKNOWN')
                    value = result.get('value', '')
                    context += f"  {col}: {value} (Confidence: {confidence_level})\n"
            
            # Format the columns to validate
            columns_to_validate = ""
            for target in targets:
                column_info = self.column_config.get(target.column, {})
                description = column_info.get('description', target.description)
                format_info = column_info.get('format', '')
                notes = column_info.get('notes', '')
                examples = self._format_examples(target.column)
                
                columns_to_validate += f"""Field: {target.column}
Current Value: {row.get(target.column, '')}
Description: {description}
Format: {format_info}
Importance: {target.importance}
"""
                if notes:
                    columns_to_validate += f"Notes: {notes}\n"
                if examples:
                    columns_to_validate += f"Examples: {examples}\n"
                
                columns_to_validate += "\n"
            
            # Format the template with our data
            template = self.prompts['multiplex_validation']
            prompt = template.format(
                context=context,
                general_notes=general_notes,
                column_count=len(targets),
                columns_to_validate=columns_to_validate
            )
            
            return prompt
            
        # Fallback to the original implementation if template is not available
        # Build the multiplex prompt header
        prompt = f"""Please validate the following data fields:

{general_notes}

I need you to validate multiple fields at once. For each field, provide your validated answer, confidence level, and supporting information.
"""
        
        # Add ID fields at the beginning
        id_fields = self._get_id_fields(self.validation_targets)
        if id_fields:
            prompt += "\nIdentification Fields:\n"
            for id_field in id_fields:
                prompt += f"  {id_field.column}: {row.get(id_field.column, '')}\n"
            prompt += "\n"
        
        # Add previous results as context if available
        if previous_results and len(previous_results) > 0:
            prompt += "Previous Validation Results:\n"
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                prompt += f"  {col}: {value} (Confidence: {confidence_level})\n"
            prompt += "\n"
        
        # Add each column to validate
        prompt += "Fields to validate:\n\n"
        
        for target in targets:
            column_info = self.column_config.get(target.column, {})
            description = column_info.get('description', target.description)
            format_info = column_info.get('format', '')
            notes = column_info.get('notes', '')
            examples = self._format_examples(target.column)
            
            prompt += f"""Field: {target.column}
Current Value: {row.get(target.column, '')}
Description: {description}
Format: {format_info}
Importance: {target.importance}
"""
            if notes:
                prompt += f"Notes: {notes}\n"
            if examples:
                prompt += f"Examples: {examples}\n"
            
            prompt += "\n"
        
        # Add response format instructions
        prompt += """Please respond with a JSON array containing an object for each field. Each object should have the following structure:
[
  {
    "column": "field name",
    "answer": "validated value",
    "confidence": "HIGH|MEDIUM|LOW",
    "quote": "direct quote from source if available",
    "sources": ["source URL 1", "source URL 2"],
    "update_required": true/false,
    "substantially_different": true/false
  },
  ...
]"""
        
        return prompt
    
    def _format_examples(self, column: str) -> str:
        """Format examples for a column."""
        examples = self.column_config.get(column, {}).get('examples', [])
        if not examples:
            return ""
        
        formatted = "Examples of valid values:\n"
        for example in examples:
            formatted += f"- {example}\n"
        return formatted
    
    def parse_validation_result(self, result: Dict, target: ValidationTarget, original_value: Any) -> Tuple[Any, float, List[str], str, str, str, bool, bool, Optional[str]]:
        """Parse the validation result from Perplexity API response."""
        try:
            # Extract content from API response
            if not isinstance(result, dict) or 'choices' not in result:
                return None, 0.0, [], "LOW", "", "", False, False, None
            
            content = result['choices'][0]['message'].get('content', '')
            if not content:
                return None, 0.0, [], "LOW", "", "", False, False, None
            
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
                        return None, 0.0, [], "LOW", "", "", False, False, None
                else:
                    return None, 0.0, [], "LOW", "", "", False, False, None
            
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
            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
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
            
            return answer, numeric_confidence, sources, confidence_level, quote, main_source, update_required, substantially_different, consistent_with_model_knowledge
            
        except Exception as e:
            logger.error(f"Error parsing validation result: {str(e)}")
            return None, 0.0, [], "LOW", "", "", False, False, None
    
    def parse_multiplex_result(self, result: Dict, row: Dict[str, Any]) -> Dict[str, Tuple[Any, float, List[str], str, str, str, bool, bool, Optional[str]]]:
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
                            
                            # Map confidence level to numeric value
                            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                            numeric_confidence = confidence_map.get(confidence_level, 0.5)
                            
                            # Convert any numeric references in sources to actual URLs using citations
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
                            
                            results[column] = (answer, numeric_confidence, sources, confidence_level, quote, main_source, update_required, substantially_different, consistent_with_model_knowledge)
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
                            
                            # Map confidence level to numeric value
                            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                            numeric_confidence = confidence_map.get(confidence_level, 0.5)
                            
                            results[column] = (answer, numeric_confidence, sources, confidence_level, quote, main_source, update_required, substantially_different, None)
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
                    
                    # Map confidence level to numeric value
                    confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
                    numeric_confidence = confidence_map.get(confidence_level, 0.5)
                    
                    # Convert any numeric references in sources to actual URLs using citations
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
                    
                    results[column] = (answer, numeric_confidence, sources, confidence_level, quote, main_source, update_required, substantially_different, None)
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
        
        # Skip check if no field relationships defined
        if not related_fields:
            logger.info("No field relationships defined in config, skipping relationship check")
            return
            
        # Check each field relationship
        for relation in related_fields:
            # Skip if relation doesn't have required fields
            relation_type = relation.get('type')
            if not relation_type:
                logger.warning(f"Field relationship missing 'type', skipping: {relation}")
                continue
                
            # Handle different relationship types
            if relation_type == 'mutually_exclusive':
                # Check if 'fields' key exists
                if 'fields' not in relation:
                    logger.warning(f"Mutually exclusive relationship missing 'fields' key, skipping: {relation}")
                    continue
                    
                # Skip if any fields in the relationship are missing
                if not all(field in validated_fields for field in relation['fields']):
                    continue
                
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
            
            elif relation_type == 'required_together':
                # Check if 'fields' key exists
                if 'fields' not in relation:
                    logger.warning(f"Required together relationship missing 'fields' key, skipping: {relation}")
                    continue
                    
                # Skip if any fields in the relationship are missing
                if not all(field in validated_fields for field in relation['fields']):
                    continue
                
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
            
            elif relation_type == 'dependent':
                # Check if required keys exist
                if 'primary' not in relation or 'dependent' not in relation:
                    logger.warning(f"Dependent relationship missing 'primary' or 'dependent' key, skipping: {relation}")
                    continue
                    
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
        confidence_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        total_fields = 0
        
        for field, result in validation_results.items():
            # Skip non-field entries
            if field in ['next_check', 'reasons', 'holistic_validation']:
                continue
            
            confidence_level = result.get('confidence_level', 'LOW')
            confidence_counts[confidence_level] += 1
            total_fields += 1
        
        # Calculate percentages
        if total_fields > 0:
            low_percentage = (confidence_counts["LOW"] / total_fields) * 100
            medium_percentage = (confidence_counts["MEDIUM"] / total_fields) * 100
            
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
            
            if confidence_level != 'HIGH':
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
        
        logger.info(f"Determining next check date for row with {len(validation_results)} validation results")
        
        try:
            # Perform holistic validation
            holistic_result = self.perform_holistic_validation(row, validation_results)
            
            # Log holistic validation results
            logger.info(f"Holistic validation results: {json.dumps(holistic_result, default=str)}")
            
            # Store holistic validation result in the validation_results
            validation_results['holistic_validation'] = holistic_result
            
            # If holistic validation found issues, add to reasons
            if holistic_result["concerns"]:
                logger.info(f"Holistic validation found {len(holistic_result['concerns'])} concerns")
                reasons.extend(holistic_result["concerns"])
            
            # Check individual fields
            for target in self.validation_targets:
                if target.column in validation_results:
                    result = validation_results[target.column]
                    confidence = result.get('confidence', 0.0)
                    validated_value = result.get('value')
                    quote = result.get('quote', '')
                    
                    # Make sure confidence is a float
                    if isinstance(confidence, str):
                        try:
                            confidence = float(confidence)
                        except (ValueError, TypeError):
                            confidence = 0.0
                    
                    if confidence < min_confidence:
                        reason = f"Low confidence ({confidence:.2f}) for {target.column}: {quote}"
                        logger.info(reason)
                        reasons.append(reason)
                        continue
                    
                    if validated_value is None:
                        reason = f"Invalid value for {target.column}: {quote}"
                        logger.info(reason)
                        reasons.append(reason)
                        continue
            
            # Determine when to schedule the next check
            if holistic_result["needs_review"]:
                # If holistic validation indicates need for review, schedule sooner
                next_check = datetime.now() + timedelta(days=1)
                if not reasons:
                    reasons.append("Holistic validation indicates need for review")
                logger.info(f"Setting next check to {next_check} due to need for review")
                return next_check, reasons
            elif reasons:
                # If there are other issues, schedule next check in 1 day
                next_check = datetime.now() + timedelta(days=1)
                logger.info(f"Setting next check to {next_check} due to {len(reasons)} issues found")
                return next_check, reasons
            else:
                # If all validations passed, schedule next check based on cache TTL
                next_check = datetime.now() + timedelta(days=self.cache_ttl_days)
                logger.info(f"Setting next check to {next_check} as all validations passed")
                return next_check, ["All validations passed"]
                
        except Exception as e:
            logger.error(f"Error in determine_next_check_date: {str(e)}")
            logger.error(traceback.format_exc())
            # Return a default date in case of error
            next_check = datetime.now() + timedelta(days=1)
            reasons.append(f"Error determining next check date: {str(e)}")
            return next_check, reasons 