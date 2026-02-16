#!/usr/bin/env python3
"""
Code-based interpretation layer for simple config changes.
Attempts to parse user instructions and generate patches without using an LLM.

This is Tier 1 (FREE) - tries to handle simple cases like:
- "Change X to Y"
- "Set field to value"
- "Update model to abc"
- "Use model XYZ"
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def try_interpret_instruction(
    instruction: str,
    config: Dict,
    config_type: str = "generic"
) -> Tuple[bool, Optional[List[Dict]], str]:
    """
    Try to interpret a simple instruction and generate patches without using AI.

    Args:
        instruction: User's refinement request
        config: Current configuration
        config_type: Type of config ("config", "settings", etc.) for specialized parsing

    Returns:
        Tuple of (success, patch_operations, reasoning)
        - success: True if we could interpret the instruction
        - patch_operations: List of JSON Patch operations if successful
        - reasoning: Explanation of what we're doing

    Example:
        >>> success, patches, reasoning = try_interpret_instruction(
        ...     "change company name to research",
        ...     my_config,
        ...     "config"
        ... )
        >>> if success:
        ...     apply_patches(patches)
    """
    logger.info(f"🔍 Attempting code-based interpretation: '{instruction[:50]}...'")

    # Normalize instruction
    instruction_lower = instruction.lower().strip()

    # Try specialized parsers based on config type
    if config_type == "config":
        return _try_parse_validation_config_instruction(instruction_lower, config)
    else:
        return _try_parse_generic_instruction(instruction_lower, config)


def _try_parse_validation_config_instruction(
    instruction: str,
    config: Dict
) -> Tuple[bool, Optional[List[Dict]], str]:
    """Parse instructions specific to validation configs"""

    patches = []
    reasoning_parts = []

    # Pattern 1: "change/set/make [column] [to/as] [importance]"
    # Example: "change company name to research"
    importance_pattern = r'(?:change|set|make|update)\s+(.+?)\s+(?:to|as|importance)\s+(id|research|critical|ignored)'
    match = re.search(importance_pattern, instruction, re.IGNORECASE)

    if match:
        column_ref = match.group(1).strip()
        new_importance = match.group(2).upper()

        logger.info(f"📝 Parsed: Change '{column_ref}' importance to {new_importance}")

        # Find the column in validation_targets
        target_index = _find_validation_target(config, column_ref)

        if target_index is not None:
            column_name = config['validation_targets'][target_index]['column']
            old_importance = config['validation_targets'][target_index].get('importance', 'unknown')

            patches.append({
                'op': 'test',
                'path': f'/validation_targets/{target_index}/column',
                'value': column_name
            })
            patches.append({
                'op': 'replace',
                'path': f'/validation_targets/{target_index}/importance',
                'value': new_importance
            })

            reasoning_parts.append(
                f"Changed '{column_name}' importance from {old_importance} to {new_importance}"
            )
        else:
            logger.warning(f"❌ Could not find column matching '{column_ref}'")
            return (False, None, f"Could not find column '{column_ref}'")

    # Pattern 2: "use/set [model] [for qc/default]"
    # Example: "use claude-opus-4-6 for qc"
    model_pattern = r'(?:use|set|change to)\s+([a-z0-9\-\.]+)\s+(?:for\s+)?(qc|default|model)?'
    match = re.search(model_pattern, instruction, re.IGNORECASE)

    if match and not patches:  # Only if we haven't found importance change
        model_name = match.group(1)
        context = match.group(2).lower() if match.group(2) else 'default'

        logger.info(f"📝 Parsed: Set {context} model to {model_name}")

        if context in ['qc', 'quality']:
            # Update QC model
            if 'qc_settings' in config and 'model' in config['qc_settings']:
                old_model = config['qc_settings']['model']
                # QC model can be string or array
                if isinstance(old_model, list):
                    new_model = [model_name] + old_model[1:] if len(old_model) > 1 else [model_name]
                else:
                    new_model = model_name

                patches.append({
                    'op': 'replace',
                    'path': '/qc_settings/model',
                    'value': new_model if isinstance(old_model, list) else new_model
                })

                reasoning_parts.append(f"Changed QC model to {model_name}")
        else:
            # Update default model
            if 'default_model' in config:
                old_model = config.get('default_model', 'unknown')
                patches.append({
                    'op': 'replace',
                    'path': '/default_model',
                    'value': model_name
                })
                reasoning_parts.append(f"Changed default model from {old_model} to {model_name}")

    # Pattern 3: "set/change [search group] model to [model]"
    # Example: "set search group 1 model to claude"
    sg_model_pattern = r'(?:set|change)\s+search\s*group\s+(\d+)\s+model\s+to\s+([a-z0-9\-\.]+)'
    match = re.search(sg_model_pattern, instruction, re.IGNORECASE)

    if match and not patches:
        group_id = int(match.group(1))
        model_name = match.group(2)

        logger.info(f"📝 Parsed: Set search group {group_id} model to {model_name}")

        # Find search group index
        sg_index = _find_search_group(config, group_id)

        if sg_index is not None:
            group_name = config['search_groups'][sg_index].get('group_name', f'Group {group_id}')
            old_model = config['search_groups'][sg_index].get('model', 'default')

            patches.append({
                'op': 'replace',
                'path': f'/search_groups/{sg_index}/model',
                'value': model_name
            })

            reasoning_parts.append(
                f"Changed search group {group_id} ('{group_name}') model from {old_model} to {model_name}"
            )

    # If we generated any patches, return success
    if patches:
        reasoning = "Code-based interpretation: " + "; ".join(reasoning_parts)
        logger.info(f"✅ Successfully generated {len(patches)} patches via code interpretation")
        return (True, patches, reasoning)

    # Could not interpret
    logger.info(f"❌ Could not interpret instruction via code-based approach")
    return (False, None, "Could not interpret instruction with code-based approach")


def _try_parse_generic_instruction(
    instruction: str,
    config: Dict
) -> Tuple[bool, Optional[List[Dict]], str]:
    """Parse generic instructions for any config type"""

    # Pattern: "set [field] to [value]"
    set_pattern = r'set\s+([a-z_]+)\s+to\s+([a-z0-9\-\.]+)'
    match = re.search(set_pattern, instruction, re.IGNORECASE)

    if match:
        field = match.group(1)
        value = match.group(2)

        # Check if field exists in top-level config
        if field in config:
            old_value = config[field]
            patches = [{
                'op': 'replace',
                'path': f'/{field}',
                'value': value
            }]
            reasoning = f"Code-based interpretation: Changed {field} from {old_value} to {value}"
            logger.info(f"✅ Generated patch for generic field change")
            return (True, patches, reasoning)

    return (False, None, "Could not interpret instruction")


def _find_validation_target(config: Dict, column_ref: str) -> Optional[int]:
    """
    Find validation target index by column name (fuzzy match).

    Args:
        config: The config dict
        column_ref: Column name or part of name to search for

    Returns:
        Index in validation_targets array, or None if not found
    """
    if 'validation_targets' not in config:
        return None

    column_ref_lower = column_ref.lower()

    # Try exact match first
    for i, target in enumerate(config['validation_targets']):
        column = target.get('column', '').lower()
        if column == column_ref_lower:
            return i

    # Try fuzzy match (contains)
    for i, target in enumerate(config['validation_targets']):
        column = target.get('column', '').lower()
        if column_ref_lower in column or column in column_ref_lower:
            # If there are multiple matches, this might be ambiguous
            # For now, return first match
            logger.debug(f"Fuzzy matched '{column_ref}' to '{target.get('column')}'")
            return i

    return None


def _find_search_group(config: Dict, group_id: int) -> Optional[int]:
    """
    Find search group array index by group_id.

    Args:
        config: The config dict
        group_id: The group_id to find

    Returns:
        Index in search_groups array, or None if not found
    """
    if 'search_groups' not in config:
        return None

    for i, group in enumerate(config['search_groups']):
        if group.get('group_id') == group_id:
            return i

    return None


def can_interpret_instruction(instruction: str, config_type: str = "generic") -> bool:
    """
    Quick check if an instruction is likely interpretable without running full interpretation.

    Args:
        instruction: User's instruction
        config_type: Type of config

    Returns:
        True if the instruction looks interpretable

    Example:
        >>> if can_interpret_instruction("change company to research"):
        ...     # Try code-based interpretation
        ...     success, patches, _ = try_interpret_instruction(...)
    """
    instruction_lower = instruction.lower()

    # Simple patterns that are likely to work
    simple_patterns = [
        r'(?:change|set|make)\s+\w+\s+to\s+\w+',  # change X to Y
        r'use\s+\w+',  # use XYZ
        r'set\s+\w+\s+to\s+\w+',  # set field to value
    ]

    for pattern in simple_patterns:
        if re.search(pattern, instruction_lower):
            return True

    return False
