"""
Simplified Schema Validator that auto-generates primary keys from ID importance fields,
uses only the format field, and supports model configuration with per-field overrides.
"""

import logging
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Optional, Set
from datetime import datetime, timedelta
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


def _extract_referenced_citations(text: str) -> Set[int]:
    """Extract citation numbers referenced in text (e.g., [1], [2], [3]).

    Args:
        text: Text that may contain citation references like [1], [2]

    Returns:
        Set of citation numbers found (e.g., {1, 2, 3})
    """
    if not text:
        return set()
    # Match [n] where n is a number (not [QC1] style)
    matches = re.findall(r'\[(\d+)\]', text)
    return {int(m) for m in matches}


def _filter_sources_by_references(sources_full: List[str], referenced_nums: Set[int]) -> List[str]:
    """Filter sources to only include those referenced by number.

    Args:
        sources_full: List of full citation strings like "[1] Title: quote (url)"
        referenced_nums: Set of citation numbers to include (e.g., {1, 2})

    Returns:
        Filtered list of sources that match the referenced numbers
    """
    if not sources_full or not referenced_nums:
        return []

    filtered = []
    for source in sources_full:
        # Extract the citation number from the source (e.g., "[1] ..." -> 1)
        match = re.match(r'^\[(\d+)\]', source.strip())
        if match and int(match.group(1)) in referenced_nums:
            filtered.append(source)

    return filtered

@dataclass
class ValidationTarget:
    column: str
    description: str
    importance: str = "RESEARCH"  # ID, RESEARCH, CRITICAL (backwards compat), IGNORED
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
        
        # Cache TTL: read from config with 1 day default
        self.cache_ttl_days = config.get('cache_ttl_days', 1)
        
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
        logger.debug(f"VALIDATOR_PARSE: Found {len(validation_targets)} validation targets in config")

        for i, target_config in enumerate(validation_targets):
            logger.debug(f"VALIDATOR_PARSE: Processing target {i}: {target_config.get('column', 'NO_COLUMN')} with importance {target_config.get('importance', 'NO_IMPORTANCE')}")
            
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
        
        logger.debug(f"VALIDATOR_PARSE: Created {len(targets)} ValidationTarget objects")
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
        """Get fields with RESEARCH or CRITICAL importance level (backwards compatible)."""
        return [target for target in self.validation_targets if target.importance.upper() in ("RESEARCH", "CRITICAL")]
    
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
        valid_importance = {"ID", "RESEARCH", "CRITICAL", "IGNORED"}  # CRITICAL for backwards compatibility
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
    
    def generate_multiplex_prompt(self, row: Dict[str, Any], targets: List[ValidationTarget], previous_results: Dict[str, Dict[str, Any]] = None, validation_history: Dict[str, Dict[str, Any]] = None, has_web_search: bool = True) -> str:
        """Generate a validation prompt for multiple targets (multiplex) using markdown prompt template.

        Args:
            row: The data row being validated
            targets: List of validation targets (fields to validate)
            previous_results: Results from previous validation groups (optional)
            validation_history: Historical validation data (optional)
            has_web_search: Whether the model has web search capability (default True for Perplexity, False for Anthropic without search)
        """
        # Debug validation history
        if validation_history:
            # Validation history available
            pass
        else:
            # No validation history provided
            pass
        
        # Load multiplex validation prompt from markdown file
        prompts_file = Path(__file__).parent / "prompts" / "multiplex_validation.md"
        try:
            with open(prompts_file, 'r', encoding='utf-8') as f:
                multiplex_prompt_template = f.read()
        except Exception as e:
            logger.error(f"Failed to load multiplex_validation.md: {e}")
            # Fallback to a basic prompt
            return "Please validate the provided fields and return results in JSON format."
        
        # Get general notes from config
        general_notes = self.config.get('general_notes', '')
        
        # Filter out ID fields - we don't validate these, just use them for context
        validation_targets = [t for t in targets if t.importance.upper() != "ID"]
        
        if not validation_targets:
            logger.warning("No non-ID fields to validate in multiplex prompt.")
            return "No fields to validate."
        
        # Build context information (ID fields + additional fields if needed)
        context_lines = []
        id_fields = self.get_id_fields()

        # Debug logging for ID fields
        logger.debug(f"Total validation targets: {len(self.validation_targets)}")
        logger.debug(f"ID fields found: {len(id_fields)}")
        for target in self.validation_targets:
            logger.debug(f"Target: {target.column}, importance: {target.importance}")

        # Add all ID fields to context
        if id_fields:
            logger.debug(f"Processing {len(id_fields)} ID fields for context")
            for id_field in id_fields:
                field_value = row.get(id_field.column, '')
                context_line = f"{id_field.column}: {field_value}"
                context_lines.append(context_line)
                logger.info(f"Added ID context: {context_line}")
        else:
            logger.warning("No ID fields found - will use first 2 RESEARCH fields for context")

        # Ensure at least 2 context fields: if <2 ID fields, add first RESEARCH fields
        if len(context_lines) < 2:
            needed = 2 - len(context_lines)
            logger.info(f"Need {needed} more context fields (have {len(context_lines)})")

            # Get validation targets (RESEARCH fields) that aren't already in context
            existing_context_cols = {line.split(':')[0] for line in context_lines}
            for target in validation_targets:
                if target.column not in existing_context_cols:
                    field_value = row.get(target.column, '')
                    context_line = f"{target.column}: {field_value}"
                    context_lines.append(context_line)
                    logger.info(f"Added additional context field: {context_line}")
                    needed -= 1
                    if needed == 0:
                        break

        context = "\n".join(context_lines) if context_lines else "No context information available."
        logger.info(f"Final context for multiplex prompt ({len(context_lines)} fields): {context}")

        # Build focused research questions (for preliminary search task)
        # Format: Search group name/description, then numbered questions
        research_questions_list = []

        # Get search group information
        group_name = ""
        group_description = ""
        if self.search_groups and validation_targets:
            search_group_id = validation_targets[0].search_group
            for group in self.search_groups:
                if group.get('group_id') == search_group_id:
                    group_name = group.get('group_name', '')
                    group_description = group.get('description', '')
                    break

        # Build the research questions section
        # Start with context
        research_questions_list.append("**Context:**")
        for context_line in context_lines:
            research_questions_list.append(context_line)
        research_questions_list.append("")

        # Add field count and "Research Questions" header
        num_fields = len(validation_targets)
        if num_fields == 1:
            research_questions_list.append("**Research Question:**")
        else:
            research_questions_list.append(f"**{num_fields} Research Questions:**")

        # Add search group name and description (if available)
        if group_name and group_description:
            research_questions_list.append(f"{group_name}: {group_description}")
            research_questions_list.append("")

        # Add each field as a numbered question
        for i, target in enumerate(validation_targets, 1):
            # Use description if available, otherwise use notes
            question_text = target.description if target.description else target.notes

            # Get current value for this field
            current_value = row.get(target.column, '')

            # Format the question
            if num_fields == 1:
                # Single field: no number
                question_line = f"**{target.column}**: {question_text}???"
            else:
                # Multiple fields: numbered
                question_line = f"**{i}. {target.column}**: {question_text}???"

            research_questions_list.append(question_line)

            # Add current value if it exists
            if current_value and str(current_value).strip():
                research_questions_list.append(f"   Current value: {current_value}")

        research_question_section = "\n".join(research_questions_list)

        # Build full original row context (all columns for reference, excluding fields being validated)
        # This gives the AI complete context about the entity, not just ID fields
        original_row_context_lines = []
        validation_target_columns = {t.column for t in validation_targets}
        id_field_columns = {f.column for f in id_fields}

        # Include all columns that are NOT being validated in this call
        for col_name, col_value in row.items():
            # Skip internal fields (start with _)
            if col_name.startswith('_'):
                continue
            # Skip columns being validated (these are shown separately with full details)
            if col_name in validation_target_columns:
                continue
            # Skip ID fields (already shown in primary context above)
            if col_name in id_field_columns:
                continue
            # Skip empty values (no context value)
            if not col_value or str(col_value).strip() == '':
                continue

            # Add this field to original row context
            original_row_context_lines.append(f"{col_name}: {col_value}")

        # Build the full original row context text
        original_row_context = ""
        if original_row_context_lines:
            original_row_context = "\n".join(original_row_context_lines)
            logger.info(f"Added {len(original_row_context_lines)} additional context fields from original row")
        else:
            logger.debug("No additional original row context fields to add")

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

            # Show current value that needs validation/updating
            current_value = row.get(target.column, '')
            field_parts.append(f"**Current Value**: {current_value}")

            field_parts.append(f"Description: {target.description}")

            if target.format:
                field_parts.append(f"Format: {target.format}")

            field_parts.append(f"Importance: {target.importance}")

            # Add notes before examples
            if target.notes:
                field_parts.append(f"\nNotes: {target.notes}")

            # Add examples after notes
            if target.examples:
                field_parts.append("\nExamples:")
                for example in target.examples:
                    field_parts.append(f"  - {example}")

            # Include validation history if available
            if validation_history and target.column in validation_history:
                field_history = validation_history[target.column]

                # Extract citation numbers referenced in current cell value and explanation
                current_value = str(row.get(target.column, ''))
                validator_explanation = field_history.get('validator_explanation', '')
                referenced_nums = _extract_referenced_citations(current_value)
                referenced_nums.update(_extract_referenced_citations(validator_explanation))

                # Previous value from Original Values sheet (historical baseline)
                if field_history.get('original_value'):
                    field_parts.append(f"\n**Previous Value** (from Original Values sheet): {field_history['original_value']}")

                    # Include context from the most recent validation of the previous value
                    if field_history.get('prior_confidence'):
                        field_parts.append(f"  Confidence: {field_history['prior_confidence']}")

                    if field_history.get('original_key_citation'):
                        field_parts.append(f"  Key Citation: {field_history['original_key_citation']}")

                    # Use original_sources_full (numbered citations) if available, filtered to only referenced ones
                    if field_history.get('original_sources_full') and referenced_nums:
                        filtered_sources = _filter_sources_by_references(
                            field_history['original_sources_full'], referenced_nums
                        )
                        if filtered_sources:
                            field_parts.append(f"  Previous Validation Sources:")
                            for source in filtered_sources:
                                field_parts.append(f"    {source}")
                    elif field_history.get('original_sources'):
                        sources_str = ', '.join(field_history['original_sources'])
                        field_parts.append(f"  Sources: {sources_str}")

                # Also show most recent prior validation if different from original_value
                elif field_history.get('prior_value'):
                    prior_ts = field_history.get('prior_timestamp', '')
                    ts_display = f"from {prior_ts}" if prior_ts else "from previous validation"
                    field_parts.append(f"\n**Previous Value** ({ts_display}): {field_history['prior_value']}")

                    if field_history.get('prior_confidence'):
                        field_parts.append(f"  Confidence: {field_history['prior_confidence']}")

                    if field_history.get('original_key_citation'):
                        field_parts.append(f"  Key Citation: {field_history['original_key_citation']}")

                    # Use original_sources_full (numbered citations) if available, filtered to only referenced ones
                    if field_history.get('original_sources_full') and referenced_nums:
                        filtered_sources = _filter_sources_by_references(
                            field_history['original_sources_full'], referenced_nums
                        )
                        if filtered_sources:
                            field_parts.append(f"  Previous Validation Sources:")
                            for source in filtered_sources:
                                field_parts.append(f"    {source}")
                    elif field_history.get('original_sources'):
                        sources_str = ', '.join(field_history['original_sources'])
                        field_parts.append(f"  Sources: {sources_str}")

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
                elif field_name == 'supporting_quotes':
                    example_obj[field_name] = '[1] "exact quote from source" - context'
                elif field_name == 'explanation':
                    example_obj[field_name] = "Succinct reason for this answer"
                elif field_name == 'sources':
                    example_obj[field_name] = ["source URL 1", "source URL 2"]
                elif field_name == 'consistent_with_model_knowledge':
                    example_obj[field_name] = "YES - aligns with general knowledge about this topic"
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
            json_schema_example = json_example  # Just the JSON, no extra text

            # Generate search instruction based on web search availability
            if has_web_search:
                search_instruction = "**Use this section to guide your initial web searches.** Detailed field requirements for synthesis appear below."
            else:
                search_instruction = "**Use this section to focus your analysis.** You will synthesize answers from your knowledge and the detailed context provided below."

            prompt = multiplex_prompt_template.format(
                search_instruction=search_instruction,
                research_questions=research_question_section,
                general_notes=general_notes,
                context=context,
                original_row_context=original_row_context,
                previous_results=previous_results_text,
                fields_to_validate=fields_to_validate,
                json_schema_example=json_schema_example
            )

        except KeyError as e:
            logger.error(f"Missing template key in multiplex_validation.md: {e}")
            return "Template error - please check multiplex_validation.md configuration."
        except Exception as e:
            logger.error(f"Error formatting prompt template: {e}")
            return "Prompt formatting error."
        
        # Clean up multiple consecutive newlines
        while "\n\n\n" in prompt:
            prompt = prompt.replace("\n\n\n", "\n\n")
        
        # LOG IF HISTORY IS IN THE PROMPT
        if validation_history:
            history_included = "Current Value validation context" in prompt or "Prior Value (from Original Values sheet)" in prompt
            logger.info(f"Validation history included in prompt: {history_included}")
            if history_included:
                # Count how many fields have validation context
                context_count = prompt.count("Current Value validation context")
                prior_count = prompt.count("Prior Value (from Original Values sheet)")
                logger.info(f"Fields with validation context: {context_count}, Fields with prior values: {prior_count}")
            else:
                logger.warning("Validation history was provided but NOT included in prompt!")
            
        return prompt
    
    def _expand_confidence(self, val):
        """Expand H/M/L to HIGH/MEDIUM/LOW, handle 'null' string -> None"""
        if val is None or val == 'null' or val == '':
            return None
        if val == 'H': return 'HIGH'
        if val == 'M': return 'MEDIUM'
        if val == 'L': return 'LOW'
        return val  # Already expanded

    def _expand_consistent(self, val):
        """Expand T/F to YES/NO, handle 'null' string -> None"""
        if val is None or val == 'null' or val == '':
            return None
        if val == 'T': return 'YES'
        if val == 'F': return 'NO'
        return val  # Already expanded

    def _parse_nullable_string(self, val):
        """Convert 'null' string to None, empty string to None"""
        if val is None or val == 'null' or val == '':
            return None
        return val

    def parse_multiplex_result(self, result: Dict, row: Dict[str, Any]) -> Dict[str, Tuple[Any, None, List[str], str, str, str, bool, bool, Optional[str]]]:
        """Parse the multiplex validation result from API response (normalized to Perplexity format).

        Supports both formats for backward compatibility:
        - Cell array format: [column, answer, confidence, original_confidence, consistent, explanation]
        - Object array format: [{column, answer, confidence, ...}, ...]
        """
        try:
            # Extract content from API response
            if not isinstance(result, dict) or 'choices' not in result:
                logger.error(f"[PARSE_ERROR] Result missing 'choices' key. Type: {type(result)}, Keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
                # [DEBUG] Check if this is a raw Anthropic response that wasn't normalized
                if isinstance(result, dict) and 'content' in result and 'role' in result:
                    logger.error(f"[PARSE_ERROR] Response appears to be raw Anthropic format - this should have been normalized by ai_client")
                return {}

            content = result['choices'][0]['message'].get('content', '')

            if not content:
                logger.error(f"[PARSE_ERROR] Content is empty - returning empty dict")
                return {}

            # Only log if content is suspiciously short (likely an error)
            if len(content) < 10:
                logger.warning(f"[PARSE_WARN] Suspiciously short content ({len(content)} chars): {content}")

            # Parse JSON response
            try:
                validation_results = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"[PARSE_ERROR] JSON decode failed: {e}")
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
                    logger.error(f"[PARSE_ERROR] Dict missing 'validation_results' key. Keys: {list(validation_results.keys())}")
                    return {}

            # Ensure it's a list
            if not isinstance(validation_results, list):
                logger.error(f"[PARSE_ERROR] Expected list, got {type(validation_results)}")
                return {}

            # Detect format: cell array (list of lists) vs object array (list of dicts)
            if validation_results and len(validation_results) > 0:
                first_item = validation_results[0]
                is_cell_array = isinstance(first_item, list)
            else:
                is_cell_array = False

            parsed_results = {}

            if is_cell_array:
                # Cell array format: [column, answer, confidence, original_confidence, consistent, explanation]
                logger.debug(f"[PARSE_FORMAT] Detected cell array format with {len(validation_results)} items")

                for item in validation_results:
                    if not isinstance(item, list) or len(item) < 6:
                        logger.warning(f"[PARSE_WARN] Skipping invalid cell array item: {item}")
                        continue

                    # Extract values from array positions
                    # Note: With uniform 2D string arrays, "null" comes as string, not None
                    column = item[0] if item[0] and item[0] != 'null' else ''
                    answer = self._parse_nullable_string(item[1])  # Handle "null" string -> None
                    confidence = item[2]  # H/M/L or "null" string
                    original_confidence = item[3]  # H/M/L or "null" string
                    consistent = item[4]  # T/F or "null" string
                    explanation = item[5] if item[5] and item[5] != 'null' else ''

                    if not column:
                        continue

                    # [FIX] Normalize column name to handle Unicode and encoding issues
                    column = unicodedata.normalize('NFC', column).strip()

                    # [DEBUG] Log column parsing for debugging cache mismatches
                    logger.debug(f"[COLUMN_DEBUG] Parsed column: '{column}' (length: {len(column)}, repr: {repr(column)})")

                    # Expand compact values to full format (handles "null" string -> None)
                    confidence_str = self._expand_confidence(confidence)
                    original_confidence_str = self._expand_confidence(original_confidence)
                    consistent_with_model_knowledge = self._expand_consistent(consistent) or ''

                    # Cell array format: sources come from citations metadata, not response
                    sources = []
                    main_source = ""
                    supporting_quotes = ''

                    # Store as tuple with same structure for downstream compatibility
                    # Indices: 0=answer, 1=confidence, 2=sources, 3=confidence_level, 4=main_source,
                    #          5=original_confidence, 6=explanation, 7=consistent, 8=supporting_quotes
                    parsed_results[column] = (
                        answer if answer is not None else '',  # Convert null to empty for value
                        confidence_str if confidence_str else 'LOW',  # Default to LOW for display
                        sources,
                        confidence_str if confidence_str else 'LOW',
                        main_source,
                        original_confidence_str,  # Preserve null for blank originals
                        explanation,
                        consistent_with_model_knowledge,
                        supporting_quotes
                    )
            else:
                # Object array format (legacy): [{column, answer, confidence, ...}, ...]
                logger.debug(f"[PARSE_FORMAT] Detected object array format with {len(validation_results)} items")

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
                    original_confidence = item.get('original_confidence')
                    sources = item.get('sources', [])
                    supporting_quotes = item.get('supporting_quotes', '')
                    explanation = item.get('explanation', '')
                    consistent_with_model_knowledge = item.get('consistent_with_model_knowledge', '')

                    # Keep confidence as string for display (no numeric conversion)
                    confidence_str = confidence_level

                    # Determine main source
                    main_source = sources[0] if sources else ""

                    # Store as tuple: (value, confidence_level, sources, confidence_level, main_source, original_confidence, explanation, consistent_with_model_knowledge, supporting_quotes)
                    # Note: reasoning field removed - use supporting_quotes for quotes and explanation for AI's reasoning
                    parsed_results[column] = (
                        answer,
                        confidence_str,  # [0]
                        sources,  # [1]
                        confidence_str,  # [2]
                        main_source,  # [3]
                        original_confidence,  # [4]
                        explanation,  # [5]
                        consistent_with_model_knowledge,  # [6]
                        supporting_quotes  # [7]
                    )

            return parsed_results

        except Exception as e:
            logger.error(f"Error parsing multiplex result: {str(e)}")
            return {}
    
    def determine_next_check_date(self, row: Dict[str, Any], validation_results: Dict[str, Dict[str, Any]]) -> Tuple[Optional[datetime], List[str]]:
        """Determine when this row should be checked next based on validation results."""
        reasons = []
        base_date = datetime.now()
        
        # Default to cache TTL (configured via cache_ttl_days, defaults to 1 day)
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
                "importance": "RESEARCH",
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