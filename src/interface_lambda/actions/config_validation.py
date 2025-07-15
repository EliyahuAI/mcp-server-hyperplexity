"""
Handles the validateConfig action.
"""
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def validate_config_structure(config_data):
    """
    Validates config data structure using built-in Python validation.
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

def handle(request_data, context):
    """
    Handles the validateConfig action.
    """
    from ..utils.helpers import create_response
    config_content = request_data.get('config', '')
    if not config_content:
        return create_response(400, {'error': 'Missing config content', 'valid': False})
    
    try:
        if isinstance(config_content, str):
            config_data = json.loads(config_content)
        else:
            config_data = config_content
        
        # Validate structure
        is_valid, errors, warnings = validate_config_structure(config_data)
        
        response = {
            'valid': is_valid,
            'errors': errors,
            'warnings': warnings
        }
        
        if is_valid:
            response['message'] = 'Configuration is valid'
            if warnings:
                response['message'] += f' (with {len(warnings)} warnings)'
        else:
            response['message'] = f'Configuration has {len(errors)} errors'
        
        return create_response(200, response)
        
    except json.JSONDecodeError as e:
        return create_response(200, {'valid': False, 'errors': [f'Invalid JSON: {str(e)}'], 'warnings': []}) 