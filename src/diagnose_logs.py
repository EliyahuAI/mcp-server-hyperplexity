import json
import boto3
import logging
import sys
import os
import time
import re

# Configure root logger to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("diagnose_logs")

def check_prompt_format(prompt):
    """
    Check if a prompt has the expected format and sections.
    
    Args:
        prompt: The prompt string to check
        
    Returns:
        dict: A dictionary with diagnostic results
    """
    result = {
        "has_sections": False,
        "sections_found": [],
        "sections_missing": [],
        "has_general_notes": False,
        "general_notes_content": None,
        "general_notes_section_header_found": False,
        "response_format_found": False,
        "json_example_found": False,
        "is_well_formatted": False
    }
    
    # Check if the prompt has section headers
    section_pattern = r"===\s*([A-Z\s]+)\s*==="
    sections_raw = re.findall(section_pattern, prompt)
    
    # Normalize section names by stripping whitespace
    sections = [s.strip() for s in sections_raw]
    result["has_sections"] = len(sections) > 0
    result["sections_found"] = sections
    
    # Determine if this is a multiplex prompt
    is_multiplex = "MULTIPLE FIELDS VALIDATION" in sections
    
    # Expected sections based on type
    if is_multiplex:
        expected_sections = [
            "MULTIPLE FIELDS VALIDATION", 
            "CONTEXT INFORMATION", 
            "GENERAL VALIDATION GUIDELINES", 
            "FIELDS TO VALIDATE",
            "RESPONSE FORMAT"
        ]
    else:
        expected_sections = [
            "FIELD TO VALIDATE", 
            "CONTEXT INFORMATION", 
            "GENERAL VALIDATION GUIDELINES", 
            "RESPONSE FORMAT"
        ]
    
    # Check for missing sections - use a set of normalized section names
    sections_set = set(sections)
    result["sections_missing"] = [s for s in expected_sections if s not in sections_set]
    
    # Check if general notes section exists
    result["general_notes_section_header_found"] = "GENERAL VALIDATION GUIDELINES" in sections_set
    
    # Check if general_notes content exists
    general_notes_pattern = r"===\s*GENERAL VALIDATION GUIDELINES\s*===\s*\n(.*?)(?:\n===|$)"
    general_notes_match = re.search(general_notes_pattern, prompt, re.DOTALL)
    if general_notes_match:
        result["has_general_notes"] = len(general_notes_match.group(1).strip()) > 0
        # Get up to 100 chars of the general notes content
        result["general_notes_content"] = general_notes_match.group(1).strip()[:100] + "..." if len(general_notes_match.group(1).strip()) > 100 else general_notes_match.group(1).strip()
    
    # Check for response format
    result["response_format_found"] = "RESPONSE FORMAT" in sections_set
    
    # Check for JSON example in the prompt
    if is_multiplex:
        # For multiplex, look for JSON array with objects
        json_pattern = r'\[\s*\{\s*"column":'
    else:
        # For single field, look for JSON object
        json_pattern = r'\{\s*"answer":'
    
    result["json_example_found"] = bool(re.search(json_pattern, prompt, re.DOTALL))
    
    # Overall assessment
    result["is_well_formatted"] = (
        result["has_sections"] and
        len(result["sections_missing"]) == 0 and
        result["has_general_notes"] and
        result["response_format_found"] and
        result["json_example_found"]
    )
    
    return result

def lambda_handler(event, context):
    """Explicit permissions testing for CloudWatch Logs and prompt diagnostics"""
    
    # Print diagnostics
    print("PRINT: Testing CloudWatch Logs permissions")
    logger.error("ERROR: Testing CloudWatch Logs permissions")
    
    # Log environment info
    logger.error(f"Python version: {sys.version}")
    logger.error(f"Environment variables: {os.environ}")
    
    # Get IAM information
    try:
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        logger.error(f"AWS Identity: {identity}")
    except Exception as e:
        logger.error(f"Failed to get identity: {e}")
    
    # Check if a prompt was provided for diagnosis
    prompt_to_check = event.get("prompt", "")
    if prompt_to_check:
        logger.error("Performing prompt format diagnosis")
        prompt_check_result = check_prompt_format(prompt_to_check)
        logger.error(f"Prompt diagnosis result: {json.dumps(prompt_check_result, indent=2)}")
        
        # Return the diagnosis result
        return {
            'statusCode': 200,
            'body': {
                'message': 'CloudWatch Logs permission test and prompt diagnosis completed',
                'prompt_diagnosis': prompt_check_result
            }
        }
    
    # Test CloudWatch Logs permissions
    logs_client = boto3.client('logs')
    
    try:
        # Try to list log groups
        logger.error("Testing describe_log_groups...")
        response = logs_client.describe_log_groups(limit=5)
        logger.error(f"Found {len(response.get('logGroups', []))} log groups")
        
        # Create a test log group
        test_group_name = f"/aws/lambda/permissions-test-{int(time.time())}"
        logger.error(f"Creating test log group: {test_group_name}")
        logs_client.create_log_group(logGroupName=test_group_name)
        
        # Create a test log stream
        test_stream_name = f"stream-{int(time.time())}"
        logger.error(f"Creating test log stream: {test_stream_name}")
        logs_client.create_log_stream(
            logGroupName=test_group_name,
            logStreamName=test_stream_name
        )
        
        # Put log events
        logger.error("Putting test log events...")
        logs_client.put_log_events(
            logGroupName=test_group_name,
            logStreamName=test_stream_name,
            logEvents=[
                {
                    'timestamp': int(time.time() * 1000),
                    'message': 'Test log event 1'
                },
                {
                    'timestamp': int(time.time() * 1000) + 1,
                    'message': 'Test log event 2'
                }
            ]
        )
        
        # Clean up
        logger.error("Cleaning up test resources...")
        logs_client.delete_log_group(logGroupName=test_group_name)
        logger.error("Test completed successfully")
        
    except Exception as e:
        logger.error(f"Error testing CloudWatch Logs: {e}")
    
    return {
        'statusCode': 200,
        'body': json.dumps('CloudWatch Logs permission test completed')
    } 