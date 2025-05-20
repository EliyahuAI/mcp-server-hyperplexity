from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

@dataclass
class ValidationTarget:
    column: str
    validation_type: str
    rules: Dict[str, Any]
    description: str

class SchemaValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_targets = self._parse_validation_targets()
        self.primary_key = config.get('primary_key', [])
        self.cache_ttl_days = config.get('cache_ttl_days', 30)
    
    def _parse_validation_targets(self) -> List[ValidationTarget]:
        """Parse validation targets from config."""
        targets = []
        for target_config in self.config.get('validation_targets', []):
            target = ValidationTarget(
                column=target_config['column'],
                validation_type=target_config['validation_type'],
                rules=target_config.get('rules', {}),
                description=target_config.get('description', '')
            )
            targets.append(target)
        return targets
    
    def generate_validation_prompt(self, row: Dict[str, Any], target: ValidationTarget) -> str:
        """Generate a validation prompt for a specific target."""
        prompt = f"""Please validate the following data according to these rules:
Column: {target.column}
Validation Type: {target.validation_type}
Rules: {json.dumps(target.rules, indent=2)}
Description: {target.description}

Data to validate:
{json.dumps(row, indent=2)}

Please respond in the following JSON format:
{{
    "validated_value": <the validated value>,
    "confidence": <confidence score between 0 and 1>,
    "message": <explanation of validation result>
}}"""
        return prompt
    
    def parse_validation_result(self, result: Dict, target: ValidationTarget) -> Tuple[Any, float, str]:
        """Parse the validation result from Perplexity API response."""
        try:
            # Log the raw response for debugging
            print(f"Raw API response: {result}")
            
            # Check if we have a valid result structure
            if not isinstance(result, dict) or 'choices' not in result:
                return None, 0.0, f"Invalid API response structure: {str(result)[:100]}..."
            
            # Extract the content from the API response
            if not result.get('choices') or not isinstance(result['choices'], list) or not result['choices'][0].get('message'):
                return None, 0.0, f"Missing content in API response: {str(result)[:100]}..."
            
            content = result['choices'][0]['message'].get('content', '')
            if not content:
                return None, 0.0, "Empty content in API response"
            
            # Look for JSON block in the response
            json_str = ""
            # Check if the content has a JSON code block
            if "```json" in content:
                # Extract the JSON from between ```json and ```
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    json_str = content[json_start:json_end].strip()
            else:
                # Try to parse the whole content as JSON
                json_str = content
            
            # Parse the JSON response
            try:
                validation_result = json.loads(json_str)
                print(f"Successfully parsed JSON: {validation_result}")
                
                return (
                    validation_result.get('validated_value'),
                    validation_result.get('confidence', 0.0),
                    validation_result.get('message', '')
                )
            except json.JSONDecodeError as json_err:
                print(f"JSON parsing error: {json_err} - Content: {json_str[:100]}")
                # Fallback to regex parsing
                import re
                validated_value = None
                confidence = 0.0
                message = ""
                
                # Try to extract data using regex patterns
                value_match = re.search(r'"validated_value"\s*:\s*"([^"]*)"', content)
                if value_match:
                    validated_value = value_match.group(1)
                
                confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', content)
                if confidence_match:
                    try:
                        confidence = float(confidence_match.group(1))
                    except:
                        confidence = 0.0
                
                message_match = re.search(r'"message"\s*:\s*"([^"]*)"', content)
                if message_match:
                    message = message_match.group(1)
                
                if validated_value and message:
                    print(f"Extracted values using regex: {validated_value}, {confidence}, {message}")
                    return validated_value, confidence, message
                
                # If all else fails, return the content as the message
                return target.column, 0.5, f"Could not parse JSON, using raw content: {content[:100]}..."
                
        except (KeyError, Exception) as e:
            return None, 0.0, f"Error parsing validation result: {str(e)}"
    
    def determine_next_check_date(
        self,
        row: Dict[str, Any],
        validation_results: Dict[str, Tuple[Any, float, str]]
    ) -> Tuple[Optional[datetime], List[str]]:
        """Determine the next check date based on validation results."""
        reasons = []
        min_confidence = 0.8  # Minimum confidence threshold
        
        for target in self.validation_targets:
            if target.column in validation_results:
                validated_value, confidence, message = validation_results[target.column]
                
                if confidence < min_confidence:
                    reasons.append(f"Low confidence ({confidence:.2f}) for {target.column}: {message}")
                    continue
                
                if validated_value is None:
                    reasons.append(f"Invalid value for {target.column}: {message}")
                    continue
        
        if reasons:
            # If there are issues, schedule next check in 1 day
            next_check = datetime.now() + timedelta(days=1)
            return next_check, reasons
        
        # If all validations passed, schedule next check based on cache TTL
        next_check = datetime.now() + timedelta(days=self.cache_ttl_days)
        return next_check, ["All validations passed"] 