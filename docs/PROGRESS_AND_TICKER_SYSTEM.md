# Progress Indicator and Ticker System

## Overview

The Progress Indicator and Ticker system provides real-time visual feedback during validation operations. The progress indicator shows validation progress with confidence-based color coding, while the ticker displays high-priority updates about critical data changes.

## Progress Indicator

### Visual Design

The progress indicator consists of:
- **Progress Track**: 120px horizontal line with left/right edges marked
- **Progress Square**: 22.5px × 22.5px animated square that moves along the track
- **Progress Text**: Status message displayed below the track
- **Ticker Row**: 2-line notification area for high-priority updates (appears between progress track and text)

### Color System

The progress square changes color based on the **average confidence score** (0-100 scale) of validation/QC results:

#### Default Color
- **Green (#2DFF45)**: Default color until confidence scores arrive

#### Confidence-Based Colors
Once confidence scores start arriving from backend:

| Confidence Score | Color | Meaning |
|-----------------|-------|---------|
| 0-50 | Red → Yellow gradient | Low to medium confidence (red at 0, yellow at 50) |
| 50-100 | Yellow → Green gradient | Medium to high confidence (yellow at 50, green at 100) |

**Calculation**:
- Backend maps confidence levels: `LOW=33`, `MEDIUM=66`, `HIGH=100`
- Calculates numeric average across all AI calls in current batch
- Sends average to frontend via WebSocket `confidence_score` field

### Animations

#### Heartbeat Pulse (Normal)
- **Animation**: `thinkingPulse` (1.2s cycle)
- **Scale**: 1.0 → 1.05 → 1.02 → 1.0
- **Box Shadow**: Subtle green glow during pulse
- **Usage**: Default animation during active processing

#### Fast Heartbeat (Stuck)
- **Animation**: `thinkingPulseFast` (0.6s cycle)
- **Scale**: 1.0 → 1.08 → 1.04 → 1.0
- **Trigger**: Automatically activates when no progress updates received for >10 seconds
- **Purpose**: Visual indicator that process is still alive but slow

#### Heartbeat Speed Up & Spin Sequence
- **Frequency**: 10% chance every 10 seconds
- **Phase 1** (2s): Heartbeat speeds up to fast pulse
- **Phase 2** (2.4s): Wrapper spins 360° twice while heartbeat continues fast
- **Phase 3**: Heartbeat calms down to normal pulse
- **Purpose**: Engaging visual feedback to show system is actively working

**Note**: During rotation, the pulse animation is paused to prevent the square from appearing to grow larger.

### Position Tracking

The progress square position represents completion percentage:
- **0%**: Far left edge of track
- **50%**: Center of track
- **100%**: Far right edge of track

Position updates are smooth with 0.3s CSS transition.

#### Critical Architecture Details

**Two-Part Structure**:
1. **Progress Square Wrapper** (`.progress-square-wrapper`): 37.5px × 37.5px black border box
   - Positioned absolutely with `top: -16.25px`, `left: -18.75px` (initial position)
   - **MUST** have `transform-origin: center center` to scale from center, not top-left corner
   - Moves along the track by updating `wrapper.style.left` property
   - Scales during grow/shrink animations

2. **Progress Square** (`.progress-square`): 22.5px × 22.5px green center
   - Positioned inside wrapper with `position: absolute; top: 50%; left: 50%`
   - **MUST** have `transform: translate(-50%, -50%)` to stay centered in wrapper
   - Never moves independently - always stays centered in wrapper
   - Pulsates with animations that preserve the centering transform

**CRITICAL**: Always move the wrapper, never the square directly:
```javascript
// CORRECT:
progressWrapper.style.left = `${position}px`;

// WRONG - causes misalignment:
progressSquare.style.left = `${position}px`;
```

**Animation Requirements**:
- Wrapper animations (grow/shrink) use simple `scale(0)` to `scale(1)`
- Square animations (pulse, complete, error) MUST include `translate(-50%, -50%)` in every keyframe
- During spin/flip animations, pulse is paused via `animation-play-state: paused`

### Backend Integration

#### Confidence Score Calculation
**File**: `src/lambdas/validation/lambda_function.py`

```python
def calculate_confidence_average(confidences: List[str]) -> int:
    """
    Calculate numeric average of confidence levels (0-100 scale).

    Args:
        confidences: List of confidence strings ('HIGH', 'MEDIUM', 'LOW')

    Returns:
        Average confidence on 0-100 scale (LOW=33, MEDIUM=66, HIGH=100)
    """
    confidence_map = {'HIGH': 100, 'MEDIUM': 66, 'LOW': 33}
    numeric_values = [confidence_map.get(c.upper(), 66) for c in confidences]
    average = sum(numeric_values) / len(numeric_values)
    return int(round(average))
```

#### Progress Updates
Backend sends progress updates via WebSocket with structure:
```python
{
    'type': 'progress_update',
    'message': 'AI call 5/20 completed',
    'progress': 25,  # 0-100 percentage
    'confidence_score': 83,  # 0-100 average confidence
    'session_id': 'session_id',
    'timestamp': '2025-01-06T12:34:56'
}
```

**Key Points**:
- Validation calls send average of validation confidence levels
- QC calls send average of `qc_confidence` levels (confidence in final QC answer)
- Progress queue batches updates to prevent WebSocket flooding
- Confidence scores are sent with every AI call completion message

### Frontend State Management

**Global State** (`globalState.currentConfidenceScore`):
- Tracks most recent confidence score (0-100)
- Reset to `null` when validation completes (returns to green)
- Updated on every progress_update WebSocket message

**Progress Tracking** (`cardCurrentProgress` Map):
- Tracks current progress percentage per card
- Ensures progress never goes backward
- Cleared when validation completes

## Ticker System

### Purpose

Display high-priority updates about critical data changes detected during validation. Shows 2-line centered messages that fade in/out, cycling through a priority queue.

### Message Format

```
Amazon - Home Products, Invest Now?: 🟢 Hold
```

**Components**:
- **Row IDs**: Identifying information from table ID fields (e.g., "Amazon - Home Products")
- **Column**: Field name being updated (e.g., "Invest Now?")
- **Confidence Emoji**: Visual indicator of confidence level (🔴 LOW, 🟡 MEDIUM, 🟢 HIGH)
- **Final Value**: The updated/QC value (e.g., "Hold")

### Character Limits (Responsive)

Messages are truncated to fit screen size:

| Component | Portrait | Landscape/Desktop |
|-----------|----------|-------------------|
| Row IDs | 20 chars | 40 chars |
| Column | 15 chars | 30 chars |
| Final Value | 15 chars | 30 chars |

**Detection**: Uses `window.matchMedia('(orientation: portrait)')` and `window.innerWidth < 768`

Truncation adds "..." when text exceeds limit.

### Priority System

Messages sorted by priority (highest first):

| Priority | Source | Trigger Condition |
|----------|--------|-------------------|
| 5 | QC | Critical importance (update_importance = 5) |
| 4 | QC | Major importance (update_importance = 4) |
| 3 | Validation | MEDIUM → HIGH confidence upgrade |
| 2 | Validation | LOW → HIGH confidence upgrade |

### Queue Management

#### Seen Tracking
- Messages track `seen: false` when added
- Marked `seen: true` when displayed
- **Sorting**: Unseen messages always appear first, then by priority, then by timestamp

#### Deduplication
- **Key**: `row_ids|column` (unique per field per row)
- **Behavior**:
  - If duplicate key exists, replace only if new message has:
    - Higher priority, OR
    - Same priority but newer timestamp
  - Preserves `seen` status when replacing

#### Persistence
- Queue persists between preview and full validation
- Allows full validation to upgrade/replace preview messages
- Maximum 10 messages in queue (keeps highest priority)

### Display Cycle

**Timing**:
- 3.5 seconds per message (3s display + 0.5s fade transition)
- Fade out → update text → fade in

**Visibility**:
- Appears automatically when first ticker message arrives
- Visible only during `PROCESSING` status (preview or full validation)
- Hidden when validation completes (queue preserved)

### Backend Integration

#### Ticker Message Structure
**File**: `src/shared/websocket_client.py`

```python
def send_ticker_update(self, session_id: str, priority: int, row_ids: str,
                      column: str, final_value: str, confidence: str,
                      explanation: str = "") -> bool:
    """Send a ticker update notification via WebSocket"""
    emoji_map = {
        'HIGH': '🟢',
        'MEDIUM': '🟡',
        'LOW': '🔴'
    }
    confidence_emoji = emoji_map.get(confidence.upper(), '🟢')

    message = {
        'type': 'ticker_update',
        'session_id': session_id,
        'priority': priority,
        'row_ids': row_ids,
        'column': column,
        'final_value': final_value,
        'confidence': confidence,
        'confidence_emoji': confidence_emoji,
        'explanation': explanation,
        'timestamp': datetime.now().isoformat()
    }

    return self.send_to_session(session_id, message)
```

#### Validation-Level Ticker Updates
**File**: `src/lambdas/validation/lambda_function.py`

Sends ticker messages for confidence upgrades:
```python
if (updated_confidence == 'HIGH' and
    original_confidence in ['LOW', 'MEDIUM']):
    priority = 2 if original_confidence == 'LOW' else 3
    websocket_client.send_ticker_update(
        session_id=session_id,
        priority=priority,
        row_ids=row_ids,
        column=field_name,
        final_value=final_value,
        confidence=updated_confidence,
        explanation=f"Validation upgraded confidence from {original_confidence}"
    )
```

#### QC-Level Ticker Updates

Sends ticker messages for high-importance QC changes (importance 4-5):
```python
if importance_level >= 4:
    websocket_client.send_ticker_update(
        session_id=session_id,
        priority=importance_level,  # 4 or 5
        row_ids=row_ids,
        column=field_name,
        final_value=qc_entry,
        confidence=qc_confidence,
        explanation=update_importance_explanation
    )
```

### Frontend State Management

**Global State**:
- `tickerMessages`: Array of ticker message objects (max 10)
- `activeCardId`: Current card displaying ticker
- `tickerInterval`: setInterval ID for cycling messages
- `currentTickerIndex`: Index of currently displayed message
- `currentValidationState`: 'preview' | 'full' | null (controls ticker visibility)

**Message Object**:
```javascript
{
    priority: 4,
    row_ids: 'Amazon - Home Products',
    column: 'Invest Now?',
    final_value: 'Hold',
    confidence_emoji: '🟢',
    timestamp: '2025-01-06T12:34:56',
    key: 'Amazon - Home Products|Invest Now?',
    seen: false
}
```

## CSS Classes and Styling

### Progress Indicator Classes

- `.progress-track`: 120px horizontal line container
- `.progress-square-wrapper`: 37.5px black border box (moves along track)
- `.progress-square`: 22.5px inner colored square (pulsates)
- `.progress-text`: Status message text below track
- `.progress-square.stuck`: Fast pulse animation when stuck
- `.progress-square-wrapper.spinning`: Rotation animation
- `.progress-square-wrapper.error`: Red error state

### Ticker Classes

- `.ticker-row`: Container for ticker messages
- `.ticker-content`: Fade in/out text content
- `.ticker-content.visible`: Opacity 1 (displayed)

## WebSocket Message Types

### progress_update
```javascript
{
    type: 'progress_update',
    message: 'AI call 5/20 completed',
    progress: 25,
    confidence_score: 83,  // Optional: 0-100 scale
    session_id: 'session_id',
    timestamp: '2025-01-06T12:34:56'
}
```

### ticker_update
```javascript
{
    type: 'ticker_update',
    session_id: 'session_id',
    priority: 4,
    row_ids: 'Amazon - Home Products',
    column: 'Invest Now?',
    final_value: 'Hold',
    confidence: 'HIGH',
    confidence_emoji: '🟢',
    explanation: 'QC detected...',
    timestamp: '2025-01-06T12:34:56'
}
```

## Troubleshooting

### Progress Indicator Issues

**Progress square stays green despite low confidence**:
- Check backend logs for `[QC_CONFIDENCE_AVG]` messages
- Verify `confidence_score` is in WebSocket message
- Ensure `globalState.currentConfidenceScore` is being updated

**Progress square gets bigger during rotation**:
- CSS should pause pulse animation during spin: `animation-play-state: paused`

**Progress indicator doesn't reset to green**:
- Check `completeThinkingInCard()` sets `globalState.currentConfidenceScore = null`

**Green square appears at bottom-right corner instead of centered**:
- Verify `.progress-square-wrapper` has `transform-origin: center center`
- Check that wrapper animations use simple `scale()`, not `translate()` + `scale()`
- Ensure `.progress-square` has `transform: translate(-50%, -50%)` in CSS
- Verify all square animations include `translate(-50%, -50%)` in keyframes

**Progress indicator disappears during execution**:
- Check that card content clearing preserves the thinking indicator element
- Ensure `completeThinkingInCard()` is called at the right time (not too early)
- For table maker: Progress should stay visible through all execution steps until completion

**Progress square moves incorrectly**:
- Always update `progressWrapper.style.left`, never `progressSquare.style.left`
- Calculate wrapper position accounting for wrapper width offset:
  ```javascript
  const wrapperOffset = 37.5 / 2; // half of wrapper width
  const position = (progress / 100) * trackWidth - wrapperOffset;
  progressWrapper.style.left = `${position}px`;
  ```

### Ticker Issues

**Ticker messages not showing**:
- Check console for `[TICKER]` log messages
- Verify `activeCardId` is set or visible thinking indicator exists
- Ensure `currentValidationState` is 'preview' or 'full'

**Duplicate ticker messages**:
- Verify deduplication logic checks message `key` (row_ids|column)
- Check seen tracking is preserved when replacing messages

**Ticker text truncated too short**:
- Verify `isPortraitMode()` detection is correct
- Adjust character limits in `updateTickerDisplay()` function

## Table Maker Execution Flow

The table maker has a specific progress indicator flow during table generation:

### Execution Phases

**Phase 1: Interview** (dummy progress, phase='interview')
- Shows simulated progress during conversation with user
- Progress updates display but don't trigger UI changes
- Used to give user feedback while AI plans the table

**Phase 2: Execution** (real progress, phase='execution')
- Real table generation with actual progress
- Triggers step-specific UI updates (boxes for columns, rows, QC)

### Execution Steps

**Step 1: Column Definition**
- Progress indicator continues running
- ID Columns box appears (cyan background)
- Research Columns box appears (purple background)
- Card content cleared except for thinking indicator and progress-content container

**Step 2: (Reserved for future use)**

**Step 3: Row Discovery**
- Progress indicator continues running
- Discovered Rows box appears (orange background)
- Shows first 10 rows with ID column values

**Step 4: QC Review**
- Progress indicator continues running
- Updates approved row count in rows box

**Step 5: Completion**
- WebSocket message `table_execution_complete` arrives
- Progress updates to 100% with message "Table generation complete!"
- After 500ms: `completeThinkingInCard()` triggers shrink animation (600ms)
- After shrink completes: Preview Validation card appears

### Expected Visual Flow
1. User confirms table structure → Submit button shows "Thinking..."
2. Progress indicator appears and runs through interview phase
3. Execution begins → ID columns box appears
4. Rows box appears below research columns
5. Progress reaches 100% → "Table generation complete!"
6. Progress indicator shrinks away (600ms animation)
7. Preview Validation card appears with new progress indicator

### Common Issues

**Rows box not appearing**:
- Check backend sends `table_execution_update` with `current_step: 3`
- Verify `message.discovered_rows` array is present
- Ensure `phase: 'execution'` (not 'interview')
- Check `${cardId}-progress-content` container exists

**Progress indicator disappears too early**:
- Verify `handleTableExecutionComplete` uses `updateThinkingProgress(100)` not `completeThinkingInCard()`
- Only complete the indicator in the setTimeout before creating preview card

**Long gap between table completion and preview start**:
- Check setTimeout delays in `handleTableExecutionComplete`
- Should be 500ms before completion + 600ms shrink + immediate preview creation

## Related Files

### Backend
- `src/lambdas/validation/lambda_function.py`: Confidence calculation, progress updates
- `src/shared/websocket_client.py`: WebSocket message sending
- `src/shared/qc_module.py`: QC confidence extraction
- `src/lambdas/interface/actions/table_maker/`: Table maker execution flow

### Frontend
- `frontend/perplexity_validator_interface2.html`: Progress indicator UI, ticker UI, WebSocket handlers
  - `handleTableExecutionUpdate()`: Processes step-specific updates
  - `handleTableExecutionComplete()`: Manages completion and preview transition
  - `showColumnsBoxes()`, `showDiscoveredRowsBox()`: Display execution step boxes

### Configuration
- `src/prompts.yml`: Update Importance scale definition (0-5)
- `src/shared/perplexity_schema.py`: QC response schema with confidence fields
