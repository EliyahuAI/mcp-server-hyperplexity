import json
import boto3
import logging
import os
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add a handler to ensure logs appear in CloudWatch
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
    logger.info("Initialized logger with StreamHandler")
else:
    logger.info("Logger already has handlers, skipping handler setup")

def lambda_handler(event, context):
    """Simple Lambda handler for testing CloudWatch logs."""
    
    # Simple log messages
    logger.info("TEST LOGGING - START")
    logger.info(f"Function name: {context.function_name}")
    logger.info(f"Request ID: {context.aws_request_id}")
    logger.info(f"Log group name: /aws/lambda/{context.function_name}")
    logger.info(f"Log stream name: {context.log_stream_name}")
    
    # Explicitly check CloudWatch permissions
    try:
        logs_client = boto3.client('logs')
        log_group_name = f"/aws/lambda/{context.function_name}"
        
        # Test if we can list log groups
        logger.info("Testing CloudWatch Logs permissions - listing log groups")
        response = logs_client.describe_log_groups(logGroupNamePrefix="/aws/lambda/")
        log_group_count = len(response.get('logGroups', []))
        logger.info(f"Found {log_group_count} Lambda log groups")
        
        # Try to create a test log stream
        try:
            test_stream_name = f"test-stream-{int(time.time())}"
            logger.info(f"Testing creating a log stream: {test_stream_name}")
            logs_client.create_log_stream(
                logGroupName=log_group_name,
                logStreamName=test_stream_name
            )
            logger.info(f"Successfully created test log stream")
            
            # Try to put a log event
            logger.info("Testing putting a log event")
            logs_client.put_log_events(
                logGroupName=log_group_name,
                logStreamName=test_stream_name,
                logEvents=[
                    {
                        'timestamp': int(time.time() * 1000),
                        'message': 'Test log event from Lambda function'
                    }
                ]
            )
            logger.info("Successfully put test log event")
        except Exception as stream_e:
            logger.error(f"Error testing log stream operations: {str(stream_e)}")
    except Exception as e:
        logger.error(f"Error testing CloudWatch Logs permissions: {str(e)}")
    
    # Log IAM role information
    try:
        iam = boto3.client('iam')
        role_name = context.invoked_function_arn.split(':')[5].split('/')[1]
        logger.info(f"Lambda execution role: {role_name}")
        
        try:
            role_info = iam.get_role(RoleName=role_name)
            logger.info(f"Role ARN: {role_info['Role']['Arn']}")
        except Exception as role_e:
            logger.error(f"Unable to get role info: {str(role_e)}")
            
    except Exception as iam_e:
        logger.error(f"Error getting IAM information: {str(iam_e)}")
    
    logger.info("TEST LOGGING - END")
    
    return {
        'statusCode': 200,
        'body': json.dumps('Logging test completed. Check CloudWatch Logs.')
    } 