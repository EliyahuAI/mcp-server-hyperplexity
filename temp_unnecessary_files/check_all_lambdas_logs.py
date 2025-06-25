import boto3
import json
from datetime import datetime, timedelta

# Initialize CloudWatch client
logs_client = boto3.client('logs', region_name='us-east-1')

def check_lambda_logs(log_group_name, function_name, minutes_back=20):
    """Check CloudWatch logs for a specific lambda"""
    
    print(f"\n{'='*80}")
    print(f"Checking logs for: {function_name}")
    print(f"Log group: {log_group_name}")
    print("="*80)
    
    # Calculate time range
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=minutes_back)
    
    print(f"Time range: {start_time.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')} UTC")
    
    try:
        # Use filter_log_events to search across all streams
        response = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            limit=100  # Get more events
        )
        
        events = response.get('events', [])
        print(f"\nFound {len(events)} total events")
        
        if not events:
            print("No events found in this time range")
            return
            
        # Group events by request ID
        requests = {}
        
        for event in events:
            message = event['message'].strip()
            timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
            
            # Extract request ID if present
            request_id = None
            if 'RequestId:' in message:
                parts = message.split('RequestId:')
                if len(parts) > 1:
                    request_id = parts[1].split()[0]
            
            # Skip certain messages
            if 'INIT_START' in message or 'Found credentials' in message:
                continue
                
            # Group by request or show directly
            if request_id:
                if request_id not in requests:
                    requests[request_id] = []
                requests[request_id].append((timestamp, message))
            else:
                # Show non-request messages (like initialization)
                if any(keyword in message.lower() for keyword in ['email', 'error', 'warning']):
                    print(f"\n[{timestamp.strftime('%H:%M:%S.%f')[:-3]}] {message}")
        
        # Show requests with interesting content
        print(f"\nFound {len(requests)} unique requests")
        
        for request_id, messages in requests.items():
            # Check if this request has interesting content
            has_interesting = False
            for ts, msg in messages:
                if any(keyword in msg.lower() for keyword in [
                    'email', 'background', 'session', 'bb43b6d5', '4d6b51b9',
                    'multipart', 'files', 'form', 'processing_started'
                ]):
                    has_interesting = True
                    break
            
            if has_interesting:
                print(f"\n{'─'*60}")
                print(f"Request ID: {request_id}")
                print("─"*60)
                
                for ts, msg in messages:
                    # Skip verbose messages
                    if any(skip in msg for skip in ['START RequestId', 'END RequestId', 'REPORT RequestId']):
                        continue
                        
                    print(f"[{ts.strftime('%H:%M:%S.%f')[:-3]}] {msg[:300]}")
                    
                    # Highlight important messages
                    if 'email' in msg.lower():
                        print("  ⚠️  EMAIL REFERENCE FOUND!")
                    if 'background' in msg.lower():
                        print("  🔄 BACKGROUND PROCESSING!")
                    if 'error' in msg.lower():
                        print("  ❌ ERROR FOUND!")
                        
    except Exception as e:
        print(f"Error checking logs: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Comprehensive Lambda Log Check")
    
    # Check interface lambda
    check_lambda_logs(
        '/aws/lambda/perplexity-validator-interface',
        'perplexity-validator-interface',
        minutes_back=15
    )
    
    # Check validator lambda
    check_lambda_logs(
        '/aws/lambda/perplexity-validator',
        'perplexity-validator',
        minutes_back=15
    ) 