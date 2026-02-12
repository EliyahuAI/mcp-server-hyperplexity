#!/usr/bin/env python3
"""
AI-Powered JSON Patch Utilities
Generalizable tools for using JSON Patch (RFC 6902) with LLMs for structured data refinement.

This module provides reusable utilities for:
1. Creating patch-based refinement schemas
2. Safely applying patches with validation and fallback
3. Building prompts for patch-based refinements
4. Integrating with ai_api_client for any refinement task

Usage Example:
    from shared.ai_patch_utils import PatchRefinementManager

    manager = PatchRefinementManager(
        original_data=my_config,
        validator_fn=validate_my_config,
        schema=my_config_schema
    )

    result = await manager.refine_with_patches(
        instructions="Change importance to RESEARCH",
        context={"validation_results": results}
    )
"""

import json
import logging
from typing import Dict, Any, Optional, Callable, List, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import jsonpatch, but don't fail if not available
try:
    import jsonpatch
    JSONPATCH_AVAILABLE = True
except ImportError:
    JSONPATCH_AVAILABLE = False
    logger.warning("jsonpatch library not available. Install with: pip install jsonpatch")


@dataclass
class PatchResult:
    """Result of applying patches to an object"""
    success: bool
    patched_data: Optional[Dict] = None
    error: Optional[str] = None
    validation_errors: Optional[List[str]] = None
    patch_operations: Optional[List[Dict]] = None
    method: str = "unknown"  # "patch", "fallback", "failed"


@dataclass
class RefinementResult:
    """Complete result from AI-powered refinement"""
    success: bool
    updated_data: Optional[Dict] = None
    reasoning: str = ""
    clarifying_questions: str = ""
    clarification_urgency: float = 0.0
    ai_summary: str = ""
    method: str = "unknown"  # "json_patch", "full_replacement", "failed"
    patch_operations: Optional[List[Dict]] = None

    # Cost/usage tracking
    eliyahu_cost: float = 0.0
    token_usage: Optional[Dict] = None
    enhanced_data: Optional[Dict] = None
    processing_time: float = 0.0

    # Error details
    error: Optional[str] = None
    error_type: Optional[str] = None


def create_patch_schema(
    base_schema: Dict[str, Any],
    description: str = "JSON Patch operations for refining the data",
    include_reasoning: bool = True,
    include_questions: bool = True,
    additional_fields: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a JSON Patch refinement schema by wrapping a base schema.

    This is a reusable schema factory that works with any structured data type.

    Args:
        base_schema: The JSON schema for the object being refined
        description: Description of what the patches will modify
        include_reasoning: Include reasoning field in response
        include_questions: Include clarifying_questions field
        additional_fields: Additional custom fields to add to the schema

    Returns:
        A complete schema for AI responses with patch operations

    Example:
        >>> config_schema = load_config_schema()
        >>> patch_schema = create_patch_schema(
        ...     base_schema=config_schema,
        ...     description="Patches to refine validation configuration",
        ...     include_questions=True
        ... )
    """
    required_fields = ["patch_operations"]

    properties = {
        "patch_operations": {
            "type": "array",
            "description": f"{description}. Use RFC 6902 JSON Patch format.",
            "items": {
                "type": "object",
                "required": ["op", "path"],
                "properties": {
                    "op": {
                        "type": "string",
                        "enum": ["add", "remove", "replace", "test", "move", "copy"],
                        "description": (
                            "Operation type:\n"
                            "- 'replace': Change existing field value\n"
                            "- 'add': Add new field or array element\n"
                            "- 'remove': Delete field or array element\n"
                            "- 'test': Verify expected value (safety check)\n"
                            "- 'move': Move value from one path to another\n"
                            "- 'copy': Copy value from one path to another"
                        )
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "JSON Pointer path (RFC 6901). Examples:\n"
                            "- '/field_name' for top-level field\n"
                            "- '/array/3/subfield' for nested array (0-indexed)\n"
                            "- '/object/nested/field' for nested object"
                        )
                    },
                    "value": {
                        "description": "Value to add/replace. Not needed for 'remove' or 'test' operations."
                    },
                    "from": {
                        "type": "string",
                        "description": "Source path for 'move' and 'copy' operations"
                    }
                },
                "additionalProperties": False
            },
            "minItems": 1
        }
    }

    if include_reasoning:
        required_fields.append("reasoning")
        properties["reasoning"] = {
            "type": "string",
            "description": "Clear explanation of why these changes address the user's request"
        }

    if include_questions:
        properties["clarifying_questions"] = {
            "type": "string",
            "description": "Questions to clarify ambiguous aspects (2-3 max, use lay-person language)"
        }
        properties["clarification_urgency"] = {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": (
                "Urgency of clarification (0-1):\n"
                "0.0-0.1 = Minimal, 0.2-0.3 = Low (typical for refinements),\n"
                "0.4-0.6 = Moderate, 0.7-0.8 = High, 0.9-1.0 = Critical"
            )
        }

    properties["ai_summary"] = {
        "type": "string",
        "description": "Brief 1-3 sentence summary of changes in plain language"
    }

    # Add any additional custom fields
    if additional_fields:
        properties.update(additional_fields)
        required_fields.extend(additional_fields.keys())

    return {
        "title": "Patch-Based Refinement Response",
        "description": f"Response schema for patch-based refinement. {description}",
        "type": "object",
        "required": required_fields,
        "properties": properties,
        "additionalProperties": False
    }


def apply_patches_with_validation(
    original_data: Dict[str, Any],
    patch_operations: List[Dict[str, Any]],
    validator_fn: Optional[Callable[[Dict], Tuple[bool, List[str], List[str]]]] = None,
    dry_run: bool = False
) -> PatchResult:
    """
    Safely apply JSON Patch operations with optional validation.

    Args:
        original_data: The original object to patch
        patch_operations: List of RFC 6902 patch operations
        validator_fn: Optional validation function that returns (is_valid, errors, warnings)
        dry_run: If True, validate patches but don't apply them

    Returns:
        PatchResult with success status and patched data or error details

    Example:
        >>> def validate_config(config):
        ...     errors = []
        ...     if not config.get('search_groups'):
        ...         errors.append("Missing search_groups")
        ...     return (len(errors) == 0, errors, [])
        ...
        >>> result = apply_patches_with_validation(
        ...     original_data=my_config,
        ...     patch_operations=patches,
        ...     validator_fn=validate_config
        ... )
        >>> if result.success:
        ...     use_data(result.patched_data)
    """
    if not JSONPATCH_AVAILABLE:
        return PatchResult(
            success=False,
            error="jsonpatch library not installed. Install with: pip install jsonpatch",
            method="failed"
        )

    if not patch_operations:
        logger.warning("No patch operations provided")
        return PatchResult(
            success=False,
            error="No patch operations to apply",
            method="failed"
        )

    try:
        # Create patch object
        patch = jsonpatch.JsonPatch(patch_operations)
        logger.info(f"Created patch with {len(patch_operations)} operations")

        # Log operations for debugging
        for i, op in enumerate(patch_operations):
            logger.debug(f"  Op {i+1}: {op.get('op')} {op.get('path')}")

        if dry_run:
            logger.info("Dry run mode - validating patch without applying")
            # Just validate the patch is well-formed
            try:
                # Create a deep copy to test on
                import copy
                test_data = copy.deepcopy(original_data)
                patch.apply(test_data)
                logger.info("✅ Patch validation successful (dry run)")
                return PatchResult(
                    success=True,
                    patched_data=None,
                    patch_operations=patch_operations,
                    method="dry_run"
                )
            except Exception as e:
                logger.error(f"❌ Patch validation failed: {e}")
                return PatchResult(
                    success=False,
                    error=f"Patch validation failed: {str(e)}",
                    patch_operations=patch_operations,
                    method="dry_run"
                )

        # Apply patches
        patched_data = patch.apply(original_data)
        logger.info("✅ Patches applied successfully")

        # Validate the result if validator provided
        if validator_fn:
            logger.info("Validating patched data...")
            is_valid, errors, warnings = validator_fn(patched_data)

            if warnings:
                logger.warning(f"Validation warnings: {warnings}")

            if not is_valid:
                logger.error(f"❌ Patched data failed validation: {errors}")
                return PatchResult(
                    success=False,
                    patched_data=patched_data,
                    validation_errors=errors,
                    patch_operations=patch_operations,
                    error=f"Validation failed: {errors[0] if errors else 'Unknown error'}",
                    method="failed"
                )

            logger.info("✅ Patched data validated successfully")

        return PatchResult(
            success=True,
            patched_data=patched_data,
            patch_operations=patch_operations,
            method="patch"
        )

    except jsonpatch.JsonPatchException as e:
        logger.error(f"❌ JSON Patch error: {e}")
        return PatchResult(
            success=False,
            error=f"Invalid patch operations: {str(e)}",
            patch_operations=patch_operations,
            method="failed"
        )
    except Exception as e:
        logger.error(f"❌ Unexpected error applying patches: {e}")
        return PatchResult(
            success=False,
            error=f"Failed to apply patches: {str(e)}",
            patch_operations=patch_operations,
            method="failed"
        )


def build_patch_prompt_template(
    original_data: Dict[str, Any],
    instructions: str,
    context_sections: Optional[Dict[str, str]] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    constraints: Optional[List[str]] = None
) -> str:
    """
    Build a generic prompt for patch-based refinement.

    Args:
        original_data: The current data to be refined
        instructions: User's refinement request
        context_sections: Dict of section_name -> section_content for additional context
        examples: List of example patch operations to show the AI
        constraints: List of constraint strings to include

    Returns:
        Complete prompt string for AI refinement

    Example:
        >>> prompt = build_patch_prompt_template(
        ...     original_data=my_config,
        ...     instructions="Make it faster",
        ...     context_sections={
        ...         "Performance Data": "Current latency: 500ms...",
        ...         "User Feedback": "Too slow on large datasets"
        ...     },
        ...     examples=[
        ...         {"op": "replace", "path": "/batch_size", "value": 100}
        ...     ]
        ... )
    """
    prompt = f"""You are refining structured data using JSON Patch (RFC 6902).

# USER'S REQUEST

"{instructions}"

# CURRENT DATA

```json
{json.dumps(original_data, indent=2)}
```

"""

    # Add context sections if provided
    if context_sections:
        for section_name, section_content in context_sections.items():
            prompt += f"""
# {section_name.upper()}

{section_content}

"""

    prompt += """
# YOUR TASK

Generate **ONLY the minimal changes** needed to address the user's request using JSON Patch operations.

## JSON Patch Format (RFC 6902)

Each operation must have:
- `op`: Operation type ("replace", "add", "remove", "test", "move", "copy")
- `path`: JSON Pointer like "/field_name" or "/array/3/subfield" (0-indexed)
- `value`: New value (not needed for "remove")

## Common Operations

**Replace a field value:**
```json
{"op": "replace", "path": "/field_name", "value": "new_value"}
```

**Change nested field:**
```json
{"op": "replace", "path": "/parent/child/field", "value": 123}
```

**Change array element:**
```json
{"op": "replace", "path": "/items/2/status", "value": "active"}
```

**Add new field:**
```json
{"op": "add", "path": "/new_field", "value": "value"}
```

**Remove field:**
```json
{"op": "remove", "path": "/old_field"}
```

**Safety check before change:**
```json
{"op": "test", "path": "/status", "value": "draft"},
{"op": "replace", "path": "/status", "value": "published"}
```

"""

    # Add custom examples if provided
    if examples:
        prompt += """
## Examples Specific to This Task

"""
        for i, example in enumerate(examples, 1):
            prompt += f"""Example {i}:
```json
{json.dumps(example, indent=2)}
```

"""

    # Add constraints
    prompt += """
## RULES

1. **Minimal changes only** - Don't modify fields not mentioned in the request
2. **Verify paths exist** - Ensure array indices and nested paths are valid
3. **Use "test" for safety** - Add test operations before critical changes
4. **Be precise** - Use exact field names and paths from the current data
"""

    if constraints:
        prompt += "\n**Additional Constraints:**\n"
        for constraint in constraints:
            prompt += f"- {constraint}\n"

    return prompt


class PatchRefinementManager:
    """
    High-level manager for AI-powered patch-based refinement.

    Integrates with ai_api_client to provide a simple interface for
    refining any structured data with LLM-generated patches.

    Example:
        >>> from shared.ai_patch_utils import PatchRefinementManager
        >>> from shared.ai_api_client import ai_client
        >>>
        >>> manager = PatchRefinementManager(
        ...     original_data=my_config,
        ...     validator_fn=validate_config,
        ...     schema=config_schema,
        ...     ai_client=ai_client
        ... )
        >>>
        >>> result = await manager.refine_with_patches(
        ...     instructions="Change model to claude-opus-4-6",
        ...     context={"performance": "Current model too slow"},
        ...     fallback_to_full=True
        ... )
        >>>
        >>> if result.success:
        ...     new_config = result.updated_data
    """

    def __init__(
        self,
        original_data: Dict[str, Any],
        validator_fn: Optional[Callable[[Dict], Tuple[bool, List[str], List[str]]]] = None,
        schema: Optional[Dict[str, Any]] = None,
        ai_client: Optional[Any] = None,
        tool_name: str = "refine_with_patches",
        model: str = "claude-opus-4-1",
        patch_model: Optional[str] = None,  # Use different model for patches (e.g., gemini-flash-2.5)
        max_tokens: int = 16000
    ):
        """
        Initialize the refinement manager.

        Args:
            original_data: The data to be refined
            validator_fn: Optional validation function (is_valid, errors, warnings)
            schema: Optional base schema for the data type
            ai_client: AI client instance (from shared.ai_api_client)
            tool_name: Name for the AI tool call
            model: Model to use for full regeneration (fallback)
            patch_model: Optional cheaper/faster model for patch generation (e.g., gemini-flash-2.5)
            max_tokens: Max tokens for AI response
        """
        self.original_data = original_data
        self.validator_fn = validator_fn
        self.schema = schema
        self.ai_client = ai_client
        self.tool_name = tool_name
        self.model = model  # Expensive model for fallback
        self.patch_model = patch_model or model  # Cheap model for patches, defaults to same
        self.max_tokens = max_tokens

    async def refine_with_patches(
        self,
        instructions: str,
        context: Optional[Dict[str, str]] = None,
        examples: Optional[List[Dict]] = None,
        constraints: Optional[List[str]] = None,
        fallback_to_full: bool = True,
        fallback_fn: Optional[Callable] = None,
        debug_name: Optional[str] = None
    ) -> RefinementResult:
        """
        Refine data using AI-generated JSON Patches with optional fallback.

        Args:
            instructions: User's refinement request
            context: Additional context sections for the prompt
            examples: Example patch operations to show the AI
            constraints: Additional constraints for the AI
            fallback_to_full: If True, call fallback_fn on patch failure
            fallback_fn: Async function to call for full regeneration
            debug_name: Name for debugging/logging

        Returns:
            RefinementResult with updated data or error details
        """
        if not JSONPATCH_AVAILABLE and not fallback_to_full:
            return RefinementResult(
                success=False,
                error="jsonpatch not available and fallback disabled",
                error_type="dependency_missing",
                method="failed"
            )

        if not self.ai_client:
            return RefinementResult(
                success=False,
                error="AI client not provided",
                error_type="config_error",
                method="failed"
            )

        try:
            # Build prompt
            prompt = build_patch_prompt_template(
                original_data=self.original_data,
                instructions=instructions,
                context_sections=context,
                examples=examples,
                constraints=constraints
            )

            # Get patch schema
            patch_schema = create_patch_schema(
                base_schema=self.schema or {},
                description="Patches to refine the data",
                include_reasoning=True,
                include_questions=True
            )

            # Call AI with patch model (cheap/fast model)
            logger.info(f"Calling AI for patch-based refinement with {self.patch_model}: {debug_name or 'refinement'}")
            result = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=patch_schema,
                model=self.patch_model,  # Use cheap model for patches
                tool_name=self.tool_name,
                max_tokens=self.max_tokens,
                max_web_searches=0,
                debug_name=debug_name or "patch_refinement"
            )

            # Extract response
            response_data = self.ai_client.extract_structured_response(
                result['response'], self.tool_name
            )

            patch_operations = response_data.get('patch_operations', [])

            if not patch_operations:
                logger.warning("No patch operations returned by AI")
                if fallback_to_full and fallback_fn:
                    logger.info("Falling back to full regeneration")
                    return await fallback_fn()
                return RefinementResult(
                    success=False,
                    error="No patches generated",
                    method="failed"
                )

            # Apply patches
            logger.info(f"Applying {len(patch_operations)} patch operations...")
            patch_result = apply_patches_with_validation(
                original_data=self.original_data,
                patch_operations=patch_operations,
                validator_fn=self.validator_fn
            )

            if not patch_result.success:
                logger.error(f"Patch application failed: {patch_result.error}")
                if fallback_to_full and fallback_fn:
                    logger.info("Falling back to full regeneration")
                    return await fallback_fn()
                return RefinementResult(
                    success=False,
                    error=patch_result.error,
                    validation_errors=patch_result.validation_errors,
                    patch_operations=patch_operations,
                    method="failed"
                )

            # Extract cost/usage data
            enhanced_data = result.get('enhanced_data', {})
            token_usage = result.get('token_usage', {})
            costs_data = enhanced_data.get('costs', {})
            eliyahu_cost = costs_data.get('actual', {}).get('total_cost', 0.0)

            logger.info("✅ Patch-based refinement successful")

            return RefinementResult(
                success=True,
                updated_data=patch_result.patched_data,
                reasoning=response_data.get('reasoning', ''),
                clarifying_questions=response_data.get('clarifying_questions', ''),
                clarification_urgency=response_data.get('clarification_urgency', 0.0),
                ai_summary=response_data.get('ai_summary', ''),
                method="json_patch",
                patch_operations=patch_operations,
                eliyahu_cost=eliyahu_cost,
                token_usage=token_usage,
                enhanced_data=enhanced_data,
                processing_time=result.get('processing_time', 0.0)
            )

        except Exception as e:
            logger.error(f"Patch refinement failed: {e}")
            if fallback_to_full and fallback_fn:
                logger.info("Falling back to full regeneration due to exception")
                return await fallback_fn()
            return RefinementResult(
                success=False,
                error=str(e),
                error_type="exception",
                method="failed"
            )


def generate_patch_diff_summary(
    original_data: Dict[str, Any],
    patch_operations: List[Dict[str, Any]],
    max_operations: int = 10
) -> str:
    """
    Generate a human-readable summary of patch operations.

    Useful for logging, audit trails, or showing users what changed.

    Args:
        original_data: Original data before patches
        patch_operations: The patch operations applied
        max_operations: Maximum number of operations to summarize

    Returns:
        Formatted string describing the changes

    Example:
        >>> summary = generate_patch_diff_summary(config, patches)
        >>> print(summary)
        3 changes:
        1. Replace /validation_targets/3/importance: "ID" → "RESEARCH"
        2. Replace /qc_settings/model: ["deepseek-v3.2"] → ["claude-opus-4-6"]
        3. Add /search_groups/1/max_web_searches: 3
    """
    if not patch_operations:
        return "No changes"

    summary_lines = [f"{len(patch_operations)} change(s):"]

    for i, op in enumerate(patch_operations[:max_operations], 1):
        op_type = op.get('op', 'unknown')
        path = op.get('path', 'unknown')
        value = op.get('value')

        if op_type == "replace":
            # Try to get old value
            old_value = _get_value_at_path(original_data, path)
            old_str = json.dumps(old_value) if old_value is not None else "N/A"
            new_str = json.dumps(value)
            summary_lines.append(f"{i}. Replace {path}: {old_str} → {new_str}")
        elif op_type == "add":
            new_str = json.dumps(value)
            summary_lines.append(f"{i}. Add {path}: {new_str}")
        elif op_type == "remove":
            old_value = _get_value_at_path(original_data, path)
            old_str = json.dumps(old_value) if old_value is not None else "N/A"
            summary_lines.append(f"{i}. Remove {path}: {old_str}")
        elif op_type == "test":
            summary_lines.append(f"{i}. Test {path} == {json.dumps(value)}")
        else:
            summary_lines.append(f"{i}. {op_type.capitalize()} {path}")

    if len(patch_operations) > max_operations:
        summary_lines.append(f"... and {len(patch_operations) - max_operations} more")

    return "\n".join(summary_lines)


def _get_value_at_path(data: Dict[str, Any], path: str) -> Any:
    """Helper to get value at JSON Pointer path"""
    try:
        parts = path.strip('/').split('/')
        current = data
        for part in parts:
            if isinstance(current, list):
                current = current[int(part)]
            else:
                current = current[part]
        return current
    except (KeyError, IndexError, ValueError, TypeError):
        return None
