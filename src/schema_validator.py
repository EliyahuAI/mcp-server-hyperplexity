from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger()

@dataclass
class ValidationTarget:
    column: str
    validation_type: str
    rules: Dict[str, Any]
    description: str
    importance: str = "MEDIUM"  # HIGH, MEDIUM, LOW, IGNORED

class SchemaValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_targets = self._parse_validation_targets()
        self.primary_key = config.get('primary_key', [])
        self.cache_ttl_days = config.get('cache_ttl_days', 30)
        self.column_config = config.get('column_config', {})
        
        # Define JSON schemas for API responses
        self._single_column_schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                "quote": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "update_required": {"type": "boolean"}
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
                    "update_required": {"type": "boolean"}
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
                importance=target_config.get('importance', 'MEDIUM')
            )
            targets.append(target)
        return targets
    
    def generate_validation_prompt(self, row: Dict[str, Any], target: ValidationTarget) -> str:
        """Generate a validation prompt for a specific target."""
        # Get column configuration
        column_info = self.column_config.get(target.column, {})
        description = column_info.get('description', target.description)
        format_info = column_info.get('format', '')
        notes = column_info.get('notes', '')
        examples = self._format_examples(target.column)
        
        # Build the prompt
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
            
        prompt += f"""

Please respond in the following JSON format:
{{
    "answer": <the validated value>,
    "confidence": <confidence level: HIGH, MEDIUM, or LOW>,
    "quote": <direct quote from source if available>,
    "sources": [<list of source URLs>],
    "update_required": <true if value needs to be updated>
}}"""
        
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
    
    def parse_validation_result(self, result: Dict, target: ValidationTarget) -> Tuple[Any, float, List[str], str, str, str]:
        """Parse the validation result from Perplexity API response."""
        try:
            # Extract content from API response
            if not isinstance(result, dict) or 'choices' not in result:
                return None, 0.0, [], "LOW", "", ""
            
            content = result['choices'][0]['message'].get('content', '')
            if not content:
                return None, 0.0, [], "LOW", "", ""
            
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
                    return None, 0.0, [], "LOW", "", ""
            
            # Extract values
            answer = validation_result.get('answer', '')
            confidence_level = validation_result.get('confidence', 'LOW')
            quote = validation_result.get('quote', '')
            sources = validation_result.get('sources', [])
            
            # Map confidence level to numeric value
            confidence_map = {"LOW": 0.5, "MEDIUM": 0.8, "HIGH": 0.95}
            numeric_confidence = confidence_map.get(confidence_level, 0.5)
            
            # Get main source if available
            main_source = sources[0] if sources else ""
            
            return answer, numeric_confidence, sources, confidence_level, quote, main_source
            
        except Exception as e:
            logger.error(f"Error parsing validation result: {str(e)}")
            return None, 0.0, [], "LOW", "", ""
    
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