# Async Validation System Requirements

## Core Requirements

### 1. Async Continuation Chain
- **Primary Goal**: Process large datasets that exceed Lambda's 15-minute timeout
- **Batch Processing**: Process configurable batch size (default 3 rows) per lambda
- **Auto-Triggering**: When approaching timeout (~14.5 minutes), automatically trigger continuation
- **Progress Tracking**: Use S3-based output tracking (NOT counters) to determine processed rows
- **Work Validation**: Only trigger continuation if progress was made (prevent infinite loops)

### 2. Lambda Coordination
- **Single Active Lambda**: Only ONE lambda should process a session at any time
- **Atomic Locking**: Use DynamoDB conditional writes to prevent race conditions
- **Lock Handoff**: Release lock BEFORE triggering continuation to allow smooth handoff
- **Stale Detection**: Detect and takeover from lambdas that haven't updated in 5+ minutes
- **Conflict Resolution**: Return 409 status when another lambda is active

### 3. S3 Payload Management
- **Large Payloads**: Store complete validation context in S3 (exceeds SQS limits)
- **Continuation Payload**: Include all necessary context for resuming:
  - Original table data
  - Config
  - Validation results so far
  - Batch timing history
  - Continuation count
- **Output Tracking**: Store partial results in S3 for continuation to append to

### 4. SQS Message Flow
- **Message Deduplication**: Prevent duplicate processing of same continuation
- **Message Age Validation**: Reject messages older than 5 minutes
- **Async Queue**: Use dedicated async queue for continuation messages
- **Completion Queue**: Trigger interface lambda for final results

### 5. Progress Reporting
- **WebSocket Updates**: Send real-time progress to connected clients
- **DynamoDB Status**: Update run status with progress percentage
- **Chain Notifications**: Notify when continuation chains start/complete

## Critical Bug Found

**THE RETURN STATEMENT BUG**:
- When coordination conflict detected, `return {'statusCode': 409}` executes but doesn't exit function
- Execution continues past return to complete validation with 0 rows
- Appears to be a Python execution flow issue with nested try/except blocks
- Located at `lambda_function.py:3329` inside multiple nested try/except blocks

## Technical Notes

### Current Architecture Issues
1. **Coordination Return Not Working**: The 409 return at line 3329 doesn't stop execution
2. **Multiple Lambda Instances**: SQS delivers same message to multiple lambdas simultaneously
3. **Continuation Triggered Twice**: Both lambdas try to trigger continuation causing duplicates

### Proposed Solutions
1. **Replace Return with Exception**: Raise custom `CoordinationConflictException` and catch at top level
2. **Add SQS Visibility Timeout**: Increase to prevent multiple deliveries
3. **Add Message Deduplication ID**: Use session_id + continuation_count as dedup key

## Implementation Strategy

### Clean Rewrite Approach
1. Start from pre-async version (before commit a5aec73)
2. Implement async continuation in stages:
   - Stage 1: Basic continuation triggering
   - Stage 2: S3 payload management
   - Stage 3: DynamoDB coordination
   - Stage 4: Progress tracking
   - Stage 5: Error handling and safety

### Key Design Principles
1. **Fail-Safe**: Always complete what we can, trigger completion on any error
2. **Idempotent**: Same continuation can be processed multiple times safely
3. **Observable**: Extensive logging at every decision point
4. **Atomic**: Use database transactions where possible
5. **Timeout-Aware**: Always check remaining time before operations

## Testing Requirements

1. **Small Dataset**: 3 rows, batch size 1 (tests continuation)
2. **Large Dataset**: 100+ rows (tests multiple continuations)
3. **Concurrent Triggers**: Multiple lambdas starting simultaneously
4. **Stale Lambda**: Lambda dies mid-processing
5. **No Progress**: Lambda makes no progress (should error out)

## Critical Code Sections to Preserve

From current implementation:
- Enhanced batch size management
- WebSocket client integration
- QC integration
- Citation extraction
- Cost/time tracking
- S3 results saving
- Interface completion triggering