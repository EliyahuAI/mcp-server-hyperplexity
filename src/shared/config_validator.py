"""
Consolidated configuration validation module.
Provides validation for both structural correctness and table-config matching.
"""
import json
import logging
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)

def validate_config_structure(config_data: Dict) -> Tuple[bool, List[str], List[str]]:
    """
    Validates config data structure using the column_config_schema.json.
    Returns tuple (is_valid, errors, warnings)
    """
    errors = []
    warnings = []
    
    # Check if config_data is a dict
    if not isinstance(config_data, dict):
        errors.append("Configuration must be a JSON object")
        return False, errors, warnings
    
    # Required root field
    if 'validation_targets' not in config_data:
        errors.append("Missing required field: validation_targets")
    
    # Validate optional root fields
    if 'default_model' in config_data and not isinstance(config_data['default_model'], str):
        errors.append("default_model must be a string")
    
    if 'default_search_context_size' in config_data:
        if config_data['default_search_context_size'] not in ['low', 'high']:
            errors.append("default_search_context_size must be 'low' or 'high'")
    
    # Validate search_groups if present
    if 'search_groups' in config_data:
        if not isinstance(config_data['search_groups'], list):
            errors.append("search_groups must be an array")
        else:
            group_ids = set()
            for i, group in enumerate(config_data['search_groups']):
                if not isinstance(group, dict):
                    errors.append(f"search_groups[{i}] must be an object")
                    continue
                
                # Required fields in search group
                required_group_fields = ['group_id', 'group_name', 'description', 'model', 'search_context']
                for field in required_group_fields:
                    if field not in group:
                        errors.append(f"search_groups[{i}] missing required field: {field}")
                
                # Validate group_id
                if 'group_id' in group:
                    if not isinstance(group['group_id'], int) or group['group_id'] < 0:
                        errors.append(f"search_groups[{i}].group_id must be a non-negative integer")
                    elif group['group_id'] in group_ids:
                        errors.append(f"Duplicate group_id: {group['group_id']}")
                    else:
                        group_ids.add(group['group_id'])
                
                # Validate search_context
                if 'search_context' in group and group['search_context'] not in ['low', 'high']:
                    errors.append(f"search_groups[{i}].search_context must be 'low' or 'high'")
                
                # Validate string fields
                for field in ['group_name', 'description', 'model']:
                    if field in group and (not isinstance(group[field], str) or not group[field].strip()):
                        errors.append(f"search_groups[{i}].{field} must be a non-empty string")
    
    # Validate validation_targets
    if 'validation_targets' in config_data:
        if not isinstance(config_data['validation_targets'], list):
            errors.append("validation_targets must be an array")
        elif len(config_data['validation_targets']) == 0:
            errors.append("validation_targets must contain at least one item")
        else:
            used_group_ids = set()
            defined_group_ids = set()
            
            # Get defined group IDs
            if 'search_groups' in config_data and isinstance(config_data['search_groups'], list):
                defined_group_ids = {g.get('group_id') for g in config_data['search_groups'] 
                                   if isinstance(g, dict) and 'group_id' in g}
            
            columns = set()
            for i, target in enumerate(config_data['validation_targets']):
                if not isinstance(target, dict):
                    errors.append(f"validation_targets[{i}] must be an object")
                    continue
                
                # Required fields in validation target
                required_target_fields = ['column', 'description', 'importance', 'format', 'examples', 'search_group']
                for field in required_target_fields:
                    if field not in target:
                        errors.append(f"validation_targets[{i}] missing required field: {field}")
                
                # Validate column uniqueness and format
                if 'column' in target:
                    if not isinstance(target['column'], str) or not target['column'].strip():
                        errors.append(f"validation_targets[{i}].column must be a non-empty string")
                    elif target['column'] in columns:
                        errors.append(f"Duplicate column name: {target['column']}")
                    else:
                        columns.add(target['column'])
                
                # Validate string fields
                for field in ['description', 'format']:
                    if field in target and (not isinstance(target[field], str) or not target[field].strip()):
                        errors.append(f"validation_targets[{i}].{field} must be a non-empty string")
                
                # Validate importance levels
                if 'importance' in target:
                    valid_importance = ['ID', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'IGNORED']
                    if target['importance'] not in valid_importance:
                        errors.append(f"validation_targets[{i}].importance must be one of: {', '.join(valid_importance)}")
                
                # Validate examples
                if 'examples' in target:
                    if not isinstance(target['examples'], list):
                        errors.append(f"validation_targets[{i}].examples must be an array")
                    elif len(target['examples']) == 0:
                        errors.append(f"validation_targets[{i}].examples must contain at least one item")
                    else:
                        for j, example in enumerate(target['examples']):
                            if not isinstance(example, str):
                                errors.append(f"validation_targets[{i}].examples[{j}] must be a string")
                
                # Validate search_group
                if 'search_group' in target:
                    if not isinstance(target['search_group'], int) or target['search_group'] < 0:
                        errors.append(f"validation_targets[{i}].search_group must be a non-negative integer")
                    else:
                        used_group_ids.add(target['search_group'])
                
                # Validate optional fields
                if 'search_context_size' in target and target['search_context_size'] not in ['low', 'high']:
                    errors.append(f"validation_targets[{i}].search_context_size must be 'low' or 'high'")
                
                if 'preferred_model' in target and (not isinstance(target['preferred_model'], str) or not target['preferred_model'].strip()):
                    errors.append(f"validation_targets[{i}].preferred_model must be a non-empty string")
            
            # Check for undefined search groups
            if defined_group_ids:  # Only check if search_groups are defined
                undefined_groups = used_group_ids - defined_group_ids
                if undefined_groups:
                    for group_id in sorted(undefined_groups):
                        warnings.append(f"Search group {group_id} is used but not defined in search_groups")
    
    return len(errors) == 0, errors, warnings

def validate_config_table_match(config_data: Dict, table_analysis: Dict) -> Tuple[bool, List[str], List[str]]:
    """
    Validates that config validation targets match actual table columns.
    Returns tuple (is_valid, errors, warnings)
    
    Args:
        config_data: The configuration dictionary
        table_analysis: Table analysis containing column information
    """
    errors = []
    warnings = []
    
    # Extract table column names from table analysis
    table_columns = set()
    if 'basic_info' in table_analysis and 'column_names' in table_analysis['basic_info']:
        table_columns = set(table_analysis['basic_info']['column_names'])
    elif 'column_analysis' in table_analysis:
        table_columns = set(table_analysis['column_analysis'].keys())
    else:
        warnings.append("No column information found in table analysis - skipping table-config match validation")
        return True, errors, warnings
    
    if not table_columns:
        warnings.append("No columns found in table - skipping table-config match validation")
        return True, errors, warnings
    
    # Check validation targets against table columns
    if 'validation_targets' in config_data:
        config_columns = set()
        missing_columns = set()
        extra_columns = set()
        
        for target in config_data['validation_targets']:
            if isinstance(target, dict) and 'column' in target:
                column_name = target['column']
                config_columns.add(column_name)
                
                if column_name not in table_columns:
                    missing_columns.add(column_name)
        
        # Check for table columns not in config
        extra_columns = table_columns - config_columns
        
        # Report missing columns as errors
        if missing_columns:
            for col in sorted(missing_columns):
                errors.append(f"Config references column '{col}' which does not exist in the table")
        
        # Report extra columns as warnings
        if extra_columns:
            for col in sorted(extra_columns):
                warnings.append(f"Table column '{col}' is not included in the configuration")
    
    return len(errors) == 0, errors, warnings

def validate_config_complete(config_data: Dict, table_analysis: Optional[Dict] = None) -> Tuple[bool, List[str], List[str]]:
    """
    Complete validation combining structural validation and optional table matching.
    
    Args:
        config_data: The configuration dictionary to validate
        table_analysis: Optional table analysis for table-config matching
        
    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    all_errors = []
    all_warnings = []
    
    # 1. Structural validation
    struct_valid, struct_errors, struct_warnings = validate_config_structure(config_data)
    all_errors.extend(struct_errors)
    all_warnings.extend(struct_warnings)
    
    # 2. Table matching validation (if table analysis provided)
    if table_analysis:
        match_valid, match_errors, match_warnings = validate_config_table_match(config_data, table_analysis)
        all_errors.extend(match_errors)
        all_warnings.extend(match_warnings)
    
    return len(all_errors) == 0, all_errors, all_warnings

def load_and_validate_config(config_content: str, table_analysis: Optional[Dict] = None) -> Dict:
    """
    Convenience function to load and validate config from string content.
    
    Args:
        config_content: JSON string or dict containing configuration
        table_analysis: Optional table analysis for table-config matching
        
    Returns:
        Dictionary with validation results and parsed config
    """
    try:
        if isinstance(config_content, str):
            config_data = json.loads(config_content)
        else:
            config_data = config_content
        
        is_valid, errors, warnings = validate_config_complete(config_data, table_analysis)
        
        response = {
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'config_data': config_data
        }
        
        if is_valid:
            response['message'] = 'Configuration is valid'
            if warnings:
                response['message'] += f' (with {len(warnings)} warnings)'
        else:
            response['message'] = f'Configuration has {len(errors)} errors'
            
        return response
        
    except json.JSONDecodeError as e:
        return {
            'valid': False,
            'errors': [f'Invalid JSON: {str(e)}'],
            'warnings': [],
            'config_data': None,
            'message': 'Invalid JSON format'
        }