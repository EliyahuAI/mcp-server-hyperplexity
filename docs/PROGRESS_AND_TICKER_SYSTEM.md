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

## Related Files

### Backend
- `src/lambdas/validation/lambda_function.py`: Confidence calculation, progress updates
- `src/shared/websocket_client.py`: WebSocket message sending
- `src/shared/qc_module.py`: QC confidence extraction

### Frontend
- `frontend/perplexity_validator_interface2.html`: Progress indicator UI, ticker UI, WebSocket handlers

### Configuration
- `src/prompts.yml`: Update Importance scale definition (0-5)
- `src/shared/perplexity_schema.py`: QC response schema with confidence fields
