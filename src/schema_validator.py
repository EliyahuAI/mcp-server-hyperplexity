from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging
import re
from pathlib import Path

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
        self.similarity_threshold = config.get('similarity_threshold', 0.8)  # Threshold for determining substantial difference
        
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
    
    def determine_next_check_date(
        self,
        row: Dict[str, Any],
        validation_results: Dict[str, Dict[str, Any]]
    ) -> Tuple[Optional[datetime], List[str]]:
        """Determine the next check date based on validation results."""
        reasons = []
        min_confidence = 0.8  # Minimum confidence threshold
        
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
                    reasons.append(f"Low confidence ({confidence:.2f}) for {target.column}: {quote}")
                    continue
                
                if validated_value is None:
                    reasons.append(f"Invalid value for {target.column}: {quote}")
                    continue
        
        if reasons:
            # If there are issues, schedule next check in 1 day
            next_check = datetime.now() + timedelta(days=1)
            return next_check, reasons
        
        # If all validations passed, schedule next check based on cache TTL
        next_check = datetime.now() + timedelta(days=self.cache_ttl_days)
        return next_check, ["All validations passed"] 