import boto3
import json
from datetime import datetime, timedelta

# Initialize CloudWatch client
logs_client = boto3.client('logs', region_name='us-east-1')

# Lambda function log group
log_group = '/aws/lambda/perplexity-validator-interface'

def check_recent_logs(minutes_back=10):
    """Check CloudWatch logs for recent executions"""
    
    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes_back)
    
    print(f"Checking logs from {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("="*80)
    
    try:
        # Get log streams
        response = logs_client.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not response['logStreams']:
            print("No log streams found")
            return
            
        # Check each recent log stream
        for stream in response['logStreams']:
            stream_name = stream['logStreamName']
            print(f"\nLog Stream: {stream_name}")
            print("-"*40)
            
            # Get log events
            events_response = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=100
            )
            
            # Display all events (with some filtering)
            print(f"Found {len(events_response['events'])} events")
            
            for event in events_response['events']:
                message = event['message'].strip()
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                
                # Skip only the most verbose messages
                if any(skip in message for skip in ['INIT_START', 'Found credentials']):
                    continue
                
                # Show all other messages
                print(f"[{timestamp.strftime('%H:%M:%S.%f')[:-3]}] {message[:200]}...")
                
                # Look for specific keywords and highlight them
                if any(keyword in message.lower() for keyword in [
                    'email', 'background', 'session_id', 'error', 'failed'
                ]):
                    print(f"  ⚠️  IMPORTANT: Contains keyword!")
                    
                    # Try to parse JSON messages for more detail
                    if message.startswith('{') or 'Received event:' in message:
                        try:
                            if 'Received event:' in message:
                                json_start = message.find('{')
                                if json_start > -1:
                                    json_str = message[json_start:]
                                    data = json.loads(json_str)
                                    if 'email' in str(data).lower():
                                        print(f"  → Found email reference: {json.dumps(data, indent=2)}")
                        except:
                            pass
                            
    except Exception as e:
        print(f"Error checking logs: {e}")

if __name__ == "__main__":
    print("Checking CloudWatch logs for email functionality...")
    check_recent_logs(10)  # Check last 10 minutes 