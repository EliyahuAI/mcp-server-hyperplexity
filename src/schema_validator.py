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
            # Extract the content from the API response
            content = result['choices'][0]['message']['content']
            # Parse the JSON response
            validation_result = json.loads(content)
            
            return (
                validation_result.get('validated_value'),
                validation_result.get('confidence', 0.0),
                validation_result.get('message', '')
            )
        except (KeyError, json.JSONDecodeError) as e:
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