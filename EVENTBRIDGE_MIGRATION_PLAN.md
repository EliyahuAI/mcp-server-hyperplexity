# EventBridge Migration Plan

## Current State
- Using SQS FIFO queues for preview processing
- Preview requests jam when processor fails due to FIFO ordering constraints
- SQS processor lambda (`perplexity-validator-sqs-processor`) is deprecated but queues still exist
- Interface lambda still sends to SQS preview queue

## Migration Overview
Replace SQS-based preview processing with EventBridge for better reliability and priority handling.

## Phase 1: EventBridge Infrastructure Setup

### 1.1 Create EventBridge Resources
- **Custom Event Bus**: `perplexity-validator-events`
- **Event Rules**:
  - `preview-high-priority`: Route high-priority preview events
  - `preview-standard`: Route standard preview events
  - `validation-events`: Route validation completion events

### 1.2 Update deployment/create_interface_package.py
```python
# Add EventBridge configuration to LAMBDA_CONFIG
LAMBDA_CONFIG["Environment"]["Variables"].update({
    "EVENTBRIDGE_BUS_NAME": "perplexity-validator-events",
    "EVENTBRIDGE_ENABLED": "true"
})

# Add EventBridge setup function
def setup_eventbridge_infrastructure(region="us-east-1"):
    """Create EventBridge custom bus and rules for preview processing."""
    events_client = boto3.client('events', region_name=region)
    
    # Create custom event bus
    bus_name = "perplexity-validator-events"
    try:
        events_client.create_event_bus(Name=bus_name)
        logger.info(f"Created EventBridge bus: {bus_name}")
    except events_client.exceptions.ResourceAlreadyExistsException:
        logger.info(f"EventBridge bus already exists: {bus_name}")
    
    # Create rules and targets
    setup_preview_rules(events_client, bus_name, region)

def setup_preview_rules(events_client, bus_name, region):
    """Create EventBridge rules for preview processing."""
    account_id = boto3.client('sts').get_caller_identity()['Account']
    
    # High priority rule
    events_client.put_rule(
        Name='preview-high-priority',
        EventPattern=json.dumps({
            "source": ["perplexity.validator"],
            "detail-type": ["Preview Request"],
            "detail": {"priority": ["high"]}
        }),
        State='ENABLED',
        EventBusName=bus_name
    )
    
    # Standard priority rule  
    events_client.put_rule(
        Name='preview-standard',
        EventPattern=json.dumps({
            "source": ["perplexity.validator"],
            "detail-type": ["Preview Request"],
            "detail": {"priority": ["standard"]}
        }),
        State='ENABLED',
        EventBusName=bus_name
    )
    
    # Add lambda targets to rules
    lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:perplexity-validator-interface"
    
    for rule_name in ['preview-high-priority', 'preview-standard']:
        events_client.put_targets(
            Rule=rule_name,
            EventBusName=bus_name,
            Targets=[{
                'Id': '1',
                'Arn': lambda_arn,
                'InputTransformer': {
                    'InputPathsMap': {
                        'detail': '$.detail'
                    },
                    'InputTemplate': '{"eventbridge_event": <detail>}'
                }
            }]
        )
```

### 1.3 Update IAM Permissions
```python
# Add to deployment script IAM policy updates
eventbridge_policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "events:PutEvents",
            "events:ListRules",
            "events:DescribeRule"
        ],
        "Resource": [
            f"arn:aws:events:{region}:{account_id}:event-bus/perplexity-validator-events",
            f"arn:aws:events:{region}:{account_id}:rule/perplexity-validator-events/*"
        ]
    }]
}
```

## Phase 2: Interface Lambda Updates

### 2.1 Add EventBridge Client Code
Create `src/shared/eventbridge_client.py`:
```python
import boto3
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class EventBridgeClient:
    def __init__(self, bus_name: str = "perplexity-validator-events"):
        self.events_client = boto3.client('events')
        self.bus_name = bus_name
    
    def send_preview_request(self, session_id: str, email: str, 
                           config_data: Dict, priority: str = "standard") -> bool:
        """Send preview request event to EventBridge."""
        try:
            event = {
                'Source': 'perplexity.validator',
                'DetailType': 'Preview Request',
                'Detail': json.dumps({
                    'session_id': session_id,
                    'email': email,
                    'config_data': config_data,
                    'priority': priority,
                    'timestamp': datetime.utcnow().isoformat(),
                    'event_type': 'preview_request'
                }),
                'EventBusName': self.bus_name
            }
            
            response = self.events_client.put_events(Entries=[event])
            
            if response['FailedEntryCount'] == 0:
                logger.info(f"Preview event sent successfully for session {session_id}")
                return True
            else:
                logger.error(f"Failed to send preview event: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending preview event: {e}")
            return False
```

### 2.2 Update Interface Lambda Handler
Modify `src/interface_lambda_function.py`:
```python
# Add import
from shared.eventbridge_client import EventBridgeClient

# Update preview handling logic
def handle_preview_request(event_data):
    """Handle preview requests via EventBridge instead of SQS."""
    eventbridge_enabled = os.environ.get('EVENTBRIDGE_ENABLED', 'false').lower() == 'true'
    
    if eventbridge_enabled:
        # Use EventBridge
        eb_client = EventBridgeClient()
        priority = "high" if event_data.get('urgent', False) else "standard"
        
        success = eb_client.send_preview_request(
            session_id=event_data['session_id'],
            email=event_data['email'], 
            config_data=event_data['config'],
            priority=priority
        )
        
        if success:
            return {"status": "preview_queued", "method": "eventbridge"}
        else:
            # Fallback to SQS if EventBridge fails
            logger.warning("EventBridge failed, falling back to SQS")
            return handle_sqs_preview(event_data)
    else:
        # Use existing SQS logic
        return handle_sqs_preview(event_data)

# Add EventBridge event handler
def handle_eventbridge_preview(event):
    """Process preview request from EventBridge."""
    try:
        detail = event.get('eventbridge_event', {})
        session_id = detail['session_id']
        email = detail['email']
        config_data = detail['config_data']
        
        logger.info(f"Processing EventBridge preview for session {session_id}")
        
        # Process the preview using existing logic
        result = process_preview_request(session_id, email, config_data)
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Error processing EventBridge preview: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
```

## Phase 3: Testing & Validation

### 3.1 Update Deployment Script Tests
```python
def test_eventbridge_integration(region):
    """Test EventBridge preview processing."""
    logger.info("Testing EventBridge integration...")
    
    # Send test event
    events_client = boto3.client('events', region_name=region)
    test_event = {
        'Source': 'perplexity.validator',
        'DetailType': 'Preview Request', 
        'Detail': json.dumps({
            'session_id': f'test_{int(time.time())}',
            'email': 'test@example.com',
            'config_data': {'test': True},
            'priority': 'standard'
        }),
        'EventBusName': 'perplexity-validator-events'
    }
    
    response = events_client.put_events(Entries=[test_event])
    
    if response['FailedEntryCount'] == 0:
        logger.info("✅ EventBridge test event sent successfully")
        return True
    else:
        logger.error(f"❌ EventBridge test failed: {response}")
        return False
```

### 3.2 Add to main() deployment function
```python
# Add to main() function in deployment script
if args.deploy:
    # ... existing deployment code ...
    
    # Setup EventBridge infrastructure
    logger.info("Setting up EventBridge infrastructure...")
    setup_eventbridge_infrastructure(args.region)
    
    # Test EventBridge integration
    if args.test_api:
        test_eventbridge_integration(args.region)
```

## Phase 4: SQS Cleanup

### 4.1 Remove SQS Infrastructure
- Delete unused `perplexity-validator-sqs-processor` lambda
- Remove SQS event source mappings
- Delete preview queues (after confirming EventBridge works)

### 4.2 Cleanup Commands
```bash
# Remove SQS processor lambda
aws lambda delete-function --function-name perplexity-validator-sqs-processor

# Delete SQS queues
aws sqs delete-queue --queue-url https://queue.amazonaws.com/400232868802/perplexity-validator-preview-queue.fifo
aws sqs delete-queue --queue-url https://queue.amazonaws.com/400232868802/perplexity-validator-preview-dlq.fifo
```

### 4.3 Remove SQS Environment Variables
```python
# Remove from LAMBDA_CONFIG in deployment script
# Remove: PREVIEW_QUEUE_URL, STANDARD_QUEUE_URL
```

## Phase 5: Priority Implementation

### 5.1 Priority Logic
```python
def determine_priority(user_email: str, config_data: Dict) -> str:
    """Determine event priority based on user and request characteristics."""
    
    # Premium users get high priority
    if is_premium_user(user_email):
        return "high"
    
    # Large requests get standard priority
    if config_data.get('row_count', 0) > 1000:
        return "standard"
    
    # Default to standard
    return "standard"
```

### 5.2 Different Processing Rules
- **High Priority**: Process immediately, higher lambda concurrency
- **Standard Priority**: Normal processing, batching allowed

## Deployment Steps

1. **Run deployment with EventBridge setup**:
   ```bash
   python deployment/create_interface_package.py --deploy --force-rebuild
   ```

2. **Test EventBridge functionality**:
   ```bash
   python deployment/create_interface_package.py --test-api
   ```

3. **Monitor for 24 hours** to ensure stability

4. **Remove SQS infrastructure** after confirming EventBridge works

## Rollback Plan

If EventBridge migration fails:
1. Set `EVENTBRIDGE_ENABLED=false` in lambda environment
2. Re-enable SQS processor lambda
3. Interface will automatically fall back to SQS processing

## Benefits After Migration

- **No jamming**: Events are independent, failures don't block others
- **Priority handling**: High-priority events processed faster
- **Better observability**: EventBridge provides detailed metrics
- **Easier scaling**: Can add new event types and processors easily
- **Cost optimization**: Pay per event vs. continuous SQS polling