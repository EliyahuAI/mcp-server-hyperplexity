"""
Simplified Schema Validator that auto-generates primary keys from ID importance fields,
uses only the format field, and supports model configuration with per-field overrides.
"""

import logging
import json
import unicodedata
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ValidationTarget:
    column: str
    description: str
    importance: str = "MEDIUM"  # ID, CRITICAL, HIGH, MEDIUM, LOW, IGNORED
    format: str = "String"
    notes: str = ""
    examples: List[str] = None
    search_group: int = 0
    preferred_model: Optional[str] = None  # Override for specific fields
    search_context_size: Optional[str] = None  # "low", "medium", "high"

    def __post_init__(self):
        if self.examples is None:
            self.examples = []

class SimplifiedSchemaValidator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.validation_targets = self._parse_validation_targets()
        
        # Auto-generate primary_key from ID importance fields
        self.primary_key = self._generate_primary_key()
        
        # Hardcoded cache TTL to 30 days
        self.cache_ttl_days = 30
        
        # Model configuration
        self.default_model = config.get('default_model', 'sonar-pro')
        
        # Search context size configuration
        self.default_search_context_size = config.get('default_search_context_size', 'low')
        
        # Search groups configuration (optional)
        self.search_groups = config.get('search_groups', [])
        # logger.debug(f"VALIDATOR_INIT: Loaded {len(self.search_groups)} search group definitions: {self.search_groups}")
        logger.debug(f"VALIDATOR_INIT: Loaded {len(self.search_groups)} search group definitions: {self.search_groups}")
        
        # Debug each search group
        for i, group in enumerate(self.search_groups):
            # logger.debug(f"VALIDATOR_INIT: Group {i}: {group}")
            logger.debug(f"VALIDATOR_INIT: Group {i}: {group}")
        
        # Build column_config from validation_targets
        self.column_config = self._build_column_config()
        
        self.similarity_threshold = config.get('similarity_threshold', 0.8)
        
        logger.info(f"Initialized with auto-generated primary_key: {self.primary_key}")
        logger.info(f"Default model: {self.default_model}")
        logger.info(f"Column config built for {len(self.column_config)} columns")
    
    def _parse_validation_targets(self) -> List[ValidationTarget]:
        """Parse validation targets from simplified config."""
        targets = []
        validation_targets = self.config.get('validation_targets', [])
        # logger.debug(f"VALIDATOR_PARSE: Found {len(validation_targets)} validation targets in config")
        logger.info(f"VALIDATOR_PARSE: Found {len(validation_targets)} validation targets in config")
        
        for i, target_config in enumerate(validation_targets):
            # logger.debug(f"VALIDATOR_PARSE: Processing target {i}: {target_config.get('column', 'NO_COLUMN')} with importance {target_config.get('importance', 'NO_IMPORTANCE')}")
            logger.info(f"VALIDATOR_PARSE: Processing target {i}: {target_config.get('column', 'NO_COLUMN')} with importance {target_config.get('importance', 'NO_IMPORTANCE')}")
            
            target = ValidationTarget(
                column=target_config['column'],
                description=target_config.get('description', ''),
                importance=target_config.get('importance', 'MEDIUM'),
                format=target_config.get('format', 'String'),
                notes=target_config.get('notes', ''),
                examples=target_config.get('examples', []),
                search_group=target_config.get('search_group', 0),
                preferred_model=target_config.get('preferred_model'),
                search_context_size=target_config.get('search_context_size')
            )
            targets.append(target)
        
        # logger.debug(f"VALIDATOR_PARSE: Created {len(targets)} ValidationTarget objects")
        logger.info(f"VALIDATOR_PARSE: Created {len(targets)} ValidationTarget objects")
        return targets
    
    def _generate_primary_key(self) -> List[str]:
        """Auto-generate primary key from fields with ID importance, in order of appearance."""
        id_fields = []
        for target in self.validation_targets:
            if target.importance.upper() == "ID":
                id_fields.append(target.column)
        
        if not id_fields:
            logger.warning("No ID importance fields found, using first column as primary key")
            if self.validation_targets:
                return [self.validation_targets[0].column]
            else:
                return ["id"]  # fallback
        
        return id_fields
    
    def _build_column_config(self) -> Dict[str, Dict[str, Any]]:
        """Build column configuration from validation targets."""
        column_config = {}
        for target in self.validation_targets:
            column_config[target.column] = {
                'description': target.description,
                'format': target.format,
                'notes': target.notes,
                'examples': target.examples,
                'importance': target.importance,
                'search_group': target.search_group,
                'preferred_model': target.preferred_model,
                'search_context_size': target.search_context_size
            }
        return column_config
    
    def get_model_for_field(self, column: str) -> str:
        """Get the model to use for a specific field (preferred_model or default)."""
        column_info = self.column_config.get(column, {})
        preferred_model = column_info.get('preferred_model')
        return preferred_model if preferred_model else self.default_model
    
    def get_search_context_size_for_field(self, column: str) -> str:
        """Get the search context size to use for a specific field."""
        column_info = self.column_config.get(column, {})
        search_context_size = column_info.get('search_context_size')
        return search_context_size if search_context_size else self.default_search_context_size
    
    def get_id_fields(self) -> List[ValidationTarget]:
        """Get fields with ID importance level."""
        id_fields = [target for target in self.validation_targets if target.importance.upper() == "ID"]
        logger.debug(f"get_id_fields() found {len(id_fields)} ID fields from {len(self.validation_targets)} total targets")
        return id_fields
    
    def get_ignored_fields(self) -> List[ValidationTarget]:
        """Get fields with IGNORED importance level."""
        return [target for target in self.validation_targets if target.importance.upper() == "IGNORED"]
    
    def get_validation_fields(self) -> List[ValidationTarget]:
        """Get fields that should be validated (not ID or IGNORED)."""
        return [target for target in self.validation_targets 
                if target.importance.upper() not in ["ID", "IGNORED"]]
    
    def get_critical_fields(self) -> List[ValidationTarget]:
        """Get fields with CRITICAL importance level."""
        return [target for target in self.validation_targets if target.importance.upper() == "CRITICAL"]
    
    def group_by_search_group(self, targets: List[ValidationTarget] = None) -> Dict[int, List[ValidationTarget]]:
        """Group validation targets by search_group for multiplexing."""
        if targets is None:
            targets = self.get_validation_fields()
        
        grouped = {}
        for target in targets:
            if target.search_group not in grouped:
                grouped[target.search_group] = []
            grouped[target.search_group].append(target)
        return grouped
    
    def group_columns_by_search_group(self, targets: List[ValidationTarget]) -> Dict[int, List[ValidationTarget]]:
        """Group validation targets by search_group for multiplexing (alias for compatibility)."""
        return self.group_by_search_group(targets)
    
    def group_by_model(self, targets: List[ValidationTarget] = None) -> Dict[str, List[ValidationTarget]]:
        """Group validation targets by model for batch processing."""
        if targets is None:
            targets = self.get_validation_fields()
        
        grouped = {}
        for target in targets:
            model = target.preferred_model if target.preferred_model else self.default_model
            if model not in grouped:
                grouped[model] = []
            grouped[model].append(target)
        return grouped
    
    def generate_row_key(self, row: Dict[str, Any]) -> str:
        """Generate a unique row key using the centralized function."""
        from row_key_utils import generate_row_key
        return generate_row_key(row, self.primary_key)
    
    def format_examples(self, column: str) -> str:
        """Format examples for a column."""
        column_info = self.column_config.get(column, {})
        examples = column_info.get('examples', [])
        
        if not examples:
            return ""
        
        formatted_examples = []
        for example in examples:
            if isinstance(example, str) and example.strip():
                formatted_examples.append(f"  - {example}")
        
        return "\n".join(formatted_examples) if formatted_examples else ""
    
    def get_context_info(self, row: Dict[str, Any]) -> str:
        """Get context information from ID fields."""
        context_lines = []
        id_fields = self.get_id_fields()
        
        for id_field in id_fields:
            value = row.get(id_field.column, '')
            context_lines.append(f"{id_field.column}: {value}")
        
        return "\n".join(context_lines)
    
    def validate_config(self) -> List[str]:
        """Validate the configuration and return any issues."""
        issues = []
        
        # Check if we have any validation targets
        if not self.validation_targets:
            issues.append("No validation targets defined")
        
        # Check if we have at least one ID field
        id_fields = self.get_id_fields()
        if not id_fields:
            issues.append("No ID importance fields defined - primary key will be auto-generated from first column")
        
        # Check for duplicate column names
        column_names = [target.column for target in self.validation_targets]
        if len(column_names) != len(set(column_names)):
            issues.append("Duplicate column names found in validation targets")
        
        # Check for valid importance levels
        valid_importance = {"ID", "CRITICAL", "HIGH", "MEDIUM", "LOW", "IGNORED"}
        for target in self.validation_targets:
            if target.importance.upper() not in valid_importance:
                issues.append(f"Invalid importance level '{target.importance}' for column '{target.column}'")
        
        # Check model configuration
        if not self.default_model:
            issues.append("No default_model specified")
        
        return issues
    
    def get_model_usage_summary(self) -> Dict[str, List[str]]:
        """Get a summary of which fields use which models."""
        model_usage = {}
        for target in self.validation_targets:
            model = target.preferred_model if target.preferred_model else self.default_model
            if model not in model_usage:
                model_usage[model] = []
            model_usage[model].append(target.column)
        return model_usage
    
    def generate_multiplex_prompt(self, row: Dict[str, Any], targets: List[ValidationTarget], previous_results: Dict[str, Dict[str, Any]] = None, validation_history: Dict[str, List[Dict[str, Any]]] = None) -> str:
        """Generate a validation prompt for multiple targets (multiplex) using prompts.yml template."""
        # Debug validation history
        if validation_history:
            # Validation history available
            pass
        else:
            # No validation history provided
            pass
        
        # Load prompts from YAML file
        prompts_file = Path(__file__).parent / "prompts.yml"
        try:
            with open(prompts_file, 'r', encoding='utf-8') as f:
                prompts = yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load prompts.yml: {e}")
            # Fallback to a basic prompt
            return "Please validate the provided fields and return results in JSON format."
        
        # Get general notes from config
        general_notes = self.config.get('general_notes', '')
        
        # Filter out ID fields - we don't validate these, just use them for context
        validation_targets = [t for t in targets if t.importance.upper() != "ID"]
        
        if not validation_targets:
            logger.warning("No non-ID fields to validate in multiplex prompt.")
            return "No fields to validate."
        
        # Build validation intro
        if len(validation_targets) == 1:
            validation_intro = f"Please validate the following field: {validation_targets[0].column}"
        else:
            validation_intro = f"Please validate the following {len(validation_targets)} fields:"
        
        # Build context information (ID fields)
        context_lines = []
        id_fields = self.get_id_fields()

        # Debug logging for ID fields
        logger.info(f"Total validation targets: {len(self.validation_targets)}")
        logger.info(f"ID fields found: {len(id_fields)}")
        for target in self.validation_targets:
            logger.info(f"Target: {target.column}, importance: {target.importance}")

        if id_fields:
            logger.info(f"Processing {len(id_fields)} ID fields for context")
            for id_field in id_fields:
                field_value = row.get(id_field.column, '')
                context_line = f"{id_field.column}: {field_value}"
                context_lines.append(context_line)
                logger.info(f"Added ID context: {context_line}")
        else:
            logger.warning("No ID fields found - context will be empty")

        context = "\n".join(context_lines) if context_lines else "No context information available."
        logger.info(f"Final context for multiplex prompt: {context}")
        
        # Build previous validation results
        previous_results_text = ""
        if previous_results and len(previous_results) > 0:
            prev_lines = []
            for col, result in previous_results.items():
                confidence_level = result.get('confidence_level', 'UNKNOWN')
                value = result.get('value', '')
                prev_lines.append(f"{col}: {value} (Confidence: {confidence_level})")
            previous_results_text = "\n".join(prev_lines)
        else:
            previous_results_text = "No previous validation results available."
        
        # Build fields to validate section
        fields_parts = []
        for i, target in enumerate(validation_targets, 1):
            field_parts = []
            field_parts.append(f"----- FIELD {i}: {target.column} -----")
            field_parts.append(f"Current Value: {row.get(target.column, '')}")
            field_parts.append(f"Description: {target.description}")
            
            if target.format:
                field_parts.append(f"Format: {target.format}")
                
            field_parts.append(f"Importance: {target.importance}")
            
            if target.notes:
                field_parts.append(f"Notes: {target.notes}")
            
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
                for entry in entries[:3]:
                    timestamp = entry.get('timestamp', 'Unknown date')
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
                        shortened_quote = quote[:100] + ("..." if len(quote) > 100 else "")
                        history_entry += f" - Source quote: \"{shortened_quote}\""
                    
                    field_parts.append(history_entry)
            
            # Include examples if available
            if target.examples:
                field_parts.append("Examples:")
                for example in target.examples:
                    field_parts.append(f"  - {example}")
            
            fields_parts.append("\n".join(field_parts))
        
        fields_to_validate = "\n\n".join(fields_parts)
        
        # Single field note for response format
        single_field_note = ""
        if len(validation_targets) == 1:
            single_field_note = f"Even though there is only 1 field ({validation_targets[0].column}), still return an array with a single object."
        
        # Format the template
        try:
            # Generate JSON schema example from the actual schema
            from perplexity_schema import MULTIPLEX_RESPONSE_SCHEMA
            
            # Extract the schema structure to create a readable example
            item_schema = MULTIPLEX_RESPONSE_SCHEMA.get('items', {})
            properties = item_schema.get('properties', {})
            required_fields = item_schema.get('required', [])
            
            # Build example JSON structure
            example_obj = {}
            for field_name, field_def in properties.items():
                field_type = field_def.get('type', 'string')
                description = field_def.get('description', '')
                
                if field_name == 'column':
                    example_obj[field_name] = "field name"
                elif field_name == 'answer':
                    example_obj[field_name] = "validated value"
                elif field_name == 'confidence':
                    example_obj[field_name] = "HIGH|MEDIUM|LOW"
                elif field_name == 'original_confidence':
                    example_obj[field_name] = "HIGH|MEDIUM|LOW|null"
                elif field_name == 'quote':
                    example_obj[field_name] = "direct quote from source if available"
                elif field_name == 'sources':
                    example_obj[field_name] = ["source URL 1", "source URL 2"]
                elif field_name in ['update_required', 'substantially_different']:
                    example_obj[field_name] = "true/false"
                elif field_name == 'consistent_with_model_knowledge':
                    example_obj[field_name] = "YES/NO followed by brief explanation"
                else:
                    # Generic handling for other fields
                    if field_type == 'boolean':
                        example_obj[field_name] = "true/false"
                    elif field_type == 'array':
                        example_obj[field_name] = ["example values"]
                    else:
                        example_obj[field_name] = f"example {field_name}"
            
            # Format as JSON example
            import json
            json_example = json.dumps([example_obj], indent=2)
            json_schema_example = f"Each object must have the following structure:\n\n{json_example}"
            
            # Get group information from search_groups for the fields being validated
            group_name = ""
            group_description = ""
            
            # Find the most relevant search group for the fields being validated
            if self.search_groups and validation_targets:
                # Get the search group ID from the first validation target
                search_group_id = validation_targets[0].search_group
                
                # Find the corresponding search group
                for group in self.search_groups:
                    if group.get('group_id') == search_group_id:
                        group_name = group.get('group_name', '')
                        group_description = group.get('description', '')
                        break
                
                # If no match found, use the first search group as fallback
                if not group_name and self.search_groups:
                    first_group = self.search_groups[0]
                    group_name = first_group.get('group_name', '')
                    group_description = first_group.get('description', '')
            
            # Format group information (only include if values exist)
            group_name_text = f"Group: {group_name}" if group_name else ""
            group_description_text = f"Description: {group_description}" if group_description else ""
            
            # Log for debugging
            logger.info(f"Search groups available: {len(self.search_groups)}")
            logger.info(f"Group name from search_groups: '{group_name}'")
            logger.info(f"Group description from search_groups: '{group_description}'")
            
            prompt = prompts['multiplex_validation'].format(
                validation_intro=validation_intro,
                group_name=group_name_text,
                group_description=group_description_text,
                general_notes=general_notes,
                context=context,
                previous_results=previous_results_text,
                fields_to_validate=fields_to_validate,
                single_field_note=single_field_note,
                json_schema_example=json_schema_example
            )
            
        except KeyError as e:
            logger.error(f"Missing template key in prompts.yml: {e}")
            return "Template error - please check prompts.yml configuration."
        except Exception as e:
            logger.error(f"Error formatting prompt template: {e}")
            return "Prompt formatting error."
        
        # Clean up multiple consecutive newlines
        while "\n\n\n" in prompt:
            prompt = prompt.replace("\n\n\n", "\n\n")
        
        # LOG IF HISTORY IS IN THE PROMPT
        if validation_history:
            history_included = "Previous validation entries:" in prompt
            logger.info(f"Validation history included in prompt: {history_included}")
            if history_included:
                # Count how many history entries are in the prompt
                history_count = prompt.count("- [20")  # Dates start with [20xx
                logger.info(f"Number of history entries in prompt: {history_count}")
            else:
                logger.warning("Validation history was provided but NOT included in prompt!")
            
        return prompt
    
    def parse_multiplex_result(self, result: Dict, row: Dict[str, Any]) -> Dict[str, Tuple[Any, None, List[str], str, str, str, bool, bool, Optional[str]]]:
        """Parse the multiplex validation result from API response (normalized to Perplexity format)."""
        try:
            # Extract content from API response
            if not isinstance(result, dict) or 'choices' not in result:
                return {}
            
            content = result['choices'][0]['message'].get('content', '')
            if not content:
                return {}
            
            # Parse JSON response
            try:
                validation_results = json.loads(content)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code block
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        validation_results = json.loads(content[json_start:json_end].strip())
                    else:
                        return {}
                else:
                    return {}

            # Handle different response formats from Perplexity
            # If it's a dict with 'validation_results' key, extract it (json_schema wrapper)
            if isinstance(validation_results, dict):
                if 'validation_results' in validation_results:
                    validation_results = validation_results['validation_results']
                else:
                    return {}

            # Ensure it's a list
            if not isinstance(validation_results, list):
                return {}
            
            parsed_results = {}
            
            for item in validation_results:
                if not isinstance(item, dict):
                    continue

                column = item.get('column', '')
                if not column:
                    continue

                # [FIX] Normalize column name to handle Unicode and encoding issues
                column = unicodedata.normalize('NFC', column).strip()

                # [DEBUG] Log column parsing for debugging cache mismatches
                logger.debug(f"[COLUMN_DEBUG] Parsed column: '{column}' (length: {len(column)}, repr: {repr(column)})")
                
                answer = item.get('answer', '')
                confidence_level = item.get('confidence', 'LOW')
                original_confidence = item.get('original_confidence')  # New field
                reasoning = item.get('reasoning', item.get('quote', ''))  # Support both old and new field names
                sources = item.get('sources', [])
                explanation = item.get('explanation', '')
                consistent_with_model_knowledge = item.get('consistent_with_model_knowledge', '')
                
                # Keep confidence as string for display (no numeric conversion)
                confidence_str = confidence_level
                
                # Determine main source
                main_source = sources[0] if sources else ""
                
                # Store as tuple: (value, confidence_level, sources, confidence_level, reasoning, main_source, original_confidence, explanation, consistent_with_model_knowledge)
                parsed_results[column] = (
                    answer,
                    confidence_str,  # String confidence, not numeric
                    sources,
                    confidence_str,  # Keep as string
                    reasoning,  # Changed from quote
                    main_source,
                    original_confidence,  # New field
                    explanation,  # New field
                    consistent_with_model_knowledge
                )
            
            return parsed_results
            
        except Exception as e:
            logger.error(f"Error parsing multiplex result: {str(e)}")
            return {}
    
    def determine_next_check_date(self, row: Dict[str, Any], validation_results: Dict[str, Dict[str, Any]]) -> Tuple[Optional[datetime], List[str]]:
        """Determine when this row should be checked next based on validation results."""
        reasons = []
        base_date = datetime.now()
        
        # Default to cache TTL (30 days)
        next_check_days = self.cache_ttl_days
        
        # Check for low confidence results
        low_confidence_count = 0
        high_confidence_count = 0
        
        for field, result in validation_results.items():
            if field in ['next_check', 'reasons']:
                continue
                
            confidence_level = result.get('confidence_level', 'LOW')
            if confidence_level == 'LOW':
                low_confidence_count += 1
            elif confidence_level == 'HIGH':
                high_confidence_count += 1
        
        # Adjust check frequency based on confidence
        if low_confidence_count > 0:
            # Check sooner if we have low confidence results
            next_check_days = min(next_check_days, 7)  # Check within a week
            reasons.append(f"Low confidence results found ({low_confidence_count} fields)")
        
        # Check for critical fields with updates
        critical_updates = 0
        for target in self.get_critical_fields():
            if target.column in validation_results:
                result = validation_results[target.column]
                if result.get('update_required', False):
                    critical_updates += 1
        
        if critical_updates > 0:
            next_check_days = min(next_check_days, 14)  # Check within 2 weeks
            reasons.append(f"Critical field updates required ({critical_updates} fields)")
        
        # If everything is high confidence, extend the check period
        if low_confidence_count == 0 and len(validation_results) > 2:
            next_check_days = min(next_check_days * 2, 60)  # Up to 2 months
            reasons.append("All results have medium or high confidence")
        
        if not reasons:
            reasons.append("Standard cache TTL")
        
        next_check = base_date + timedelta(days=next_check_days)
        return next_check, reasons

# Example usage and migration helper
def migrate_old_config_to_simplified(old_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate an old configuration format to the simplified format.
    Removes validation_type, rules, field_relationships, and primary_key.
    Adds model configuration and hardcodes cache TTL.
    """
    new_config = {
        "general_notes": old_config.get("general_notes", ""),
        "default_model": "sonar-pro",  # Default model
        "validation_targets": []
    }
    
    # Process validation targets
    for old_target in old_config.get("validation_targets", []):
        new_target = {
            "column": old_target["column"],
            "description": old_target.get("description", ""),
            "importance": old_target.get("importance", "MEDIUM"),
            "format": old_target.get("format", "String"),
            "notes": old_target.get("notes", ""),
            "examples": old_target.get("examples", []),
            "search_group": old_target.get("search_group", 0)
        }
        
        # Add preferred_model if specified in old config (unlikely but possible)
        if "preferred_model" in old_target:
            new_target["preferred_model"] = old_target["preferred_model"]
        
        new_config["validation_targets"].append(new_target)
    
    return new_config

if __name__ == "__main__":
    # Example of how to use the simplified validator
    sample_config = {
        "general_notes": "Sample configuration",
        "default_model": "sonar-pro",
        "validation_targets": [
            {
                "column": "Product Name",
                "description": "Product identifier",
                "importance": "ID",
                "format": "String",
                "examples": ["Product-A", "Product-B"]
            },
            {
                "column": "Status",
                "description": "Current status",
                "importance": "CRITICAL",
                "format": "String",
                "examples": ["Active", "Inactive"]
            },
            {
                "column": "Complex Field",
                "description": "Field requiring special model",
                "importance": "HIGH",
                "format": "String",
                "preferred_model": "claude-3-opus"
            }
        ]
    }
    
    validator = SimplifiedSchemaValidator(sample_config)
    print(f"Auto-generated primary key: {validator.primary_key}")
    print(f"Default model: {validator.default_model}")
    print(f"Model for 'Status': {validator.get_model_for_field('Status')}")
    print(f"Model for 'Complex Field': {validator.get_model_for_field('Complex Field')}")
    print(f"Model usage summary: {validator.get_model_usage_summary()}")
    print(f"Validation issues: {validator.validate_config()}") 