import boto3
import json
from datetime import datetime, timedelta

# Initialize clients
lambda_client = boto3.client('lambda', region_name='us-east-1')
logs_client = boto3.client('logs', region_name='us-east-1')

def check_lambda_config(function_name):
    """Check Lambda function configuration"""
    print(f"\n{'='*60}")
    print(f"Lambda Configuration: {function_name}")
    print("="*60)
    
    try:
        # Get function configuration
        response = lambda_client.get_function(FunctionName=function_name)
        config = response['Configuration']
        
        print(f"Function ARN: {config['FunctionArn']}")
        print(f"Runtime: {config['Runtime']}")
        print(f"Handler: {config['Handler']}")
        print(f"State: {config['State']}")
        print(f"Last Modified: {config['LastModified']}")
        print(f"Timeout: {config['Timeout']} seconds")
        print(f"Memory: {config['MemorySize']} MB")
        
        # Check environment variables
        env_vars = config.get('Environment', {}).get('Variables', {})
        print("\nEnvironment Variables:")
        for key, value in env_vars.items():
            if 'KEY' in key or 'SECRET' in key:
                print(f"  {key}: ***")
            else:
                print(f"  {key}: {value}")
        
        # Check if CloudWatch Logs are configured
        print(f"\nCloudWatch Logs:")
        print(f"  Log Group: /aws/lambda/{function_name}")
        
        # Check if log group exists
        try:
            logs_client.describe_log_groups(
                logGroupNamePrefix=f"/aws/lambda/{function_name}",
                limit=1
            )
            print("  ✓ Log group exists")
        except:
            print("  ✗ Log group NOT found!")
            
        # Get recent invocation metrics
        print("\nChecking recent invocations...")
        
        # Get function metrics
        cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=30)
        
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/Lambda',
            MetricName='Invocations',
            Dimensions=[
                {
                    'Name': 'FunctionName',
                    'Value': function_name
                }
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5 minute periods
            Statistics=['Sum']
        )
        
        print(f"\nInvocations in last 30 minutes:")
        if response['Datapoints']:
            for point in sorted(response['Datapoints'], key=lambda x: x['Timestamp']):
                print(f"  {point['Timestamp'].strftime('%H:%M')} UTC: {int(point['Sum'])} invocations")
        else:
            print("  No invocations recorded")
            
    except Exception as e:
        print(f"Error checking configuration: {e}")
        import traceback
        traceback.print_exc()

def list_recent_log_streams(function_name):
    """List all log streams for a function"""
    print(f"\n{'='*60}")
    print(f"All Log Streams for {function_name}")
    print("="*60)
    
    try:
        log_group = f"/aws/lambda/{function_name}"
        
        # Get ALL log streams
        paginator = logs_client.get_paginator('describe_log_streams')
        page_iterator = paginator.paginate(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True
        )
        
        stream_count = 0
        for page in page_iterator:
            for stream in page['logStreams']:
                stream_count += 1
                last_event = datetime.fromtimestamp(stream.get('lastEventTime', 0) / 1000)
                print(f"\nStream: {stream['logStreamName']}")
                print(f"  Last Event: {last_event.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                print(f"  Stored Bytes: {stream.get('storedBytes', 0)}")
                
                if stream_count >= 10:  # Limit output
                    break
            if stream_count >= 10:
                break
                
        print(f"\nTotal streams shown: {stream_count}")
        
    except Exception as e:
        print(f"Error listing log streams: {e}")

if __name__ == "__main__":
    print("Lambda Configuration and Logging Check")
    
    # Check interface lambda
    check_lambda_config('perplexity-validator-interface')
    list_recent_log_streams('perplexity-validator-interface')
    
    # Check validator lambda
    check_lambda_config('perplexity-validator')
    list_recent_log_streams('perplexity-validator') 