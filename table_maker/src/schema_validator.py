#!/usr/bin/env python3
"""
Schema validator for table generation system.
Validates AI responses against JSON schemas using jsonschema library.
"""

import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import jsonschema
from jsonschema import validate, ValidationError, Draft7Validator

# Configure logging
logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validate AI responses and data structures against JSON schemas."""

    def __init__(self, schemas_dir: str):
        """
        Initialize schema validator.

        Args:
            schemas_dir: Path to directory containing JSON schema files
        """
        self.schemas_dir = Path(schemas_dir)
        if not self.schemas_dir.exists():
            raise ValueError(f"Schemas directory does not exist: {schemas_dir}")

        logger.info(f"Initialized SchemaValidator with directory: {schemas_dir}")

        # Cache loaded schemas
        self._schema_cache: Dict[str, Dict] = {}

    def load_schema(self, schema_name: str) -> Dict:
        """
        Load a JSON schema from file.

        Args:
            schema_name: Name of the schema file (without .json extension)

        Returns:
            Schema dictionary

        Raises:
            FileNotFoundError: If schema file doesn't exist
            json.JSONDecodeError: If schema file is invalid JSON
        """
        # Check cache first
        if schema_name in self._schema_cache:
            logger.debug(f"Using cached schema: {schema_name}")
            return self._schema_cache[schema_name]

        # Construct file path
        if not schema_name.endswith('.json'):
            schema_name = f"{schema_name}.json"

        schema_path = self.schemas_dir / schema_name

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        # Read and parse schema file
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)

            # Validate that the schema itself is valid
            Draft7Validator.check_schema(schema)

            # Cache the schema
            self._schema_cache[schema_name] = schema
            logger.info(f"Loaded schema: {schema_name}")
            return schema

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file {schema_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading schema {schema_path}: {e}")
            raise

    def validate(self, data: Any, schema_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate data against a schema.

        Args:
            data: Data to validate
            schema_name: Name of the schema to validate against

        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        try:
            schema = self.load_schema(schema_name)
            validate(instance=data, schema=schema)
            logger.debug(f"Data validated successfully against schema: {schema_name}")
            return True, None

        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            logger.warning(f"Validation failed for schema {schema_name}: {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error during validation: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def validate_with_details(self, data: Any, schema_name: str) -> Dict[str, Any]:
        """
        Validate data and return detailed validation results.

        Args:
            data: Data to validate
            schema_name: Name of the schema to validate against

        Returns:
            Dictionary with validation results:
            {
                'is_valid': bool,
                'errors': List[str],
                'warnings': List[str],
                'schema_name': str
            }
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'schema_name': schema_name
        }

        try:
            schema = self.load_schema(schema_name)
            validator = Draft7Validator(schema)

            # Collect all validation errors
            errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

            if errors:
                result['is_valid'] = False
                for error in errors:
                    error_msg = self._format_validation_error(error)
                    result['errors'].append(error_msg)

                logger.warning(
                    f"Validation failed for {schema_name} with {len(errors)} error(s)"
                )
            else:
                logger.debug(f"Data validated successfully against schema: {schema_name}")

            # Check for optional fields that are missing (warnings)
            if result['is_valid']:
                warnings = self._check_optional_fields(data, schema)
                result['warnings'] = warnings

        except Exception as e:
            result['is_valid'] = False
            result['errors'].append(f"Unexpected validation error: {str(e)}")
            logger.error(f"Error during validation: {e}")

        return result

    def validate_ai_response(self, response: Dict, expected_schema: str) -> Dict[str, Any]:
        """
        Validate an AI API response against expected schema.

        Args:
            response: AI response dictionary
            expected_schema: Expected schema name

        Returns:
            Validation result dictionary with is_valid, errors, and warnings
        """
        if not isinstance(response, dict):
            return {
                'is_valid': False,
                'errors': [f"Response must be a dictionary, got {type(response).__name__}"],
                'warnings': [],
                'schema_name': expected_schema
            }

        return self.validate_with_details(response, expected_schema)

    def _format_validation_error(self, error: ValidationError) -> str:
        """
        Format a validation error into a readable message.

        Args:
            error: ValidationError from jsonschema

        Returns:
            Formatted error message
        """
        # Build path to the error location
        path = ".".join(str(p) for p in error.path) if error.path else "root"

        # Format the error message
        if error.validator == 'required':
            missing_props = error.message.split("'")[1::2]  # Extract property names
            return f"Missing required field(s) at '{path}': {', '.join(missing_props)}"
        elif error.validator == 'type':
            return f"Type error at '{path}': {error.message}"
        elif error.validator == 'enum':
            return f"Invalid value at '{path}': {error.message}"
        elif error.validator == 'minimum' or error.validator == 'maximum':
            return f"Value out of range at '{path}': {error.message}"
        else:
            return f"Validation error at '{path}': {error.message}"

    def _check_optional_fields(self, data: Dict, schema: Dict) -> List[str]:
        """
        Check for optional fields that are missing (generate warnings).

        Args:
            data: Data to check
            schema: Schema definition

        Returns:
            List of warning messages for missing optional fields
        """
        warnings = []

        # Only check if schema defines properties
        if 'properties' not in schema or 'required' not in schema:
            return warnings

        all_properties = set(schema['properties'].keys())
        required_properties = set(schema.get('required', []))
        optional_properties = all_properties - required_properties
        provided_properties = set(data.keys())

        missing_optional = optional_properties - provided_properties

        for prop in missing_optional:
            warnings.append(f"Optional field '{prop}' not provided")

        return warnings

    def get_schema_required_fields(self, schema_name: str) -> List[str]:
        """
        Get list of required fields from a schema.

        Args:
            schema_name: Name of the schema

        Returns:
            List of required field names
        """
        try:
            schema = self.load_schema(schema_name)
            return schema.get('required', [])
        except Exception as e:
            logger.error(f"Error getting required fields for {schema_name}: {e}")
            return []

    def get_schema_properties(self, schema_name: str) -> Dict[str, Any]:
        """
        Get all properties defined in a schema.

        Args:
            schema_name: Name of the schema

        Returns:
            Dictionary of property definitions
        """
        try:
            schema = self.load_schema(schema_name)
            return schema.get('properties', {})
        except Exception as e:
            logger.error(f"Error getting properties for {schema_name}: {e}")
            return {}

    def clear_cache(self):
        """Clear the schema cache."""
        self._schema_cache.clear()
        logger.info("Cleared schema cache")
